"""End-to-end check that previously issued proxy URLs survive a backend restart.

This reproduces the production failure mode: the player holds rewritten playlist
URLs, the backend process loses its in-memory session store, and the player keeps
retrying those URLs. Before the ctx-token change every retry returned
404 "Playback session not found or expired".
"""

import os
import subprocess
import time
from pathlib import Path
from typing import Optional

import requests


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
PORT = 8012
BASE = f"http://127.0.0.1:{PORT}"
LOG = ROOT / "logs" / "smoke_test_recovery_server.log"


def start_server(log_handle) -> subprocess.Popen:
    env = os.environ.copy()
    env["SERVER_HOST"] = "127.0.0.1"
    env["SERVER_PORT"] = str(PORT)
    env["PYTHONUNBUFFERED"] = "1"
    return subprocess.Popen(
        [str(PYTHON), "main.py"],
        cwd=str(ROOT),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )


def stop_server(server: subprocess.Popen) -> None:
    server.terminate()
    try:
        server.wait(timeout=15)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait(timeout=5)


def wait_for_server(timeout: float = 45.0) -> None:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            if requests.get(f"{BASE}/health", timeout=2).status_code == 200:
                return
        except Exception as exc:
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"Server did not become ready: {last_error}")


def wait_for_port_closed(timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            requests.get(f"{BASE}/health", timeout=1)
        except Exception:
            return
        time.sleep(0.3)


def first_playlist_url(playlist_text: str) -> Optional[str]:
    for line in playlist_text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return None


def main() -> int:
    LOG.parent.mkdir(exist_ok=True)
    if LOG.exists():
        LOG.unlink()
    log_handle = open(LOG, "w", encoding="utf-8")
    server = start_server(log_handle)

    try:
        wait_for_server()

        catalog = requests.get(f"{BASE}/api/fbstream/catalog", params={"category": "live-now"}, timeout=30)
        catalog.raise_for_status()
        items = catalog.json()["categories"][0]["items"]
        if not items:
            raise RuntimeError("catalog returned no live-now items")
        target_url = os.getenv("FBSTREAM_TEST_URL", "").strip() or items[0]["targetUrl"]
        print("target url:", target_url)

        stream = requests.get(f"{BASE}/api/fbstream/stream", params={"url": target_url}, timeout=240)
        stream.raise_for_status()
        stream_json = stream.json()
        playback_url = stream_json["playbackUrl"]
        playback_id = stream_json["playbackId"]
        print("playbackId:", playback_id)
        if "ctx=" not in playback_url:
            raise RuntimeError(f"playbackUrl is missing ctx token: {playback_url}")

        first = requests.get(playback_url, timeout=60)
        if first.status_code != 200 or "#EXTM3U" not in first.text:
            raise RuntimeError(f"initial proxy playlist failed: HTTP {first.status_code}\n{first.text[:500]}")
        nested_url = first_playlist_url(first.text)
        if not nested_url:
            raise RuntimeError("initial playlist had no nested URL")
        if "ctx=" not in nested_url:
            raise RuntimeError(f"rewritten nested URL is missing ctx token: {nested_url}")
        print("initial playlist OK; nested url carries ctx")

        # --- Simulate the production failure: backend process restarts mid-playback ---
        print("restarting backend to wipe in-memory sessions...")
        stop_server(server)
        wait_for_port_closed()
        log_handle.write("\n===== SERVER RESTARTED (sessions wiped) =====\n")
        log_handle.flush()
        server = start_server(log_handle)
        wait_for_server()

        # The player retries the URLs it already holds.
        retry_root = requests.get(playback_url, timeout=60)
        if retry_root.status_code != 200 or "#EXTM3U" not in retry_root.text:
            raise RuntimeError(
                f"RECOVERY FAILED: root playlist after restart returned HTTP {retry_root.status_code}\n"
                f"{retry_root.text[:500]}"
            )
        print("root playlist after restart: 200 OK")

        retry_nested = requests.get(nested_url, timeout=60)
        if retry_nested.status_code != 200:
            raise RuntimeError(
                f"RECOVERY FAILED: nested resource after restart returned HTTP {retry_nested.status_code}\n"
                f"{retry_nested.text[:500]}"
            )
        print("nested resource after restart: 200 OK content-type:", retry_nested.headers.get("content-type"))

        # A URL with no ctx should still 404 (no silent open-proxy behaviour without context).
        bare_url = playback_url.split("?", 1)[0]
        bare = requests.get(bare_url, timeout=30)
        if bare.status_code != 404:
            raise RuntimeError(f"expected 404 for ctx-less unknown session, got HTTP {bare.status_code}")
        print("ctx-less unknown session correctly rejected: 404")

        log_handle.flush()
        log_text = LOG.read_text(encoding="utf-8", errors="replace")
        after_restart = log_text.split("===== SERVER RESTARTED", 1)[-1]
        if "Restored playback session from URL context" not in after_restart:
            raise RuntimeError("server log does not show session restoration after restart")
        if "Playback session not found or expired" in after_restart.split("ctx-less", 1)[0] and after_restart.count(
            "Playback session not found or expired"
        ) > 1:
            raise RuntimeError("unexpected 'session not found' failures after restart")
        print("server log confirms: Restored playback session from URL context")

        print("RECOVERY SMOKETEST PASSED")
        return 0
    finally:
        stop_server(server)
        try:
            log_handle.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
