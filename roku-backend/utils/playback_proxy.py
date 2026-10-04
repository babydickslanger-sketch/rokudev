import base64
import binascii
import json
import logging
import os
import posixpath
import re
import shutil
import subprocess
import threading
import time
import uuid
from typing import Callable, Dict, Optional
from urllib.parse import urlencode, urljoin, urlparse

import requests
from fastapi import HTTPException, Request
from fastapi.responses import Response

logger = logging.getLogger(__name__)


PLAYBACK_SESSION_TTL_SECONDS = int(os.getenv("PLAYBACK_SESSION_TTL_SECONDS", "3600"))
PLAYBACK_PROXY_TIMEOUT_SECONDS = int(os.getenv("PLAYBACK_PROXY_TIMEOUT_SECONDS", "120"))
MAX_PLAYBACK_SESSIONS = int(os.getenv("MAX_PLAYBACK_SESSIONS", "200"))

_HLS_CONTENT_TYPES = (
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "audio/mpegurl",
    "audio/x-mpegurl",
)
_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}
_PASSTHROUGH_RESPONSE_HEADERS = {
    "accept-ranges",
    "content-range",
    "content-type",
    "content-length",
    "etag",
    "last-modified",
}
_URI_ATTR_PATTERN = re.compile(r'URI="([^"]+)"')
_PLAYBACK_SESSIONS: Dict[str, Dict] = {}
_PLAYBACK_SESSIONS_LOCK = threading.RLock()
_HLS_ATTRIBUTE_PATTERN = re.compile(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)')
_FBSTREAM_MAX_VARIANT_HEIGHT = 486
_FFPROBE_STREAM_FIELDS = (
    "codec_type,codec_name,profile,codec_tag_string,width,height,pix_fmt,level,"
    "sample_rate,channels,channel_layout"
)


def register_playback_session(request: Request, source_page_url: str, stream_info: Dict) -> Dict:
    if not stream_info.get("streamUrl"):
        raise ValueError("stream_info must include streamUrl")

    direct_stream_url = stream_info["streamUrl"]
    http_headers = _sanitize_upstream_headers(stream_info.get("httpHeaders") or {})
    if source_page_url and "Referer" not in http_headers:
        http_headers["Referer"] = source_page_url

    playback_id = uuid.uuid4().hex
    session = {
        "playbackId": playback_id,
        "createdAt": time.time(),
        "updatedAt": time.time(),
        "sourcePageUrl": source_page_url,
        "directStreamUrl": direct_stream_url,
        "streamFormat": stream_info.get("streamFormat") or "hls",
        "title": stream_info.get("title") or "FBStream event",
        "httpHeaders": http_headers,
        "extractor": stream_info.get("extractor") or "unknown",
        "hlsResources": {},
    }

    with _PLAYBACK_SESSIONS_LOCK:
        _prune_expired_sessions_locked()
        if len(_PLAYBACK_SESSIONS) >= MAX_PLAYBACK_SESSIONS:
            _drop_oldest_session_locked()
        _PLAYBACK_SESSIONS[playback_id] = session

    proxied_url = build_proxy_url(request, playback_id, direct_stream_url, session=session, include_target_url=True)
    logger.info(
        "Registered playback session playback_id=%s extractor=%s format=%s direct=%s proxied=%s header_keys=%s",
        playback_id,
        stream_info.get("extractor") or "unknown",
        stream_info.get("streamFormat") or "hls",
        _safe_resource_url(direct_stream_url),
        _safe_resource_url(proxied_url),
        sorted(http_headers.keys()),
    )
    payload = dict(stream_info)
    payload["playbackId"] = playback_id
    payload["playbackUrl"] = proxied_url
    payload["directStreamUrl"] = direct_stream_url
    payload["streamUrl"] = proxied_url
    payload["proxyMode"] = "hls-rewrite" if _looks_like_hls(direct_stream_url, None, None) else "passthrough"
    return payload


