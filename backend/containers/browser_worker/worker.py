#!/usr/bin/env python3
"""
Browser worker: runs Chromium with CDP enabled and serves a health/control endpoint.

Environment variables:
    ACCOUNT_ID       - LinkedIn account UUID (used as profile sub-directory name)
    PROFILE_BASE     - base path where per-account profile dirs live (default: /app/profiles)
    CDP_PORT         - Chromium remote-debugging port (default: 9222)
    HEALTH_PORT      - health/control HTTP server port (default: 8080)
    PROXY_URL        - optional proxy for Chromium (e.g. http://user:pass@host:3128)
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ACCOUNT_ID   = os.getenv("ACCOUNT_ID", "default")
PROFILE_BASE = os.getenv("PROFILE_BASE", "/app/profiles")
CDP_PORT     = int(os.getenv("CDP_PORT", "9222"))
HEALTH_PORT  = int(os.getenv("HEALTH_PORT", "8080"))
PROXY_URL    = os.getenv("PROXY_URL", "")

PROFILE_DIR = Path(PROFILE_BASE) / ACCOUNT_ID

_chromium_proc: subprocess.Popen | None = None
_stop_event = threading.Event()


# ── Chromium management ───────────────────────────────────────────────────────

def _find_chromium() -> str:
    """Locate the Chromium binary on this image."""
    candidates = [
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    raise FileNotFoundError("No Chromium binary found. Checked: " + ", ".join(candidates))


def start_chromium() -> subprocess.Popen:
    global _chromium_proc

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    binary = _find_chromium()

    cmd = [
        binary,
        "--headless=new",
        f"--remote-debugging-port={CDP_PORT}",
        "--remote-debugging-address=0.0.0.0",
        f"--user-data-dir={PROFILE_DIR}",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-setuid-sandbox",
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--safebrowsing-disable-auto-update",
        "--disable-sync",
        "--disable-translate",
        "--metrics-recording-only",
        "--mute-audio",
        "--no-crash-upload",
        "about:blank",
    ]
    if PROXY_URL:
        cmd.append(f"--proxy-server={PROXY_URL}")

    print(f"[worker] Starting Chromium for account {ACCOUNT_ID} on CDP port {CDP_PORT}", flush=True)
    _chromium_proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    return _chromium_proc


def _is_chromium_alive() -> bool:
    return _chromium_proc is not None and _chromium_proc.poll() is None


def _watchdog():
    """Restart Chromium automatically if it crashes."""
    while not _stop_event.is_set():
        if not _is_chromium_alive():
            print("[worker] Chromium exited — restarting in 3s", flush=True)
            time.sleep(3)
            start_chromium()
        time.sleep(5)


# ── Health / control HTTP server ──────────────────────────────────────────────

class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            alive = _is_chromium_alive()
            body = json.dumps({
                "status": "ok" if alive else "starting",
                "cdp_port": CDP_PORT,
                "account_id": ACCOUNT_ID,
                "pid": _chromium_proc.pid if _chromium_proc else None,
            }).encode()
            self.send_response(200 if alive else 503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/stop":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"stopping"}')
            _stop_event.set()
            if _chromium_proc:
                _chromium_proc.terminate()
            sys.exit(0)

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):  # silence access logs
        pass


def _run_health_server():
    server = HTTPServer(("0.0.0.0", HEALTH_PORT), _Handler)
    print(f"[worker] Health server on port {HEALTH_PORT}", flush=True)
    server.serve_forever()


# ── Graceful shutdown ─────────────────────────────────────────────────────────

def _handle_signal(signum, _frame):
    print(f"[worker] Received signal {signum} — shutting down", flush=True)
    _stop_event.set()
    if _chromium_proc:
        _chromium_proc.terminate()
    sys.exit(0)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT,  _handle_signal)

    start_chromium()

    # Health server in background thread
    health_thread = threading.Thread(target=_run_health_server, daemon=True)
    health_thread.start()

    # Watchdog in background thread
    watchdog_thread = threading.Thread(target=_watchdog, daemon=True)
    watchdog_thread.start()

    # Block main thread until stop requested
    _stop_event.wait()
    if _chromium_proc:
        _chromium_proc.terminate()
        _chromium_proc.wait(timeout=10)


if __name__ == "__main__":
    main()
