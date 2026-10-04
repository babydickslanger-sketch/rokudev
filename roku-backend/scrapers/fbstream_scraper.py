import base64
import html
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from utils.stream_extractor import extract_stream_url

logger = logging.getLogger(__name__)

FBSTREAM_BASE_URL = "https://fbstream.is"
FBSTREAM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/127.0 Safari/537.36",
    "Referer": f"{FBSTREAM_BASE_URL}/",
}
FBSTREAM_CATEGORIES = {
    "live-now": "LIVE NOW",
    "football": "FOOTBALL",
    "nfl": "NFL",
    "college-football": "COLLEGE FOOTBALL",
    "basketball": "BASKETBALL",
    "college-basketball": "COLLEGE BASKETBALL",
    "nba": "NBA",
    "hockey": "HOCKEY",
    "nhl": "NHL",
    "baseball": "BASEBALL",
    "mlb": "MLB",
    "tennis": "TENNIS",
    "motorsports": "MOTOR SPORTS",
    "f1": "F1",
    "motogp": "MOTOGP",
    "ufc": "UFC",
    "mma": "MMA",
    "boxing": "BOXING",
    "rugby": "RUGBY",
    "afl": "AFL",
    "darts": "DARTS",
    "golf": "GOLF",
}


def get_fbstream_catalog(category: str = "live-now") -> Dict:
    """Scrape event listings for one FBStream sports category."""
    category = category.strip().lower()
    if category not in FBSTREAM_CATEGORIES:
        raise ValueError(f"Invalid FBStream category: {category}")

    page_url = f"{FBSTREAM_BASE_URL}/stream/{category}"
    try:
        response = requests.get(
            page_url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        events = _extract_events(soup, page_url)
    except requests.RequestException as error:
        print(f"Error scraping FBStream category {category}: {error}")
        events = []

    return {
        "category": category,
        "categories": [{"title": _category_title(category), "slug": category, "items": events}],
    }


def _extract_events(soup: BeautifulSoup, page_url: str) -> List[Dict]:
    """Extract distinct event links while excluding the site's navigation links."""
    page_host = urlparse(FBSTREAM_BASE_URL).netloc
    events = []
    seen_urls = set()

    for anchor in soup.select("a[href]"):
        title = " ".join(anchor.get_text(" ", strip=True).split())
        target_url = urljoin(page_url, anchor.get("href", ""))
        parsed_url = urlparse(target_url)
        path = parsed_url.path.rstrip("/")

        if not title or len(title) < 5 or parsed_url.netloc != page_host:
            continue
        if path in {"", "/", "/privacy", "/dmca"}:
            continue
        if path.startswith("/stream/") and path.count("/") == 2:
            continue
        if target_url in seen_urls:
            continue

        image = anchor.find("img")
        image_url = ""
        if image:
            image_url = urljoin(page_url, image.get("src") or image.get("data-src") or "")

        events.append({
            "id": path.rsplit("/", 1)[-1],
            "title": title,
            "hdPosterUrl": image_url,
            "description": "Live sports event",
            "targetUrl": target_url,
        })
        seen_urls.add(target_url)

    return events


def _category_title(category: str) -> str:
    return FBSTREAM_CATEGORIES.get(category, category.replace("-", " ")).title()


def get_fbstream_stream(url: str) -> Dict:
    """Resolve direct media or a supported embedded player from an FBStream event page."""
    logger.info("Resolving FBStream event url=%s", url)
    parsed_url = urlparse(url)
    if parsed_url.scheme != "https" or parsed_url.hostname not in {"fbstream.is", "www.fbstream.is"}:
        raise ValueError("Stream URL must be an HTTPS FBStream event page")

    # Try streamlink first as it's designed for stream extraction
    try:
        logger.info("Trying streamlink for url=%s", url)
        stream_info = _extract_with_streamlink(url)
        if stream_info.get("streamUrl"):
            logger.info(
                "Streamlink resolved stream extractor=%s stream=%s",
                stream_info.get("extractor"),
                stream_info.get("streamUrl"),
            )
            return stream_info
    except Exception as error:
        logger.warning("Streamlink extraction failed url=%s error=%s", url, error)

    session = requests.Session()
    response = session.get(url, headers=FBSTREAM_HEADERS, timeout=20)
    response.raise_for_status()
    logger.info("Loaded FBStream event page url=%s final_url=%s status=%s", url, response.url, response.status_code)
    final_host = (urlparse(response.url).hostname or "").lower()
    if response.history and _is_tracking_host(final_host):
        raise RuntimeError(
            f"FBStream event redirected to tracking host {final_host}; no player page was returned"
        )
    soup = BeautifulSoup(response.text, "html.parser")
    page_title = _page_title(soup)

    direct_sources = _extract_direct_sources(soup, response.text, url)
    if direct_sources:
        logger.info("Found %s direct source candidates on event page", len(direct_sources))
    for source_url in direct_sources:
        logger.info("Using direct event-page source url=%s", source_url)
        return _direct_stream_info(page_title, source_url, url)

    embed_urls = _extract_embed_urls(soup, url)
    preferred_embed_url = _build_player_embed_url(response.text)
    if preferred_embed_url:
        embed_urls.insert(0, preferred_embed_url)
    logger.info(
        "FBStream embed candidates count=%s preferred=%s embeds=%s",
        len(embed_urls),
        preferred_embed_url,
        embed_urls[:5],
    )

    errors = []
    for embed_url in embed_urls:
        embed_host = urlparse(embed_url).hostname
        if embed_host in {"fbstream.is", "www.fbstream.is"}:
            continue

        embed_headers = {
            **FBSTREAM_HEADERS,
            "Referer": url,
            "Origin": f"{urlparse(url).scheme}://{urlparse(url).netloc}",
        }
        try:
            logger.info("Trying FBStream embed host=%s url=%s", embed_host, embed_url)
            embed_response = session.get(embed_url, headers=embed_headers, timeout=20)
            embed_response.raise_for_status()
            embed_soup = BeautifulSoup(embed_response.text, "html.parser")
            direct_sources = _extract_direct_sources(embed_soup, embed_response.text, embed_response.url)
            if direct_sources:
                logger.info("Found %s direct source candidates on embed host=%s", len(direct_sources), embed_host)
            for source_url in direct_sources:
                logger.info("Using direct embed source host=%s url=%s", embed_host, source_url)
                return _direct_stream_info(page_title, source_url, embed_response.url)

            source_lookup_url = _extract_source_lookup_url(embed_response.text, embed_response.url)
            if source_lookup_url:
                logger.info("Trying source lookup host=%s url=%s", embed_host, source_lookup_url)
                lookup_response = session.get(
                    source_lookup_url,
                    headers={
                        **embed_headers,
                        "Referer": embed_response.url,
                        "Accept": "*/*",
                        "Sec-Fetch-Dest": "empty",
                        "Sec-Fetch-Mode": "cors",
                        "Sec-Fetch-Site": "same-origin",
                    },
                    timeout=20,
                )
                if lookup_response.status_code == 403:
                    raise RuntimeError("The embedded player's source lookup was denied (HTTP 403)")
                lookup_response.raise_for_status()
                source_url = _find_media_url(lookup_response.text, lookup_response.url)
                if source_url:
                    logger.info("Using source lookup media host=%s url=%s", embed_host, source_url)
                    return _direct_stream_info(page_title, source_url, embed_response.url)

            stream_info = extract_stream_url(embed_url, http_headers=embed_headers)
            if stream_info.get("streamUrl"):
                stream_info.setdefault("title", page_title)
                logger.info(
                    "External extractor resolved host=%s extractor=%s stream=%s",
                    embed_host,
                    stream_info.get("extractor"),
                    stream_info.get("streamUrl"),
                )
                return stream_info
        except Exception as error:
            logger.warning("FBStream embed attempt failed host=%s error=%s", embed_host, error)
            errors.append(f"{embed_host}: {error}")

    try:
        logger.info("Falling back to Playwright for url=%s embed=%s", url, preferred_embed_url)
        stream_info = _extract_stream_with_playwright(url, page_title, preferred_embed_url)
        if stream_info.get("streamUrl"):
            logger.info(
                "Playwright resolved stream extractor=%s stream=%s",
                stream_info.get("extractor"),
                stream_info.get("streamUrl"),
            )
            return stream_info
    except Exception as error:
        logger.warning("Playwright fallback failed url=%s error=%s", url, error)
        errors.append(f"playwright: {error}")

    detail = "No direct HLS/MP4 source or supported external player was found"
    if errors:
        detail += "; extraction failures: " + " | ".join(errors[:4])
    logger.error("FBStream resolution failed url=%s detail=%s", url, detail)
    raise RuntimeError(detail)


def _extract_with_streamlink(url: str) -> Dict:
    """Use streamlink to extract stream URL from FBStream event page."""
    try:
        # Run streamlink to get available streams
        result = subprocess.run(
            ["streamlink", "--json", url],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        stream_data = json.loads(result.stdout)
        
        # Get the best quality stream
        if "streams" in stream_data and stream_data["streams"]:
            # Prefer HLS, then fallback to any available
            stream_types = ["hls", "http", "dash"]
            for stream_type in stream_types:
                if stream_type in stream_data["streams"]:
                    selected_stream = stream_data["streams"][stream_type]
                    break
            else:
                # Fallback to first available stream
                selected_stream = list(stream_data["streams"].values())[0]
            
            stream_url = selected_stream.get("url")
            if stream_url:
                return {
                    "title": "FBStream event",
                    "streamUrl": stream_url,
                    "streamFormat": "hls" if ".m3u8" in stream_url else "mp4",
                    "httpHeaders": {
                        "User-Agent": FBSTREAM_HEADERS["User-Agent"],
                        "Referer": url,
                    },
                    "extractor": "streamlink",
                }
        
        raise RuntimeError("Streamlink found no playable streams")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Streamlink timed out after 60 seconds")
    except subprocess.CalledProcessError as error:
        # Streamlink couldn't handle the URL directly, try as a passthrough
        # This will allow the normal scraping to continue
        raise RuntimeError(f"Streamlink doesn't support this URL directly: {error.stderr}")
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Streamlink returned invalid JSON: {result.stdout[:500]}")


def _extract_stream_with_playwright(url: str, page_title: str, embed_url: Optional[str] = None) -> Dict:
    worker_path = Path(__file__).resolve().parents[1] / "utils" / "fbstream_playwright_worker.py"
    command = [sys.executable, str(worker_path), url, page_title or "FBStream event", embed_url or ""]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=120, check=True)
    except subprocess.TimeoutExpired as error:
        stderr_tail = (error.stderr or "")[-4000:]
        raise RuntimeError(f"Playwright worker timed out after {error.timeout}s; stderr tail: {stderr_tail}") from error
    except subprocess.CalledProcessError as error:
        stderr_tail = (error.stderr or "")[-4000:]
        stdout_tail = (error.stdout or "")[-1000:]
        raise RuntimeError(
            f"Playwright worker failed with exit {error.returncode}; stderr tail: {stderr_tail}; stdout tail: {stdout_tail}"
        ) from error
    if completed.stderr.strip():
        logger.info("Playwright worker stderr tail: %s", completed.stderr.strip()[-4000:])
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Playwright worker returned invalid JSON: {completed.stdout[:500]}") from error


def _playwright_extract_frame_sources(page) -> List[str]:
    page_html = page.content()
    sources = _extract_direct_sources(BeautifulSoup(page_html, "html.parser"), page_html, page.url)
    if sources:
        return sources

    for frame in page.frames:
        try:
            frame_html = frame.content()
        except Exception:
            continue
        frame_sources = _extract_direct_sources(BeautifulSoup(frame_html, "html.parser"), frame_html, frame.url or page.url)
        if frame_sources:
            return frame_sources
    return []


def _click_playwright_iframe(page) -> None:
    iframe_locator = page.locator("iframe").first
    try:
        box = iframe_locator.bounding_box()
    except Exception:
        box = None
    if box:
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def _first_playwright_iframe_url(page) -> Optional[str]:
    for frame in page.frames:
        if frame.url and frame.url not in {"about:blank", page.url}:
            return frame.url
    return None


def _playwright_allowed_hosts(page_url: str, embed_url: Optional[str]) -> List[str]:
    hosts = [urlparse(page_url).hostname or ""]
    embed_host = urlparse(embed_url).hostname if embed_url else ""
    if embed_host:
        hosts.extend([embed_host, f"sts.{embed_host}"])
    hosts.extend([
        "seckyes.cc",
        "owlsig.cc",
        "nasig.live",
        "owledge.cc",
        "app.rmelvo.shop",
    ])
    return [host.lower() for host in hosts if host]


def _host_matches_allowed_list(host: str, allowed_hosts: List[str]) -> bool:
    return any(host == allowed_host or host.endswith("." + allowed_host) for allowed_host in allowed_hosts)


def _should_abort_playwright_request(request_url: str, resource_type: str, allowed_hosts: List[str]) -> bool:
    host = (urlparse(request_url).hostname or "").lower()
    if not host:
        return False
    if _is_tracking_host(host):
        return True
    if _host_matches_allowed_list(host, allowed_hosts):
        return False
    blocked_document_hosts = (
        "google.com",
        "www.google.com",
        "intellipopup.com",
        "llvpn.com",
        "googlesyndication.com",
        "googleadservices.com",
    )
    if host in blocked_document_hosts or any(host.endswith("." + blocked_host) for blocked_host in blocked_document_hosts):
        return True
    return resource_type in {"document", "script", "fetch", "xhr", "image", "media", "other"}


def _looks_like_stream_candidate(url: str) -> bool:
    lowered = url.lower()
    return (
        _is_direct_media_url(url)
        or ".m3u8" in lowered
        or ".mp4" in lowered
        or "/manifest.ts" in lowered
        or "/play.m3u8" in lowered
        or "/master.m3u8" in lowered
    )


def _playwright_candidate_sort_key(candidate: Dict) -> tuple:
    lowered = candidate["url"].lower()
    if "/play.m3u8" in lowered:
        priority = 0
    elif "/master.m3u8" in lowered:
        priority = 1
    elif lowered.endswith("/manifest.ts"):
        priority = 2
    else:
        stream_format = _stream_format(candidate["url"])
        priority = 0 if stream_format == "hls" else 3
    return (priority, len(candidate["url"]))


def _playwright_http_headers(context, stream_url: str, request_headers: Dict[str, str], referer: str) -> Dict[str, str]:
    interesting_headers = {"accept", "accept-language", "origin", "referer", "user-agent", "authorization"}
    headers = {
        key.title(): value
        for key, value in (request_headers or {}).items()
        if key.lower() in interesting_headers and value
    }
    if "Referer" not in headers and referer:
        headers["Referer"] = referer
    if "User-Agent" not in headers:
        headers["User-Agent"] = FBSTREAM_HEADERS["User-Agent"]

    cookies = context.cookies([stream_url])
    if cookies and "Cookie" not in headers:
        headers["Cookie"] = "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in cookies)
    return headers


def _build_player_embed_url(page_html: str) -> Optional[str]:
    config_match = re.search(r"(?:const|let|var)\s+siteConfig\s*=\s*", page_html)
    if not config_match:
        return None

    try:
        site_config, _ = json.JSONDecoder().raw_decode(page_html[config_match.end():])
    except (json.JSONDecodeError, TypeError):
        return None

    def match_value(name: str, pattern: str, default: str = "") -> str:
        match = re.search(pattern, page_html)
        return match.group(1) if match else default

    player_id = match_value("pid", r"\bconst\s+pid\s*=\s*(\d+)")
    zone_id = match_value("zmid", r"\bconst\s+zmid\s*=\s*[\"']([^\"']+)")
    embed_domain = match_value("edm", r"\bconst\s+edm\s*=\s*[\"']([^\"']+)")
    category = match_value("gameCat", r"\b(?:const|let|var)\s+gameCat\s*=\s*[\"']([^\"']*)", "sp")
    game_text = match_value("gameText", r"\b(?:const|let|var)\s+gameText\s*=\s*[\"']([^\"']*)")
    required = ("csrf", "csrf_ip", "sec_expires", "sec_hash")
    if not player_id or not zone_id or not embed_domain or any(not site_config.get(key) for key in required):
        return None
    query = urlencode({
        "pid": player_id,
        "gacat": game_text,
        "gatxt": category,
        "v": zone_id,
        "csrf": site_config["csrf"],
        "csrf_ip": site_config["csrf_ip"],
        "expires": site_config["sec_expires"],
        "sec_hash": site_config["sec_hash"],
    })
    return f"https://{embed_domain}/sd0embed/{category}?{query}"


def _extract_source_lookup_url(embed_html: str, embed_url: str) -> Optional[str]:
    match = re.search(r"\ba\s*=\s*D\(\s*[\"']([A-Za-z0-9+/=_-]+)[\"']\s*\)", embed_html)
    if not match:
        return None
    try:
        encoded_path = base64.b64decode(match.group(1) + "=" * (-len(match.group(1)) % 4)).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    return _normalize_player_url(encoded_path, embed_url)


def _find_media_url(response_text: str, response_url: str) -> Optional[str]:
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError:
        payload = response_text

    candidates = []
    if isinstance(payload, str):
        candidates.append(payload)
    elif isinstance(payload, dict):
        for key in ("streamUrl", "url", "file", "src", "source", "hls"):
            value = payload.get(key)
            if isinstance(value, str):
                candidates.append(value)
            elif isinstance(value, list):
                candidates.extend(item for item in value if isinstance(item, str))

    for value in candidates:
        candidate = _normalize_player_url(value, response_url)
        if candidate and _is_direct_media_url(candidate):
            return candidate

    soup = BeautifulSoup(response_text, "html.parser")
    sources = _extract_direct_sources(soup, response_text, response_url)
    return sources[0] if sources else None


def _direct_stream_info(title: str, source_url: str, referer: str) -> Dict:
    return {
        "title": title,
        "streamUrl": source_url,
        "streamFormat": _stream_format(source_url),
        "httpHeaders": {"Referer": referer},
        "extractor": "html",
    }


def _page_title(soup: BeautifulSoup) -> str:
    title_node = soup.find("title") or soup.find(["h1", "h2"])
    return title_node.get_text(" ", strip=True) if title_node else "FBStream event"


def _normalize_player_url(candidate: Optional[str], page_url: str) -> Optional[str]:
    if not candidate:
        return None
    candidate = html.unescape(candidate.strip()).replace("\\/", "/")
    candidate = candidate.replace("\\u0026", "&").replace("&amp;", "&")
    if candidate.startswith("//"):
        candidate = "https:" + candidate
    resolved = urljoin(page_url, candidate)
    if urlparse(resolved).scheme not in {"http", "https"}:
        return None
    return resolved


def _extract_direct_sources(soup: BeautifulSoup, page_html: str, page_url: str) -> List[str]:
    sources = []
    for node in soup.select("video[src], video source[src], source[src], video[data-src], source[data-src]"):
        candidate = _normalize_player_url(node.get("src") or node.get("data-src"), page_url)
        if candidate and _is_direct_media_url(candidate) and candidate not in sources:
            sources.append(candidate)

    normalized_html = html.unescape(page_html).replace("\\/", "/").replace("\\u0026", "&")
    media_pattern = re.compile(r"https?://[^\s\"'<>\\]+?\.(?:m3u8|mp4)(?:\?[^\s\"'<>\\]*)?", re.IGNORECASE)
    for match in media_pattern.findall(normalized_html):
        candidate = _normalize_player_url(match.rstrip(",);}"), page_url)
        if candidate and candidate not in sources:
            sources.append(candidate)

    return sorted(sources, key=lambda item: 0 if _stream_format(item) == "hls" else 1)


def _extract_embed_urls(soup: BeautifulSoup, page_url: str) -> List[str]:
    urls = []
    for node in soup.select("iframe[src], iframe[data-src], video[data-embed], [data-embed-url]"):
        for attribute in ("src", "data-src", "data-embed", "data-embed-url"):
            candidate = _normalize_player_url(node.get(attribute), page_url)
            if candidate and candidate not in urls:
                urls.append(candidate)
    return urls


def _is_direct_media_url(url: str) -> bool:
    return _stream_format(url) in {"hls", "mp4"}


def _stream_format(url: str) -> str:
    path = urlparse(url).path.lower()
    if path.endswith(".m3u8"):
        return "hls"
    if path.endswith(".mp4"):
        return "mp4"
    return ""


def _is_tracking_host(host: str) -> bool:
    return host == "mesclck.com" or host.endswith(".mesclck.com")