def proxy_playback_request(
    request: Request,
    playback_id: str,
    target_url: Optional[str],
    refresh_resolver: Optional[Callable[[str], Dict]] = None,
    context_token: Optional[str] = None,
) -> Response:
    session = _get_or_restore_session(playback_id, context_token)
    if not session:
        raise HTTPException(status_code=404, detail="Playback session not found or expired")

    _touch_session(playback_id)
    session = _get_session(playback_id) or session
    upstream_url = target_url or session["directStreamUrl"]
    resource = _describe_resource(session, upstream_url)
    request_range = request.headers.get("range")
    logger.info(
        "Playback trace request playback_id=%s kind=%s url=%s range=%s",
        playback_id,
        resource["kind"],
        _safe_resource_url(upstream_url),
        request_range or "none",
    )
    fetch_started = time.monotonic()
    try:
        upstream_response = _fetch_upstream_resource(request, session, upstream_url)
    except requests.RequestException as error:
        logger.warning(
            "Playback trace upstream request failed playback_id=%s kind=%s url=%s elapsed_ms=%s error_type=%s error=%s",
            playback_id,
            resource["kind"],
            _safe_resource_url(upstream_url),
            round((time.monotonic() - fetch_started) * 1000),
            type(error).__name__,
            _safe_exception_message(error),
        )
        raise

    if upstream_response.status_code in {401, 403, 404, 410} and refresh_resolver and session.get("sourcePageUrl"):
        logger.warning(
            "Playback trace source refresh playback_id=%s status=%s kind=%s url=%s",
            playback_id,
            upstream_response.status_code,
            resource["kind"],
            _safe_resource_url(upstream_url),
        )
        refresh_started = time.monotonic()
        refreshed = refresh_resolver(session["sourcePageUrl"])
        logger.info(
            "Playback trace source refresh complete playback_id=%s elapsed_ms=%s extractor=%s",
            playback_id,
            round((time.monotonic() - refresh_started) * 1000),
            refreshed.get("extractor", "unknown"),
        )
        _update_session(playback_id, refreshed)
        session = _PLAYBACK_SESSIONS[playback_id]
        retry_url = target_url
        if not retry_url or retry_url == upstream_url:
            retry_url = session["directStreamUrl"]
        retry_started = time.monotonic()
        resource = _describe_resource(session, retry_url)
        try:
            upstream_response = _fetch_upstream_resource(request, session, retry_url)
        except requests.RequestException as error:
            logger.warning(
                "Playback trace retry failed playback_id=%s kind=%s url=%s elapsed_ms=%s error_type=%s error=%s",
                playback_id,
                resource["kind"],
                _safe_resource_url(retry_url),
                round((time.monotonic() - retry_started) * 1000),
                type(error).__name__,
                _safe_exception_message(error),
            )
            raise
        fetch_started = retry_started

    logger.info(
        "Playback trace upstream response playback_id=%s kind=%s url=%s status=%s content_type=%s content_range=%s accept_ranges=%s bytes=%s elapsed_ms=%s final_url=%s",
        playback_id,
        resource["kind"],
        _safe_resource_url(upstream_url),
        upstream_response.status_code,
        upstream_response.headers.get("Content-Type"),
        upstream_response.headers.get("Content-Range", "none"),
        upstream_response.headers.get("Accept-Ranges", "none"),
        len(upstream_response.content or b""),
        round((time.monotonic() - fetch_started) * 1000),
        _safe_resource_url(getattr(upstream_response, "url", upstream_url)),
    )

    if upstream_response.status_code >= 400:
        logger.error(
            "Playback trace rejected upstream response playback_id=%s kind=%s status=%s body_preview=%s",
            playback_id,
            resource["kind"],
            upstream_response.status_code,
            _safe_response_preview(upstream_response),
        )
        raise HTTPException(
            status_code=502,
            detail=f"Upstream stream request failed with HTTP {upstream_response.status_code}",
        )

    content_type = upstream_response.headers.get("Content-Type", "application/octet-stream")
    payload = upstream_response.content

    if _looks_like_hls(upstream_url, content_type, payload):
        text = payload.decode(upstream_response.encoding or "utf-8", errors="replace")
        _log_hls_playlist_diagnostics(playback_id, text, upstream_url, session)
        if _is_fbstream_session(session):
            text, selected_variant = _select_hls_variant(text, _FBSTREAM_MAX_VARIANT_HEIGHT)
            if selected_variant:
                logger.info(
                    "HLS Roku-compatible variant selected playback_id=%s resolution=%s bandwidth=%s codecs=%s max_height=%s",
                    playback_id,
                    selected_variant["resolution"],
                    selected_variant["bandwidth"],
                    selected_variant["codecs"],
                    _FBSTREAM_MAX_VARIANT_HEIGHT,
                )
        rewritten = rewrite_m3u8_playlist(
            text,
            upstream_url,
            lambda resolved_url: build_proxy_url(request, playback_id, resolved_url, session=session, include_target_url=True),
        )
        headers = {
            "Cache-Control": "no-store",
            "Access-Control-Allow-Origin": "*",
        }
        logger.info(
            "Proxy rewrote HLS playlist playback_id=%s upstream=%s",
            playback_id,
            _safe_resource_url(upstream_url),
        )
        return Response(content=rewritten, media_type="application/vnd.apple.mpegurl", headers=headers)

    if resource["kind"] == "key":
        _log_hls_key_diagnostics(playback_id, upstream_url, payload, resource)

    if _is_transport_stream(upstream_url, content_type):
        encryption = resource.get("encryption") or {}
        _log_transport_stream_diagnostics(playback_id, payload, encryption)
        encryption_method = encryption.get("METHOD", encryption.get("method", ""))
        if encryption_method.upper().startswith("AES"):
            logger.info(
                "MPEG-TS codec probe skipped playback_id=%s reason=encrypted_segment method=%s",
                playback_id,
                encryption_method,
            )
        elif _claim_codec_probe(playback_id):
            _log_transport_stream_codecs(playback_id, payload)

    headers = {
        key: value
        for key, value in upstream_response.headers.items()
        if key.lower() in _PASSTHROUGH_RESPONSE_HEADERS
    }
    headers["Cache-Control"] = "no-store"
    headers["Access-Control-Allow-Origin"] = "*"
    media_type = headers.pop("Content-Type", None) or content_type or "application/octet-stream"
    logger.info(
        "Playback trace response ready playback_id=%s kind=%s status=%s media_type=%s bytes=%s",
        playback_id,
        resource["kind"],
        upstream_response.status_code,
        media_type,
        len(payload),
    )
    return Response(content=payload, media_type=media_type, headers=headers)


