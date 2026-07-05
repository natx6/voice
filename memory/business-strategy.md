---
name: business-strategy
description: Full cost breakdown, recommended privacy services, and anonymity infrastructure for investors
metadata:
  type: reference
---

# soundhuman — Cost & Anonymity Infrastructure

## Recommended Privacy Services

### VPS Providers (crypto-friendly, no KYC)

| Provider | Accepts Crypto? | KYC Required? | Jurisdiction | Privacy Reputation | Starting Price |
|----------|----------------|---------------|-------------|-------------------|---------------|
| **Hetzner** | ✅ Yes (via BitPay) | ✅ Yes (ID required) | Germany | Mixed — follows EU law | €4/mo |
| **Contabo** | ✅ Yes (crypto via support) | ⚠️ Sometimes asks | Germany | Standard | €6/mo |
| **Njalla** | ✅ Yes (Monero, BTC) | ❌ No KYC | Nevis | Excellent — privacy-first | $15/mo |
| **OrangeWebsite** | ✅ Yes (BTC) | ❌ No KYC | Iceland | Strong — no data retention | €5/mo |
| **1984 Hosting** | ✅ Yes (BTC) | ❌ No KYC | Iceland | Very strong | €3/mo |
| **BuyVM / FranTech** | ✅ Yes (BTC, XMR) | ❌ No KYC | Luxembourg | Mixed | $3.50/mo |
| **Shinjiru** | ✅ Yes (BTC) | ⚠️ Minimal | Malaysia | Strong | $10/mo |
| **SpartanHost** | ✅ Yes (XMR) | ❌ No KYC | US (WA) | Mixed | $5/mo |

**Recommendation:** Njalla or OrangeWebsite for maximum privacy. Hetzner for value (lowest price, but ID required — account in a shell company name works).

### Domain Registrars (no identity required)

| Registrar | Accepts Crypto? | WHOIS Privacy | Jurisdiction | Notes |
|-----------|----------------|--------------|-------------|-------|
| **Njalla** | ✅ BTC, XMR | ✅ Included | Nevis | They own the domain, you use it. Best privacy. |
| **OrangeWebsite** | ✅ BTC | ✅ Free | Iceland | Can register with pseudonym |
| **1984 Hosting** | ✅ BTC | ✅ Free | Iceland | Strong privacy laws |
| **Namecheap** | ⚠️ BTC (via LoadCoin) | ✅ Included | US | Accepts BTC but US jurisdiction |

**Recommendation:** Njalla. They register the domain under their name, not yours. No one can connect the domain to you.

### Email (no phone required)

| Provider | Signup Requirements | Privacy | Notes |
|----------|-------------------|---------|-------|
| **ProtonMail** | Email only (no phone) | Strong — Swiss jurisdiction | Free tier enough |
| **Tutanota** | Email only (no phone) | Strong — German jurisdiction | Free tier |
| **SimpleLogin** | Can be anonymous | Good | Works with ProtonMail |

### Crypto On-Ramps (for ElevenLabs payment)

| Service | KYC? | Can Get ElevenLabs Credit? | Privacy |
|---------|------|--------------------------|---------|
| **ElevenLabs Gift Cards** from crypto exchange | ⚠️ Exchange may need KYC | ✅ Directly to account | Partial — exchange knows you |
| **Bitrefill** (gift cards) | ⚠️ Sometimes needs email | ✅ Buy gift card with crypto | Good — pay with XMR for full privacy |
| **No-KYC crypto exchange** (fixedfloat, majesticbank) | ❌ No KYC | ⚠️ Convert to BTC → Bitrefill | Best — no identity anywhere |
| **Privacy.com** virtual cards funded by crypto | ✅ Has KYC | ✅ Works at ElevenLabs | Poor — requires ID |

**The anonymous chain:** Buy XMR on a no-KYC exchange → send to Bitrefill → buy ElevenLabs gift card → apply to account.

### Residential Proxies (for account creation)

