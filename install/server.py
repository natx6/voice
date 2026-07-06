#!/usr/bin/env python3
"""Local server that serves the soundhuman frontend and handles capture.
Run this after installation to use the app locally with capture support.

API calls are proxied to your soundhuman cloud server.
"""

import http.server
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

# ── CONFIG ──────────────────────────────────────────────────────────
# Change this to your cloud server URL
CLOUD_SERVER = os.environ.get("SOUNDHUMAN_SERVER", "http://localhost:8765")
FRONTEND_DIR = Path(__file__).parent / "frontend"
PORT = 8766

# ── Audio Capture (local only) ──────────────────────────────────────

def get_virtual_sink():
    """Get or create the VoiceChanger virtual sink."""
    if sys.platform == "linux":
        try:
            result = subprocess.run(
                ["pactl", "list", "sinks", "short"],
                capture_output=True, text=True, timeout=5,
            )
            if "VoiceChanger" in result.stdout:
                return "VoiceChanger"
            # Create the sink
            subprocess.run(
                ["pactl", "load-module", "module-null-sink",
                 "sink_name=VoiceChanger",
                 "sink_properties=device.description=VoiceChanger"],
                check=True, timeout=5,
            )
            return "VoiceChanger"
        except Exception as e:
            print(f"  PulseAudio setup failed: {e}")
            return None
    elif sys.platform == "darwin":
        # macOS - BlackHole should be installed by the installer
        return "BlackHole"
    elif sys.platform == "win32":
        # Windows - VB-Cable should be installed by the installer
        return "CABLE Input"
    return None


def play_audio(file_path: str, sink: str):
    """Play audio through the virtual sink for capture."""
    if not sink:
        return False
    try:
        if sys.platform == "linux":
            subprocess.run(
                ["paplay", "--raw", f"--rate=24000", "--format=s16le",
                 "--channels=1", f"--device={sink}", file_path],
                check=True, timeout=600,
            )
        elif sys.platform == "darwin":
            # macOS - play through BlackHole using ffmpeg
            subprocess.run(
                ["ffplay", "-nodisp", "-autoexit",
                 f"-f", "s16le", f"-ar", "24000", "-ac", "1",
                 file_path],
                check=True, timeout=600,
            )
        elif sys.platform == "win32":
            # Windows - play through VB-Cable
            subprocess.run(
                ["ffplay", "-nodisp", "-autoexit",
                 f"-f", "s16le", f"-ar", "24000", "-ac", "1",
                 file_path],
                check=True, timeout=600,
            )
        return True
    except Exception as e:
        print(f"  Playback failed: {e}")
        return False


# ── Proxy Handler ──────────────────────────────────────────────────

class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def do_GET(self):
        # Serve frontend files directly
        if not self.path.startswith("/api/"):
            return super().do_GET()
        self._proxy_request("GET")

    def do_POST(self):
        self._proxy_request("POST")

    def do_DELETE(self):
        self._proxy_request("DELETE")

    def do_PATCH(self):
        self._proxy_request("PATCH")

    def _proxy_request(self, method):
        """Proxy API calls to the cloud server."""
        url = f"{CLOUD_SERVER}{self.path}"
        body = None
        if method in ("POST", "PATCH"):
            length = int(self.headers.get("Content-Length", 0))
            if length > 0:
                body = self.rfile.read(length)

        try:
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": self.headers.get("Content-Type", "application/json")},
                method=method,
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", resp.headers.get("Content-Type", "application/json"))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def log_message(self, format, *args):
        print(f"  {args[0]} {args[1]} {args[2]}")


# ── Main ───────────────────────────────────────────────────────────

def main():
    sink = get_virtual_sink()
    print(f"\n  🎙  soundhuman local server")
    print(f"  ─────────────────────────")
    print(f"  Cloud server: {CLOUD_SERVER}")
    print(f"  Virtual sink: {sink or 'not found — capture disabled'}")
    print(f"  Frontend:     http://localhost:{PORT}")
    print(f"  ─────────────────────────")
    print(f"  Press Ctrl+C to stop\n")

    server = http.server.HTTPServer(("", PORT), ProxyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