def build_proxy_url(
    request: Request,
    playback_id: str,
    target_url: str,
    session: Optional[Dict] = None,
    include_target_url: bool = True,
) -> str:
    resource_name = _proxy_resource_name(target_url)
    base_url = str(request.url_for("fbstream_proxy_named", playback_id=playback_id, resource_name=resource_name))
    query_params = {}
    if include_target_url:
        query_params["url"] = target_url
    context_token = _encode_session_context(session) if session else None
    if context_token:
        query_params["ctx"] = context_token
    if not query_params:
        return base_url
    return base_url + "?" + urlencode(query_params)


def _proxy_resource_name(target_url: str) -> str:
    parsed = urlparse(target_url)
    candidate = posixpath.basename(parsed.path) or "stream"
    if "." not in candidate:
        if "m3u8" in target_url.lower():
            candidate = candidate + ".m3u8"
        elif target_url.lower().endswith(".ts") or ".ts?" in target_url.lower():
            candidate = candidate + ".ts"
        else:
            candidate = candidate + ".bin"
    return candidate


def rewrite_m3u8_playlist(content: str, base_url: str, proxy_url_builder: Callable[[str], str]) -> str:
    rewritten_lines = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            rewritten_lines.append(line)
            continue

        if stripped.startswith("#"):
            rewritten_lines.append(_rewrite_uri_attributes(line, base_url, proxy_url_builder))
            continue

        rewritten_lines.append(proxy_url_builder(urljoin(base_url, stripped)))

    return "\n".join(rewritten_lines)