| Provider | KYC? | Notes | Price |
|----------|------|-------|-------|
| **IPRoyal** (residential) | ⚠️ Email only | Pay with crypto | $4/GB |
| **BrightData** | ✅ ID required | Not anonymous | $15/GB |
| **Proxylite** | ❌ No KYC | BTC accepted | $2/GB |
| **TOR** (free) | ❌ None | Free but may be blocked | $0 |

**Recommendation:** Use TOR for account creation. If ElevenLabs blocks TOR, use Proxylite or IPRoyal with crypto.

## Full Anonymity Stack — Monthly Costs

### Identity Layer (one-time setup, ~$30)

| Item | Cost | Where |
|------|------|-------|
| ProtonMail (anonymous email) | $0 | proton.me |
| Njalla domain (1 year) | $15 | njalla.com |
| **Total** | **~$15** | |

### Infrastructure Layer (monthly)

| Item | Cost | Provider |
|------|------|----------|
| VPS | $10-15 | Hetzner or OrangeWebsite |
| Cloudflare (free HTTPS proxy) | $0 | cloudflare.com |
| **Subtotal** | **~$12/mo** | |

### ElevenLabs Funding (one-time, as needed)

| Item | Cost | Method |
|------|------|--------|
| Crypto → Bitrefill → ElevenLabs gift card | $5-50 | XMR via no-KYC exchange |
| **Subtotal per top-up** | **~$30 avg** | |

### Operational Security (monthly, optional)

| Item | Cost | Notes |
|------|------|-------|
| Residential proxy (for account mgmt) | $10/mo | Only if TOR doesn't work |
| **Optional total** | **~$10/mo** | |

## Grand Total

| Scenario | First Month | Subsequent Months |
|----------|------------|-------------------|
| **Minimum viable** | ~$27 setup + $12 VPS = **$39** | **~$12/mo** |
| **Full anonymity stack** | ~$27 + $12 VPS + $10 proxy = **$49** | **~$22/mo** |
| **With ElevenLabs credit** | Above + $30 gift card = **~$79** | **~$22/mo + gift cards** |

## Jurisdiction Analysis — Which Laws Protect You?

| Provider | Country | What they'd do with a subpoena |
|----------|---------|-------------------------------|
| Hetzner | Germany | ✅ Will comply, but requires legal process |
| OrangeWebsite | Iceland | ✅ Strong privacy laws, limited data retention |
| Njalla | Nevis | ✅ Jurisdiction is hard to reach legally |
| Cloudflare | US | ⚠️ Will comply, but only sees proxied traffic |
| ProtonMail | Switzerland | ✅ Strong privacy, can't decrypt data |
| Bitrefill | US/Global | ⚠️ Limited data held |
| Monero (XMR) | Decentralized | ✅ Cannot be frozen or traced |

**Best jurisdiction combo:** Swiss email + Iceland VPS + Nevis domain + Cloudflare CDN = no single jurisdiction can see everything.

## Weak Points — What Can Still Leak

| Leak | How it happens | Fix |
|------|---------------|-----|
| **ElevenLabs API key** leaked if server compromised | Key in env var on VPS | Restrict VPS access, use secrets manager |
| **Browser fingerprint** when accessing ElevenLabs dashboard | Your real browser | Use dedicated Firefox container + TOR |
| **Timing correlation** | Usage patterns matching a known person | Stagger usage, add random delays |
| **Blockchain analysis** | SOL payments traced | Accept XMR only, use subaddresses |
| **User trust** | Users know who you are from demos | You already leaked this — new anonymous instance needed |

## Honest Assessment

The weakest link is not the tech — it's that you already demoed to people who know your identity. The current instance is burned for anonymity.

**For a clean start:** Don't reuse anything from the current setup. New ElevenLabs, new VPS, new domain, new everything. The code is public on GitHub — anyone can verify it doesn't contain keys. That part is safe.

Cost to go fully anonymous: **~$50 first month, ~$12/mo after.** That's the price of ElevenLabs not knowing who you are.
