import os
import subprocess
import time
from pathlib import Path
from typing import Optional

import requests


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
PORT = 8011
BASE = f"http://127.0.0.1:{PORT}"
SMOKE_LOG = ROOT / "logs" / "smoke_test_server.log"


def wait_for_server(timeout: float = 45.0) -> None:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            response = requests.get(f"{BASE}/health", timeout=2)
            if response.status_code == 200:
                return
        except Exception as exc:
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"Server did not become ready: {last_error}")


def assert_status(response: requests.Response, expected: int, label: str) -> None:
    if response.status_code != expected:
        raise RuntimeError(
            f"{label} failed: HTTP {response.status_code}\n{response.text[:3000]}"
        )


def first_playlist_url(playlist_text: str) -> Optional[str]:
    for line in playlist_text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return None


def first_key_uri(playlist_text: str) -> Optional[str]:
    marker = 'URI="'
    for line in playlist_text.splitlines():
        index = line.find(marker)
        if index >= 0:
            rest = line[index + len(marker):]
            end = rest.find('"')
            if end >= 0:
                return rest[:end]
    return None


def main() -> int:
    env = os.environ.copy()
    env["SERVER_HOST"] = "127.0.0.1"
    env["SERVER_PORT"] = str(PORT)
    env["PYTHONUNBUFFERED"] = "1"

    SMOKE_LOG.parent.mkdir(exist_ok=True)
    if SMOKE_LOG.exists():
        SMOKE_LOG.unlink()
    log_handle = open(SMOKE_LOG, "w", encoding="utf-8")
    server = subprocess.Popen(
        [str(PYTHON), "main.py"],
        cwd=str(ROOT),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        wait_for_server()

        health = requests.get(f"{BASE}/health", timeout=10)
        assert_status(health, 200, "health")
        print("health:", health.json())

        catalog = requests.get(
            f"{BASE}/api/fbstream/catalog",
            params={"category": os.getenv("FBSTREAM_TEST_CATEGORY", "live-now")},
            timeout=30,
        )
        assert_status(catalog, 200, "catalog")
        catalog_json = catalog.json()
        items = catalog_json["categories"][0]["items"]
        if not items:
            raise RuntimeError("catalog returned no live-now items")
        print("catalog items:", len(items))

        target_url = os.getenv("FBSTREAM_TEST_URL", "").strip()
        target_title = "configured test url"
        if not target_url:
            first = items[0]
            target_url = first["targetUrl"]
            target_title = first["title"]
        print("target title:", target_title)
        print("target url:", target_url)

        stream = requests.get(
            f"{BASE}/api/fbstream/stream",
            params={"url": target_url},
            timeout=240,
        )
        assert_status(stream, 200, "stream")
        stream_json = stream.json()
        if not stream_json.get("playbackId"):
            raise RuntimeError(f"stream response missing playbackId: {stream_json}")
        if not stream_json.get("streamUrl"):
            raise RuntimeError(f"stream response missing streamUrl: {stream_json}")
        print("stream extractor:", stream_json.get("extractor"))
        print("playbackId:", stream_json.get("playbackId"))
        print("playbackUrl:", stream_json.get("playbackUrl"))

        proxy = requests.get(stream_json["playbackUrl"], timeout=60)
        assert_status(proxy, 200, "proxy playlist")
        proxy_text = proxy.text
        if "#EXTM3U" not in proxy_text:
            raise RuntimeError(f"proxy playlist is not HLS:\n{proxy_text[:2000]}")
        if "/api/fbstream/proxy/" not in proxy_text:
            raise RuntimeError("proxy playlist was not rewritten through backend proxy")
        print("proxy content-type:", proxy.headers.get("content-type"))
        print("proxy playlist preview:\n", proxy_text[:1200])

        nested_url = first_playlist_url(proxy_text)
        if not nested_url:
            raise RuntimeError("proxy playlist did not contain a nested playlist or media URL")
        print("nested proxy url:", nested_url)

        nested = requests.get(nested_url, timeout=60)
        assert_status(nested, 200, "nested proxy resource")
        print("nested content-type:", nested.headers.get("content-type"))

        nested_text = nested.text if "#EXTM3U" in nested.text else ""
        if nested_text:
            print("nested playlist preview:\n", nested_text[:1200])
            segment_url = first_key_uri(nested_text) or first_playlist_url(nested_text)
            if not segment_url:
                raise RuntimeError("nested playlist did not contain a key or segment URL")
            print("media proxy url:", segment_url)
            media = requests.get(segment_url, timeout=60, headers={"Range": "bytes=0-0"})
            if media.status_code not in {200, 206}:
                raise RuntimeError(
                    f"media proxy fetch failed: HTTP {media.status_code}\n{media.text[:500]}"
                )
            print("media status:", media.status_code)
            print("media content-type:", media.headers.get("content-type"))
            print("media bytes:", len(media.content))
        else:
            print("nested response bytes:", len(nested.content))

        print("SMOKETEST PASSED")
        return 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)

        try:
            log_handle.close()
        except Exception:
            pass

        output = ""
        try:
            if SMOKE_LOG.exists():
                output = SMOKE_LOG.read_text(encoding="utf-8", errors="replace")
        except Exception:
            output = ""
        if output.strip():
            print("\n--- server output ---")
            print(output[-8000:])


if __name__ == "__main__":
    raise SystemExit(main())