def _is_fbstream_session(session: Dict) -> bool:
    return (urlparse(session.get("sourcePageUrl") or "").hostname or "").lower() in {
        "fbstream.is",
        "www.fbstream.is",
    }


def _select_hls_variant(content: str, max_height: int) -> tuple[str, Optional[Dict[str, str]]]:
    lines = content.splitlines()
    variants = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line.startswith("#EXT-X-STREAM-INF:"):
            index += 1
            continue

        attributes = _parse_hls_attributes(line.partition(":")[2])
        uri_index = index + 1
        while uri_index < len(lines) and (not lines[uri_index].strip() or lines[uri_index].lstrip().startswith("#")):
            uri_index += 1
        resolution = re.fullmatch(r"(\d+)x(\d+)", attributes.get("RESOLUTION", ""))
        if uri_index < len(lines) and resolution and int(resolution.group(2)) <= max_height:
            variants.append({
                "start": index,
                "end": uri_index,
                "height": int(resolution.group(2)),
                "width": int(resolution.group(1)),
                "bandwidth": int(attributes.get("AVERAGE-BANDWIDTH") or attributes.get("BANDWIDTH") or "0"),
                "codecs": attributes.get("CODECS", "unspecified"),
            })
        index = uri_index + 1

    if not variants:
        return content, None

    selected = max(variants, key=lambda variant: (variant["height"], variant["bandwidth"]))
    selected_lines = []
    index = 0
    while index < len(lines):
        if lines[index].strip().startswith("#EXT-X-STREAM-INF:"):
            uri_index = index + 1
            while uri_index < len(lines) and (not lines[uri_index].strip() or lines[uri_index].lstrip().startswith("#")):
                uri_index += 1
            if index == selected["start"]:
                selected_lines.extend(lines[index:uri_index + 1])
            index = uri_index + 1
            continue
        selected_lines.append(lines[index])
        index += 1

    return "\n".join(selected_lines), {
        "resolution": f'{selected["width"]}x{selected["height"]}',
        "bandwidth": str(selected["bandwidth"]),
        "codecs": selected["codecs"],
    }


