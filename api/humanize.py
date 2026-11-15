"""Turn written text into something a person would actually say out loud.

ElevenLabs v3 renders audio tags ([sighs], [pause], [breaths]) and reads
punctuation as timing. Given clean written prose it produces clean read prose —
metronomic, no breaths, no repairs. Real speech is irregular: false starts,
filler openers, trailing off, silence where a sentence should end.

This is deterministic and offline. Same text and seed always give the same
result so a good take can be reproduced, and nothing leaves the machine.
"""

from __future__ import annotations

import hashlib
import random
import re

# Missing-apostrophe forms. Kept to unambiguous ones — "were", "ill", "well" and
# "its" all have honest non-contraction readings, so they are left alone.
_CONTRACTIONS = {
    "dont": "don't", "doesnt": "doesn't", "didnt": "didn't", "isnt": "isn't",
    "arent": "aren't", "wasnt": "wasn't", "werent": "weren't", "cant": "can't",
    "couldnt": "couldn't", "wouldnt": "wouldn't", "shouldnt": "shouldn't",
    "wont": "won't", "havent": "haven't", "hasnt": "hasn't", "hadnt": "hadn't",
    "thats": "that's", "whats": "what's", "wheres": "where's",
    "theres": "there's", "heres": "here's", "hows": "how's", "whos": "who's",
    "youre": "you're", "theyre": "they're", "weve": "we've", "youve": "you've",
    "ive": "I've", "im": "I'm", "lets": "let's", "aint": "ain't",
    "gonna": "gonna", "youd": "you'd", "theyd": "they'd", "wed": "we'd",
    "ive": "I've", "wouldve": "would've", "couldve": "could've",
    "shouldve": "should've", "mustnt": "mustn't", "neednt": "needn't",
}

# Full-word contractions the voice already knows but reads stiffly.
_FORMAL = [
    (r"\bI am\b", "I'm"), (r"\byou are\b", "you're"), (r"\bhe is\b", "he's"),
    (r"\bshe is\b", "she's"), (r"\bit is\b", "it's"), (r"\bwe are\b", "we're"),
    (r"\bthey are\b", "they're"), (r"\bdo not\b", "don't"),
    (r"\bdoes not\b", "doesn't"), (r"\bdid not\b", "didn't"),
    (r"\bwill not\b", "won't"), (r"\bcan not\b", "can't"),
    (r"\bcannot\b", "can't"),
    (r"\bhave not\b", "haven't"), (r"\bhas not\b", "hasn't"),
    (r"\bwould not\b", "wouldn't"), (r"\bshould not\b", "shouldn't"),
    (r"\bcould not\b", "couldn't"), (r"\bI will\b", "I'll"),
    (r"\byou will\b", "you'll"), (r"\bwe will\b", "we'll"),
    (r"\bI have\b", "I've"), (r"\byou have\b", "you've"),
    (r"\bgoing to\b", "gonna"), (r"\bwant to\b", "wanna"),
    (r"\bgot to\b", "gotta"), (r"\bkind of\b", "kinda"),
    (r"\bsort of\b", "sorta"), (r"\bbecause\b", "'cause"),
    (r"\bin order to\b", "to"), (r"\bprior to\b", "before"),
    (r"\bapproximately\b", "about"), (r"\bsufficient\b", "enough"),
    (r"\bnumerous\b", "a lot of"), (r"\butilize\b", "use"),
    (r"\bfurthermore\b", "also"), (r"\bhowever\b", "but"),
    (r"\bnevertheless\b", "still"), (r"\badditionally\b", "plus"),
    (r"\bin the event that\b", "if"), (r"\bwith regard to\b", "about"),
]

# Sentence openers a person drops in without thinking. None of these carry
# meaning; all of them buy the voice a beat of thought.
_OPENERS = ["So", "Yeah", "I mean", "Honestly", "Look", "You know", "Okay so"]

# Only insert a breath-type tag on sentences that plausibly provoke one.
_HEAVY = re.compile(
    r"\b(sorry|tired|fine|whatever|never ?mind|forget it|doesn't matter|"
    r"upset|angry|sad|hard|difficult|worried|scared|hurt|miss|alone|"
    r"please|thanks|thank you|honestly|seriously)\b",
    re.IGNORECASE,
)
_LIGHT = re.compile(r"\b(laugh|funny|joke|haha|whatever|anyway)\b", re.IGNORECASE)

