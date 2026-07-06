#!/bin/bash
# soundhuman — Linux/macOS installer
# Usage: curl -s https://YOUR_SERVER/install.sh | bash
# Or:    bash install.sh

set -e

SERVER="${SOUNDHUMAN_SERVER:-http://localhost:8765}"
INSTALL_DIR="$HOME/.soundhuman-app"
PYTHON="${PYTHON:-python3}"

echo ""
echo "  ╔══════════════════════════════════╗"
echo "  ║     soundhuman installer         ║"
echo "  ╚══════════════════════════════════╝"
echo ""

# ── Detect OS ──
OS="linux"
if [[ "$(uname)" == "Darwin" ]]; then
    OS="macos"
fi
echo "  Detected: $OS"

# ── Install virtual audio driver ──
if [[ "$OS" == "linux" ]]; then
    echo "  Installing PulseAudio virtual sink..."
    if command -v pactl &>/dev/null; then
        # Check if VoiceChanger sink exists
        if ! pactl list sinks short 2>/dev/null | grep -q VoiceChanger; then
            pactl load-module module-null-sink \
                sink_name=VoiceChanger \
                sink_properties=device.description=VoiceChanger 2>/dev/null || true
        fi
        echo "  ✅ VoiceChanger sink ready"
    else
        echo "  ⚠️  pulseaudio-utils not found. Install with: sudo apt install pulseaudio-utils"
    fi
elif [[ "$OS" == "macos" ]]; then
    echo "  Checking for BlackHole..."
    if ! system_profiler SPAudioDataType 2>/dev/null | grep -q BlackHole; then
        echo "  ⚠️  BlackHole not found. Download and install from:"
        echo "      https://github.com/ExistentialAudio/BlackHole"
        echo "  Then run this installer again."
        echo ""
        echo "  Quick install: brew install --cask blackhole"
        if command -v brew &>/dev/null; then
            echo "  Installing via Homebrew..."
            brew install --cask blackhole 2>/dev/null || true
        fi
    else
        echo "  ✅ BlackHole found"
    fi
fi

# ── Create install directory ──
echo "  Installing to: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

# ── Download or copy frontend ──
if [[ -d "$(dirname "$0")/frontend" ]]; then
    # Running from the repo
    echo "  Copying frontend from local build..."
    cp -r "$(dirname "$0")/frontend" "$INSTALL_DIR/"
else
    echo "  Downloading frontend from $SERVER..."
    cd "$INSTALL_DIR"
    curl -sL "$SERVER/api/install/download" -o frontend.zip 2>/dev/null || {
        echo "  ⚠️  Could not download from server. Using fallback..."
        mkdir -p "$INSTALL_DIR/frontend"
    }
    if [[ -f frontend.zip ]]; then
        unzip -q frontend.zip -d frontend 2>/dev/null || mkdir -p frontend
        rm frontend.zip
    fi
fi

# ── Copy server script ──
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$SCRIPT_DIR/server.py" ]]; then
    cp "$SCRIPT_DIR/server.py" "$INSTALL_DIR/"
else
    # Download server.py from the repo
    curl -sL "https://raw.githubusercontent.com/natx6/voice/main/install/server.py" \
        -o "$INSTALL_DIR/server.py" 2>/dev/null || {
        echo "  ⚠️  Could not download server.py"
    }
fi

# ── Create config ──
echo "{\"server\": \"$SERVER\"}" > "$INSTALL_DIR/config.json"

# ── Create launch script ──
LAUNCHER="$INSTALL_DIR/start.sh"
cat > "$LAUNCHER" << EOF
#!/bin/bash
cd "$INSTALL_DIR"
echo "  🎙  soundhuman starting..."
echo "  Server: $SERVER"
echo ""
export SOUNDHUMAN_SERVER="$SERVER"
$PYTHON server.py &
BGPID=\$!
sleep 1
if command -v xdg-open &>/dev/null; then
    xdg-open "http://localhost:8766" 2>/dev/null
elif command -v open &>/dev/null; then
    open "http://localhost:8766" 2>/dev/null
fi
echo ""
echo "  Press Ctrl+C to stop"
wait \$BGPID
EOF
chmod +x "$LAUNCHER"

# ── Create desktop shortcut (Linux) ──
if [[ "$OS" == "linux" ]]; then
    mkdir -p "$HOME/.local/share/applications"
    cat > "$HOME/.local/share/applications/soundhuman.desktop" << EOF
[Desktop Entry]
Name=soundhuman
Comment=Text that sounds like you
Exec=$LAUNCHER
Terminal=true
Type=Application
Categories=Audio;Utility;
EOF
    echo "  ✅ Desktop shortcut created"
fi

echo ""
echo "  ──────────────────────────────────────"
echo "  ✅ Installation complete!"
echo ""
echo "  Launch: $LAUNCHER"
echo "  Or:    bash $LAUNCHER"
echo ""
echo "  Open http://localhost:8766 in your browser"
echo "  ──────────────────────────────────────"
echo ""