def _log_hls_playlist_diagnostics(
    playback_id: str,
    playlist: str,
    base_url: Optional[str] = None,
    session: Optional[Dict] = None,
) -> None:
    summary = {
        "version": None,
        "target_duration": None,
        "playlist_type": None,
        "media_sequence": None,
        "endlist": False,
        "independent_segments": False,
        "stream_variants": [],
        "keys": [],
        "maps": 0,
        "media_renditions": [],
        "segment_count": 0,
        "segment_duration_seconds": [],
    }
    pending_resource_kind = None
    active_encryption = {"method": "NONE"}
    resources = []
    for line in playlist.splitlines():
        tag = line.strip()
        if not tag:
            continue
        if tag.startswith("#EXT-X-VERSION:"):
            summary["version"] = tag.partition(":")[2]
        elif tag.startswith("#EXT-X-TARGETDURATION:"):
            summary["target_duration"] = tag.partition(":")[2]
        elif tag.startswith("#EXT-X-PLAYLIST-TYPE:"):
            summary["playlist_type"] = tag.partition(":")[2]
        elif tag.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            summary["media_sequence"] = tag.partition(":")[2]
        elif tag == "#EXT-X-ENDLIST":
            summary["endlist"] = True
        elif tag == "#EXT-X-INDEPENDENT-SEGMENTS":
            summary["independent_segments"] = True
        elif tag.startswith("#EXT-X-STREAM-INF:"):
            attributes = _parse_hls_attributes(tag.partition(":")[2])
            summary["stream_variants"].append({
                key: attributes[key]
                for key in ("BANDWIDTH", "AVERAGE-BANDWIDTH", "RESOLUTION", "FRAME-RATE", "CODECS")
                if key in attributes
            })
            pending_resource_kind = "variant_playlist"
        elif tag.startswith(("#EXT-X-KEY:", "#EXT-X-SESSION-KEY:")):
            attributes = _parse_hls_attributes(tag.partition(":")[2])
            encryption = {
                key: attributes[key]
                for key in ("METHOD", "KEYFORMAT", "KEYFORMATVERSIONS", "IV")
                if key in attributes
            }
            summary["keys"].append({key: value for key, value in encryption.items() if key != "IV"})
            active_encryption = encryption
            if attributes.get("URI"):
                resources.append((urljoin(base_url or "", attributes["URI"]), {
                    "kind": "key",
                    "method": attributes.get("METHOD", "unknown"),
                    "keyformat": attributes.get("KEYFORMAT", "identity"),
                }))
        elif tag.startswith("#EXT-X-MAP:"):
            summary["maps"] += 1
            attributes = _parse_hls_attributes(tag.partition(":")[2])
            if attributes.get("URI"):
                resources.append((urljoin(base_url or "", attributes["URI"]), {"kind": "init_segment"}))
        elif tag.startswith("#EXT-X-MEDIA:"):
            attributes = _parse_hls_attributes(tag.partition(":")[2])
            summary["media_renditions"].append({
                key: attributes[key]
                for key in ("TYPE", "GROUP-ID", "NAME", "LANGUAGE", "DEFAULT", "AUTOSELECT")
                if key in attributes
            })
            if attributes.get("URI"):
                resources.append((urljoin(base_url or "", attributes["URI"]), {"kind": "rendition_playlist"}))
        elif tag.startswith("#EXT-X-I-FRAME-STREAM-INF:"):
            attributes = _parse_hls_attributes(tag.partition(":")[2])
            if attributes.get("URI"):
                resources.append((urljoin(base_url or "", attributes["URI"]), {"kind": "iframe_playlist"}))
        elif tag.startswith("#EXTINF:"):
            duration = tag.partition(":")[2].partition(",")[0]
            try:
                summary["segment_duration_seconds"].append(float(duration))
            except ValueError:
                pass
            summary["segment_count"] += 1
            pending_resource_kind = "segment"
        elif tag.startswith("#EXT-X-BYTERANGE:"):
            summary.setdefault("byte_ranges", []).append(tag.partition(":")[2])
        elif tag.startswith("#EXT-X-DISCONTINUITY"):
            summary.setdefault("discontinuities", 0)
            summary["discontinuities"] += 1
        elif tag.startswith("#EXT-X-PROGRAM-DATE-TIME:"):
            summary.setdefault("program_date_time", tag.partition(":")[2])
        elif tag.startswith("#"):
            continue
        else:
            kind = pending_resource_kind or _resource_kind_from_path(tag)
            details = {"kind": kind}
            if kind == "segment":
                details["encryption"] = dict(active_encryption)
            resources.append((urljoin(base_url or "", tag), details))
            pending_resource_kind = None

    if summary["segment_duration_seconds"]:
        summary["segment_duration_range_seconds"] = [
            min(summary["segment_duration_seconds"]),
            max(summary["segment_duration_seconds"]),
        ]
    summary.pop("segment_duration_seconds", None)
    if session is not None and resources:
        _remember_hls_resources(playback_id, session, resources)

    logger.info("HLS playlist diagnostics playback_id=%s summary=%s", playback_id, summary)


def _remember_hls_resources(playback_id: str, session: Dict, resources) -> None:
    resource_map = session.setdefault("hlsResources", {})
    resource_map.update(resources)
    with _PLAYBACK_SESSIONS_LOCK:
        stored_session = _PLAYBACK_SESSIONS.get(playback_id)
        if stored_session is not None:
            stored_session.setdefault("hlsResources", {}).update(resources)