_STYLE_TAGS = {
    "sad": ["[sighs]", "[breaths]", "[short pause]"],
    "excited": ["[laughs]", "[breaths]", "[short pause]"],
    "angry": ["[sighs]", "[short pause]"],
    "anxious": ["[breaths]", "[short pause]", "[breaths]"],
    "smug": ["[chuckles]", "[short pause]"],
    "comforting": ["[breaths]", "[pause]"],
    "conversational": ["[breaths]", "[short pause]", "[pause]"],
    "auto": ["[breaths]", "[short pause]", "[pause]"],
}


def _restore_apostrophes(text: str) -> str:
    def sub(m: re.Match) -> str:
        word = m.group(0)
        low = word.lower()
        rep = _CONTRACTIONS.get(low)
        if not rep:
            return word
        # im/ive/id only read as contractions when capitalised or after a pronoun.
        if low in {"im", "ive", "id"} and not word[0].isupper():
            return word
        return rep

    return re.sub(r"\b[A-Za-z']+\b", sub, text)


def _split_long_sentences(text: str, rng: random.Random) -> str:
    """Break a long clause at its first comma — speech comes in shorter bites."""
    out = []
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        words = sentence.split()
        if len(words) > 15 and sentence.count(",") >= 1:
            head, tail = sentence.split(",", 1)
            if len(head.split()) >= 5 and len(tail.split()) >= 4:
                tail = tail.strip()
                tail = tail[0].upper() + tail[1:] if tail else tail
                out.append(head.strip() + ".")
                out.append(tail)
                continue
        out.append(sentence)
    return " ".join(out)


def _add_false_start(text: str, rng: random.Random) -> str:
    """A repair that cuts off mid-clause — 'I don't— I don't know'. Repeating the
    whole phrase sounds like an acting exercise; real repairs drop one word."""
    m = re.search(r"\b(I(?:\s+just|\s+really|\s+guess|\s+thought|\s+mean|"
                  r"\s+don't|\s+didn't|\s+was|\s+know)?(?:\s+\w+){0,2})\b", text)
    if not m:
        return text
    clause = m.group(0).strip()
    words = clause.split()
    if len(words) < 2 or rng.random() > 0.30:
        return text
    cut = " ".join(words[:-1])
    return text[:m.start()] + f"{cut}— {clause}" + text[m.end():]


# Words that are safe to lowercase when they open a sentence mid-flow. Anything
# else keeps its capital, which protects names.
_LOWERABLE = {
    "the", "this", "that", "it", "it's", "you", "you're", "we", "they", "he",
    "she", "there", "here", "my", "your", "his", "her", "what", "when",
    "where", "how", "why", "who", "and", "but", "so", "no", "yes", "just",
    "maybe", "nothing", "everything", "nobody", "someone", "somebody", "look",
    "okay", "alright", "fine", "sorry", "thanks", "thank you", "please",
    "honestly", "yeah", "nah", "i've", "i'll", "i'd", "don't", "can't",
    "didn't", "doesn't", "isn't", "won't", "are", "is", "was", "were", "do",
    "does", "did", "have", "has", "had", "everyone", "people", "life", "all",
}


def _lower_first(text: str) -> str:
    """Lowercase the opening word, unless it is 'I' or looks like a name."""
    if not text:
        return text
    word = re.split(r"[\s,.!?…—]", text, maxsplit=1)[0]
    if word.lower().strip("'") == "i" or word in {"I", "I'm", "I've", "I'll", "I'd"}:
        return text
    if word.lower() in _LOWERABLE or word[0].islower():
        return text[0].lower() + text[1:]
    return text


