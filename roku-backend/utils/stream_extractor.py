import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

import yt_dlp


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36"
)
YTDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "format": "best",
    "skip_download": True,
    "noplaylist": False,
    "extract_flat": False,
}


def extract_stream_url(url: str, http_headers: Optional[Dict[str, str]] = None) -> Dict:
    """Extract a playable stream URL using multiple tools in priority order."""
    clean_headers = _clean_headers(http_headers)
    errors: List[str] = []

    for extractor_name, extractor in (
        ("yt-dlp-python", _extract_with_python_ytdlp),
        ("yt-dlp-cli", _extract_with_cli_ytdlp),
        ("streamlink", _extract_with_streamlink),
    ):
        try:
            result = extractor(url, clean_headers)
            if result.get("streamUrl"):
                result.setdefault("httpHeaders", clean_headers)
                result.setdefault("extractor", extractor_name)
                return result
        except Exception as error:
            errors.append(f"{extractor_name}: {error}")

    detail = " | ".join(errors) if errors else "no extractor produced a stream URL"
    print(f"Error extracting stream: {detail}")
    raise Exception(f"Stream extraction failed: {detail}")


def extract_playlist_streams(url: str) -> Dict:
    """Extract all streams from a playlist (for TV series episodes)."""
    try:
        with yt_dlp.YoutubeDL(YTDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info or info.get("_type") != "playlist":
            raise Exception("URL is not a playlist")

        entries = info.get("entries", [])
        episodes = []
        for entry in entries:
            if not entry:
                continue
            stream_url = entry.get("url")
            if not stream_url:
                continue
            episodes.append(
                {
                    "title": entry.get("title", f"Episode {len(episodes) + 1}"),
                    "streamUrl": stream_url,
                    "streamFormat": _stream_format(stream_url),
                    "duration": entry.get("duration"),
                }
            )

        return {
            "title": info.get("title", "Playlist"),
            "description": info.get("description", ""),
            "episodes": episodes,
        }
    except Exception as error:
        print(f"Error extracting playlist: {error}")
        raise Exception(f"Playlist extraction failed: {error}")


def _extract_with_python_ytdlp(url: str, http_headers: Dict[str, str]) -> Dict:
    options = YTDL_OPTS.copy()
    if http_headers:
        options["http_headers"] = http_headers.copy()

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

    return _build_stream_result(info, http_headers, "yt-dlp-python")


def _extract_with_cli_ytdlp(url: str, http_headers: Dict[str, str]) -> Dict:
    executable = _find_executable(_yt_dlp_candidates())
    if not executable:
        raise RuntimeError("yt-dlp executable was not found")

    command = [
        executable,
        "--dump-single-json",
        "--no-warnings",
        "--skip-download",
        "--format",
        "best",
    ]
    for key, value in http_headers.items():
        command.extend(["--add-header", f"{key}:{value}"])

    cookies_from_browser = os.getenv("YTDLP_COOKIES_FROM_BROWSER", "").strip()
    if cookies_from_browser:
        command.extend(["--cookies-from-browser", cookies_from_browser])

    command.append(url)
    completed = subprocess.run(command, capture_output=True, text=True, timeout=60, check=True)
    info = json.loads(completed.stdout)
    return _build_stream_result(info, http_headers, "yt-dlp-cli")


def _extract_with_streamlink(url: str, http_headers: Dict[str, str]) -> Dict:
    executable = _find_executable(_streamlink_candidates())
    if not executable:
        raise RuntimeError("streamlink executable was not found")

    command = [executable]
    for key, value in http_headers.items():
        command.extend(["--http-header", f"{key}={value}"])
    command.extend(["--stream-url", url, "best"])

    completed = subprocess.run(command, capture_output=True, text=True, timeout=60, check=True)
    stream_url = completed.stdout.strip()
    if not stream_url:
        raise RuntimeError("streamlink did not return a stream URL")

    return {
        "title": "Video",
        "streamUrl": stream_url,
        "streamFormat": _stream_format(stream_url),
        "duration": None,
        "thumbnail": None,
        "description": "",
        "httpHeaders": http_headers,
        "extractor": "streamlink",
    }


def _build_stream_result(info: Dict, http_headers: Dict[str, str], extractor: str) -> Dict:
    if not info:
        raise RuntimeError("Unable to extract video information")

    stream_url = info.get("url")
    if not stream_url:
        stream_url = _pick_best_format_url(info.get("formats", []))
    if not stream_url:
        raise RuntimeError("No stream URL found")

    return {
        "title": info.get("title", "Video"),
        "streamUrl": stream_url,
        "streamFormat": _stream_format(stream_url),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "description": info.get("description", ""),
        "httpHeaders": http_headers,
        "extractor": extractor,
    }


def _pick_best_format_url(formats: List[Dict]) -> Optional[str]:
    if not formats:
        return None

    def score(format_item: Dict) -> tuple:
        url = format_item.get("url", "")
        protocol = str(format_item.get("protocol", ""))
        ext = str(format_item.get("ext", ""))
        hls_priority = 1 if ("m3u8" in url or "m3u8" in protocol or ext == "m3u8") else 0
        height = format_item.get("height") or 0
        tbr = format_item.get("tbr") or 0
        filesize = format_item.get("filesize") or 0
        return (hls_priority, height, tbr, filesize)

    best_format = max(formats, key=score)
    return best_format.get("url")


def _stream_format(url: str) -> str:
    lowered = url.lower()
    if ".m3u8" in lowered:
        return "hls"
    if ".mp4" in lowered:
        return "mp4"
    return "hls" if "manifest" in lowered else "mp4"


def _clean_headers(http_headers: Optional[Dict[str, str]]) -> Dict[str, str]:
    if not http_headers:
        return {}
    return {str(key): str(value) for key, value in http_headers.items() if value not in (None, "")}


def _find_executable(candidates: List[str]) -> Optional[str]:
    for candidate in candidates:
        if not candidate:
            continue
        if os.path.isfile(candidate):
            return candidate
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def _yt_dlp_candidates() -> List[str]:
    repo_root = Path(__file__).resolve().parents[1]
    return [
        os.getenv("YTDLP_PATH", "").strip(),
        str(repo_root / ".venv" / "Scripts" / "yt-dlp.exe"),
        "yt-dlp",
    ]


def _streamlink_candidates() -> List[str]:
    home = Path.home()
    return [
        os.getenv("STREAMLINK_PATH", "").strip(),
        str(home / "AppData" / "Local" / "Programs" / "Streamlink" / "bin" / "streamlink.exe"),
        "streamlink",
    ]