def _resource_kind_from_path(url: str) -> str:
    path = urlparse(url).path.lower()
    if path.endswith(".m3u8"):
        return "playlist"
    if path.endswith((".ts", ".m4s", ".mp4")):
        return "segment"
    return "resource"


def _describe_resource(session: Dict, url: str) -> Dict:
    resource = dict(session.get("hlsResources", {}).get(url) or {})
    resource.setdefault("kind", _resource_kind_from_path(url))
    return resource


def _safe_resource_url(url: Optional[str]) -> str:
    if not url:
        return "none"
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    safe_url = f"{parsed.scheme}://{host}{parsed.path}" if parsed.scheme else parsed.path
    return safe_url + ("?<redacted>" if parsed.query else "")


def _safe_response_preview(response: requests.Response) -> str:
    content_type = response.headers.get("Content-Type", "").lower()
    if not any(kind in content_type for kind in ("text/", "json", "xml", "html")):
        return f"<non-text response bytes={len(response.content or b'')}>"
    preview = (response.text or "")[:300]
    preview = re.sub(r"https?://[^\s\"'<>]+", lambda match: _safe_resource_url(match.group(0)), preview)
    preview = re.sub(
        r"(?i)\b(token|key|signature|sig|ssid|session_id|csrf|authorization|expires)=([^&\s,;\"']+)",
        r"\1=<redacted>",
        preview,
    )
    return preview.replace("\r", " ").replace("\n", " ")


def _safe_exception_message(error: Exception) -> str:
    message = re.sub(r"https?://[^\s\"'<>]+", lambda match: _safe_resource_url(match.group(0)), str(error))
    message = re.sub(
        r"(?i)\b(token|key|signature|sig|ssid|session_id|csrf|authorization|expires)=([^&\s,;\"']+)",
        r"\1=<redacted>",
        message,
    )
    return message[:300]


def _log_hls_key_diagnostics(playback_id: str, url: str, payload: bytes, resource: Dict) -> None:
    expected_bytes = 16 if resource.get("method") == "AES-128" else None
    logger.info(
        "HLS key diagnostics playback_id=%s url=%s method=%s keyformat=%s bytes=%s expected_bytes=%s valid_length=%s",
        playback_id,
        _safe_resource_url(url),
        resource.get("method", "unknown"),
        resource.get("keyformat", "unknown"),
        len(payload),
        expected_bytes if expected_bytes is not None else "unknown",
        len(payload) == expected_bytes if expected_bytes is not None else "unknown",
    )


def _log_transport_stream_diagnostics(playback_id: str, media: bytes, encryption: Dict) -> None:
    packet_size = 188
    sync_offsets = [offset for offset in range(min(packet_size * 5, len(media))) if offset % packet_size == 0]
    sync_valid = bool(media) and all(media[offset] == 0x47 for offset in sync_offsets)
    method = encryption.get("METHOD", "unknown")
    logger.info(
        "MPEG-TS segment diagnostics playback_id=%s bytes=%s sync_byte_valid=%s sync_packets_checked=%s encrypted=%s encryption_method=%s iv_declared=%s",
        playback_id,
        len(media),
        sync_valid,
        len(sync_offsets),
        method.upper() not in {"NONE", "UNKNOWN"},
        method,
        bool(encryption.get("IV", encryption.get("iv"))),
    )


def _parse_hls_attributes(value: str) -> Dict[str, str]:
    return {
        key: raw_value[1:-1] if raw_value.startswith('"') and raw_value.endswith('"') else raw_value
        for key, raw_value in _HLS_ATTRIBUTE_PATTERN.findall(value)
    }


def _is_transport_stream(url: str, content_type: str) -> bool:
    return "mp2t" in content_type.lower() or urlparse(url).path.lower().endswith(".ts")