def _soften_punctuation(text: str, rng: random.Random, style: str) -> str:
    """Trail off at sentence ends; hesitate at commas. Never join with a dash —
    a dash across a full stop drags the next capital letter with it."""
    ellipsis_rate = {"sad": 0.6, "anxious": 0.5, "smug": 0.45,
                     "comforting": 0.3}.get(style, 0.35)
    dash_rate = {"anxious": 0.45, "angry": 0.35}.get(style, 0.2)

    pieces = re.split(r"(?<=[.!?])(\s+)", text)
    for i, piece in enumerate(pieces):
        if i % 2:  # whitespace runs
            continue
        body = piece.rstrip(".!" + "?" * (piece.endswith("?")))
        if not body or piece.endswith("?"):
            continue
        if rng.random() < ellipsis_rate:
            pieces[i] = body + "..."
    text = "".join(pieces)

    # A comma mid-sentence becomes a beat of hesitation sometimes.
    out = []
    for chunk in re.split(r"(\s+)", text):
        if chunk == "," and rng.random() < 0.35:
            out.append(" —")
        else:
            out.append(chunk)
    return "".join(out)


def _insert_tags(text: str, rng: random.Random, style: str) -> str:
    """Audio tags, budgeted by length so a short line does not become all stagecraft."""
    tags = _STYLE_TAGS.get(style, _STYLE_TAGS["conversational"])
    sentences = [s for s in re.split(r"(?<=[.!?…])\s+", text.strip()) if s]
    if not sentences:
        return text
    words = len(text.split())
    budget = max(1, min(4, words // 12))
    chosen = set()

    if _HEAVY.search(text):
        chosen.add(0)
    if _LIGHT.search(text) and "[chuckles]" in tags + ["[chuckles]"]:
        tag_laugh = "[chuckles]"
    else:
        tag_laugh = None

    # Always put a beat before a deflection — "it's fine", "whatever". That
    # turn is where a spoken take separates from a read one, so it is not left
    # to the random draw. Matched without apostrophes: humanize() strips them.
    for idx, s in enumerate(sentences):
        head = s.strip().lower()
        if idx and re.match(r"(but\b|and yet|its fine|it is fine|im fine|i am fine|"
                            r"anyway\b|whatever|never ?mind|doesn'?t matter|"
                            r"no rush|never mind)", head):
            chosen.add(idx)
            break

    while len(chosen) < budget:
        pick = rng.randrange(len(sentences))
        if pick in chosen:
            if len(chosen) >= len(sentences):
                break
            continue
        chosen.add(pick)

    for idx in sorted(chosen):
        s = sentences[idx]
        tag = tag_laugh if (idx == 0 and tag_laugh) else rng.choice(tags)
        if tag in s:
            continue
        if idx == 0:
            sentences[idx] = f"{tag} {_lower_first(s)}"
        else:
            sentences[idx] = f"{tag} {s}"
    return " ".join(sentences)


def humanize(text: str, style: str = "conversational", seed: int | None = None) -> str:
    """Rewrite written text as speech. Deterministic for a given seed."""
    if not text or not text.strip():
        return text

    if seed is None:
        seed = int(hashlib.sha256(f"{style}|{text}".encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)

    body = re.sub(r"\s+", " ", text).strip()
    body = _restore_apostrophes(body)

    for pattern, rep in _FORMAL:
        body = re.sub(pattern, rep, body, flags=re.IGNORECASE)

    # Casual openers — "yes" and "hello" never survive a mic.
    body = re.sub(r"^Yes\b", "Yeah", body)
    body = re.sub(r"^No\b", "Nah", body)
    body = re.sub(r"^Hello\b", "Hey", body)
    body = re.sub(r"\bI think that\b", "I think", body)
    body = re.sub(r"\bthat I\b", "I", body) if rng.random() < 0.15 else body

    body = _split_long_sentences(body, rng)
    body = re.sub(r"\s+", " ", body).strip()

    # One filler opener, at the front, only when the line is long enough to carry it.
    if len(body.split()) > 6 and rng.random() < 0.8:
        body = f"{rng.choice(_OPENERS)}, {_lower_first(body)}"

    body = _add_false_start(body, rng)
    body = _soften_punctuation(body, rng, style)
    body = _insert_tags(body, rng, style)

    body = re.sub(r"\s+([,.!?…])", r"\1", body)
    body = re.sub(r"\s{2,}", " ", body).strip()
    return body