def _claim_codec_probe(playback_id: str) -> bool:
    with _PLAYBACK_SESSIONS_LOCK:
        session = _PLAYBACK_SESSIONS.get(playback_id)
        if not session or session.get("codecProbeAttempted"):
            return False
        session["codecProbeAttempted"] = True
        return True


def _log_transport_stream_codecs(playback_id: str, media: bytes) -> None:
    ffprobe_path = shutil.which("ffprobe")
    if not ffprobe_path:
        logger.warning("MPEG-TS codec diagnostics unavailable playback_id=%s reason=ffprobe_not_installed", playback_id)
        return

    try:
        result = subprocess.run(
            [
                ffprobe_path,
                "-v", "error",
                "-show_entries", f"stream={_FFPROBE_STREAM_FIELDS}",
                "-of", "json",
                "-i", "pipe:0",
            ],
            input=media,
            capture_output=True,
            timeout=8,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning("MPEG-TS codec probe timed out playback_id=%s timeout_seconds=8", playback_id)
        return
    except OSError as error:
        logger.warning("MPEG-TS codec probe could not run playback_id=%s error=%s", playback_id, error)
        return

    if result.returncode:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()[-1000:]
        logger.warning(
            "MPEG-TS codec probe failed playback_id=%s exit_code=%s stderr=%s",
            playback_id,
            result.returncode,
            stderr,
        )
        return

    try:
        streams = json.loads(result.stdout.decode("utf-8")).get("streams", [])
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("MPEG-TS codec probe returned invalid JSON playback_id=%s", playback_id)
        return
    logger.info("MPEG-TS codec diagnostics playback_id=%s streams=%s", playback_id, streams)


def _rewrite_uri_attributes(line: str, base_url: str, proxy_url_builder: Callable[[str], str]) -> str:
    def replace_uri(match: re.Match) -> str:
        resolved_url = urljoin(base_url, match.group(1))
        return f'URI="{proxy_url_builder(resolved_url)}"'

    return _URI_ATTR_PATTERN.sub(replace_uri, line)


def _fetch_upstream_resource(request: Request, session: Dict, upstream_url: str) -> requests.Response:
    headers = _sanitize_upstream_headers(session.get("httpHeaders") or {})
    request_range = request.headers.get("range")
    if request_range:
        headers["Range"] = request_range

    response = requests.get(
        upstream_url,
        headers=headers,
        timeout=PLAYBACK_PROXY_TIMEOUT_SECONDS,
        allow_redirects=True,
    )
    return response


def _sanitize_upstream_headers(headers: Dict[str, str]) -> Dict[str, str]:
    sanitized = {}
    for key, value in headers.items():
        if value is None:
            continue
        normalized_key = str(key).strip()
        normalized_value = str(value).strip()
        if not normalized_key or not normalized_value:
            continue
        if normalized_key.lower() in _HOP_BY_HOP_HEADERS:
            continue
        sanitized[normalized_key] = normalized_value
    return sanitized


def _looks_like_hls(url: str, content_type: Optional[str], payload: Optional[bytes]) -> bool:
    if url.lower().split("?", 1)[0].endswith(".m3u8"):
        return True
    if content_type:
        lowered = content_type.lower()
        if any(value in lowered for value in _HLS_CONTENT_TYPES):
            return True
    if payload:
        return payload[:64].lstrip().startswith(b"#EXTM3U")
    return False


def _touch_session(playback_id: str) -> None:
    with _PLAYBACK_SESSIONS_LOCK:
        if playback_id in _PLAYBACK_SESSIONS:
            _PLAYBACK_SESSIONS[playback_id]["updatedAt"] = time.time()


def _update_session(playback_id: str, stream_info: Dict) -> None:
    with _PLAYBACK_SESSIONS_LOCK:
        session = _PLAYBACK_SESSIONS.get(playback_id)
        if not session:
            return

        session["updatedAt"] = time.time()
        session["directStreamUrl"] = stream_info.get("streamUrl", session["directStreamUrl"])
        session["streamFormat"] = stream_info.get("streamFormat", session["streamFormat"])
        session["title"] = stream_info.get("title", session["title"])
        session["extractor"] = stream_info.get("extractor", session["extractor"])

        refreshed_headers = _sanitize_upstream_headers(stream_info.get("httpHeaders") or {})
        if session.get("sourcePageUrl") and "Referer" not in refreshed_headers:
            refreshed_headers["Referer"] = session["sourcePageUrl"]
        session["httpHeaders"] = refreshed_headers


def _get_session(playback_id: str) -> Optional[Dict]:
    with _PLAYBACK_SESSIONS_LOCK:
        session = _PLAYBACK_SESSIONS.get(playback_id)
        return dict(session) if session else None


def _get_or_restore_session(playback_id: str, context_token: Optional[str]) -> Optional[Dict]:
    session = _get_session(playback_id)
    if session:
        return session
    if not context_token:
        return None
    restored = _decode_session_context(context_token)
    if not restored:
        return None

    restored_session = {
        "playbackId": playback_id,
        "createdAt": time.time(),
        "updatedAt": time.time(),
        "sourcePageUrl": restored.get("sourcePageUrl") or "",
        "directStreamUrl": restored.get("directStreamUrl") or "",
        "streamFormat": restored.get("streamFormat") or "hls",
        "title": restored.get("title") or "FBStream event",
        "httpHeaders": _sanitize_upstream_headers(restored.get("httpHeaders") or {}),
        "extractor": restored.get("extractor") or "unknown",
        "hlsResources": {},
    }
    if not restored_session["directStreamUrl"]:
        return None

    with _PLAYBACK_SESSIONS_LOCK:
        _prune_expired_sessions_locked()
        if len(_PLAYBACK_SESSIONS) >= MAX_PLAYBACK_SESSIONS:
            _drop_oldest_session_locked()
        existing = _PLAYBACK_SESSIONS.get(playback_id)
        if existing:
            return dict(existing)
        _PLAYBACK_SESSIONS[playback_id] = restored_session

    logger.warning("Restored playback session from URL context playback_id=%s", playback_id)
    return dict(restored_session)


def _encode_session_context(session: Optional[Dict]) -> Optional[str]:
    if not session:
        return None
    payload = {
        "sourcePageUrl": session.get("sourcePageUrl") or "",
        "directStreamUrl": session.get("directStreamUrl") or "",
        "streamFormat": session.get("streamFormat") or "hls",
        "title": session.get("title") or "FBStream event",
        "httpHeaders": _sanitize_upstream_headers(session.get("httpHeaders") or {}),
        "extractor": session.get("extractor") or "unknown",
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def _decode_session_context(context_token: str) -> Optional[Dict]:
    try:
        padded = context_token + ("=" * (-len(context_token) % 4))
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(decoded.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, binascii.Error):
        logger.warning("Failed to decode playback context token")
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _prune_expired_sessions() -> None:
    with _PLAYBACK_SESSIONS_LOCK:
        _prune_expired_sessions_locked()


def _prune_expired_sessions_locked() -> None:
    cutoff = time.time() - PLAYBACK_SESSION_TTL_SECONDS
    expired_ids = [
        playback_id
        for playback_id, session in _PLAYBACK_SESSIONS.items()
        if session.get("updatedAt", session.get("createdAt", 0)) < cutoff
    ]
    for playback_id in expired_ids:
        _PLAYBACK_SESSIONS.pop(playback_id, None)


def _drop_oldest_session() -> None:
    with _PLAYBACK_SESSIONS_LOCK:
        _drop_oldest_session_locked()


def _drop_oldest_session_locked() -> None:
    if not _PLAYBACK_SESSIONS:
        return
    oldest_playback_id = min(
        _PLAYBACK_SESSIONS,
        key=lambda playback_id: _PLAYBACK_SESSIONS[playback_id].get("updatedAt", 0),
    )
    _PLAYBACK_SESSIONS.pop(oldest_playback_id, None)
