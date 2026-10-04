import json
import sys
from typing import Dict, List, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36"
)
PREFERRED_PROVIDER_HOSTS = {
    "dervlin.me",
    "posamari.me",
    "ninguno.cc",
    "lonpapil.eu",
    "fallafar.me",
}


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def normalize_url(candidate: Optional[str], page_url: str) -> Optional[str]:
    if not candidate:
        return None
    from urllib.parse import urljoin
    import html as html_module

    candidate = html_module.unescape(candidate.strip()).replace("\\/", "/")
    candidate = candidate.replace("\\u0026", "&").replace("&amp;", "&")
    if candidate.startswith("//"):
        candidate = "https:" + candidate
    resolved = urljoin(page_url, candidate)
    if urlparse(resolved).scheme not in {"http", "https"}:
        return None
    return resolved


def stream_format(url: str) -> str:
    path = urlparse(url).path.lower()
    if ".m3u8" in path:
        return "hls"
    if ".mp4" in path:
        return "mp4"
    if "/manifest.ts" in url.lower():
        return "hls"
    return ""


def extract_direct_sources(page_html: str, page_url: str) -> List[str]:
    import html as html_module
    import re

    soup = BeautifulSoup(page_html, "html.parser")
    sources: List[str] = []
    for node in soup.select("video[src], video source[src], source[src], video[data-src], source[data-src]"):
        candidate = normalize_url(node.get("src") or node.get("data-src"), page_url)
        if candidate and (stream_format(candidate) in {"hls", "mp4"}) and candidate not in sources:
            sources.append(candidate)

    normalized_html = html_module.unescape(page_html).replace("\\/", "/").replace("\\u0026", "&")
    media_pattern = re.compile(r"https?://[^\s\"'<>\\]+?\.(?:m3u8|mp4)(?:\?[^\s\"'<>\\]*)?", re.IGNORECASE)
    for match in media_pattern.findall(normalized_html):
        candidate = normalize_url(match.rstrip(",);}"), page_url)
        if candidate and candidate not in sources:
            sources.append(candidate)

    return sorted(sources, key=lambda item: 0 if stream_format(item) == "hls" else 1)


def should_abort_tracking(host: str) -> bool:
    host = host.lower()
    return host == "mesclck.com" or host.endswith(".mesclck.com")


def allowed_hosts(page_url: str, embed_url: Optional[str]) -> List[str]:
    hosts = [urlparse(page_url).hostname or ""]
    embed_host = urlparse(embed_url).hostname if embed_url else ""
    if embed_host:
        hosts.extend([embed_host, f"sts.{embed_host}"])
    hosts.extend([
        "dervlin.me",
        "sts.dervlin.me",
        "posamari.me",
        "sts.posamari.me",
        "ninguno.cc",
        "sts.ninguno.cc",
        "lonpapil.eu",
        "sts.lonpapil.eu",
        "fallafar.me",
        "sts.fallafar.me",
        "seckyes.cc",
        "owlsig.cc",
        "nasig.live",
        "owledge.cc",
        "app.rmelvo.shop",
        "cloudflare.com",
        "cloudfront.net",
    ])
    return [host.lower() for host in hosts if host]


def host_allowed(host: str, allowlist: List[str]) -> bool:
    host = host.lower()
    return any(host == allowed or host.endswith("." + allowed) for allowed in allowlist)


def should_abort_request(request_url: str, resource_type: str, allowlist: List[str]) -> bool:
    host = (urlparse(request_url).hostname or "").lower()
    if not host:
        return False
    if should_abort_tracking(host):
        return True
    if host_allowed(host, allowlist):
        return False
    blocked_document_hosts = {
        "google.com",
        "www.google.com",
        "intellipopup.com",
        "llvpn.com",
        "googlesyndication.com",
        "googleadservices.com",
    }
    if host in blocked_document_hosts or any(host.endswith("." + blocked) for blocked in blocked_document_hosts):
        return True
    return resource_type in {"document", "script", "fetch", "xhr", "image", "media", "other"}


def looks_like_stream_candidate(url: str) -> bool:
    lowered = url.lower()
    return (
        stream_format(url) in {"hls", "mp4"}
        or ".m3u8" in lowered
        or ".mp4" in lowered
        or "/manifest.ts" in lowered
        or "/play.m3u8" in lowered
        or "/master.m3u8" in lowered
    )


def candidate_sort_key(candidate: Dict) -> tuple:
    lowered = candidate["url"].lower()
    if "/play.m3u8" in lowered:
        priority = 0
    elif "/master.m3u8" in lowered:
        priority = 1
    elif "/manifest.ts" in lowered:
        priority = 2
    else:
        priority = 0 if stream_format(candidate["url"]) == "hls" else 3
    return (priority, len(candidate["url"]))


def click_iframe(page, selector: str = "iframe") -> None:
    try:
        box = page.locator(selector).first.bounding_box()
    except Exception:
        box = None
    if box:
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def inject_embed_iframe(page, embed_url: str) -> None:
    page.evaluate(
        """
        (iframeUrl) => {
            const existing = document.querySelector('iframe#__agent_embed');
            if (existing) existing.remove();
            const iframe = document.createElement('iframe');
            iframe.id = '__agent_embed';
            iframe.src = iframeUrl;
            iframe.width = 1280;
            iframe.height = 720;
            iframe.style.position = 'fixed';
            iframe.style.top = '0';
            iframe.style.left = '0';
            iframe.style.zIndex = '2147483647';
            iframe.style.background = '#000';
            document.body.appendChild(iframe);
        }
        """,
        embed_url,
    )


def first_iframe_url(page) -> Optional[str]:
    for frame in page.frames:
        if frame.url and frame.url not in {"about:blank", page.url}:
            return frame.url
    return None


def frame_sources(page) -> List[str]:
    sources = extract_direct_sources(page.content(), page.url)
    if sources:
        return sources
    for frame in page.frames:
        try:
            html = frame.content()
        except Exception:
            continue
        sources = extract_direct_sources(html, frame.url or page.url)
        if sources:
            return sources
    return []


def build_headers(context, stream_url: str, request_headers: Dict[str, str], referer: str) -> Dict[str, str]:
    interesting = {"accept", "accept-language", "origin", "referer", "user-agent", "authorization"}
    headers = {
        key.title(): value
        for key, value in (request_headers or {}).items()
        if key.lower() in interesting and value
    }
    if "Referer" not in headers and referer:
        headers["Referer"] = referer
    if "User-Agent" not in headers:
        headers["User-Agent"] = USER_AGENT
    cookies = context.cookies([stream_url])
    if cookies and "Cookie" not in headers:
        headers["Cookie"] = "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in cookies)
    return headers


def safe_request_page_url(request, fallback_url: str) -> str:
    try:
        frame = request.frame
        if frame and frame.url:
            return frame.url
    except Exception:
        pass
    return fallback_url


def resolve_stream(event_url: str, page_title: str, embed_url: Optional[str]) -> Dict:
    candidates: List[Dict] = []
    allowlist = allowed_hosts(event_url, embed_url)

    def capture(candidate_url: Optional[str], page_url: str, request_headers: Optional[Dict[str, str]] = None) -> None:
        normalized = normalize_url(candidate_url, page_url)
        if not normalized or not looks_like_stream_candidate(normalized):
            return
        if any(existing["url"] == normalized for existing in candidates):
            return
        candidates.append({
            "url": normalized,
            "pageUrl": page_url,
            "headers": dict(request_headers or {}),
        })
        log(f"captured candidate count={len(candidates)} url={normalized}")

    def build_result(result_page, source_url: str) -> Dict:
        return {
            "title": page_title or result_page.title() or "FBStream event",
            "streamUrl": source_url,
            "streamFormat": stream_format(source_url),
            "httpHeaders": {"Referer": result_page.url, "User-Agent": USER_AGENT},
            "extractor": "playwright",
        }

    def attach_page_capture(target_page) -> None:
        target_page.route(
            "**/*",
            lambda route: route.abort()
            if should_abort_request(route.request.url, route.request.resource_type, allowlist)
            else route.continue_(),
        )
        target_page.on(
            "request",
            lambda request: capture(
                request.url,
                safe_request_page_url(request, target_page.url or event_url),
                request.headers,
            ),
        )
        target_page.on(
            "response",
            lambda response: capture(
                response.url,
                safe_request_page_url(response.request, target_page.url or event_url),
                response.request.headers,
            ),
        )
        target_page.on("popup", lambda popup: popup.close())

    with sync_playwright() as playwright:
        log(f"worker starting event_url={event_url} embed_url={embed_url}")
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=USER_AGENT,
            ignore_https_errors=True,
            viewport={"width": 1366, "height": 768},
        )
        page = context.new_page()
        attach_page_capture(page)
        page.goto(event_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
        log(f"event page loaded url={page.url} frames={len(page.frames)}")

        sources = frame_sources(page)
        if sources:
            log(f"resolved direct frame source url={sources[0]}")
            browser.close()
            return build_result(page, sources[0])

        embed_host = (urlparse(embed_url).hostname or "").lower() if embed_url else ""
        if embed_url and embed_host in PREFERRED_PROVIDER_HOSTS:
            log(f"trying preferred provider helper path host={embed_host}")
            helper_page = context.new_page()
            attach_page_capture(helper_page)
            helper_page.set_content("<html><body></body></html>")
            inject_embed_iframe(helper_page, embed_url)
            for wait_ms in (4000, 6000, 8000):
                click_iframe(helper_page, 'iframe#__agent_embed')
                helper_page.wait_for_timeout(wait_ms)
                log(f"preferred helper wait_ms={wait_ms} candidates={len(candidates)} frames={len(helper_page.frames)}")
                sources = frame_sources(helper_page)
                if sources:
                    log(f"resolved preferred helper source url={sources[0]}")
                    browser.close()
                    return build_result(helper_page, sources[0])
                if candidates:
                    break

        for wait_ms in (8000, 10000, 12000):
            if candidates:
                break
            click_iframe(page)
            page.wait_for_timeout(wait_ms)
            log(f"event page click wait_ms={wait_ms} candidates={len(candidates)} frames={len(page.frames)}")
            sources = frame_sources(page)
            if sources:
                log(f"resolved event page source after click url={sources[0]}")
                browser.close()
                return build_result(page, sources[0])

        if not candidates and embed_url:
            log("injecting embed iframe into event page")
            inject_embed_iframe(page, embed_url)
            for wait_ms in (8000, 12000, 14000):
                click_iframe(page, 'iframe#__agent_embed')
                page.wait_for_timeout(wait_ms)
                log(f"event page injected iframe wait_ms={wait_ms} candidates={len(candidates)} frames={len(page.frames)}")
                if candidates:
                    break
                sources = frame_sources(page)
                if sources:
                    log(f"resolved injected iframe source url={sources[0]}")
                    browser.close()
                    return build_result(page, sources[0])

        if not candidates:
            iframe_url = first_iframe_url(page)
            if iframe_url:
                log(f"trying generic helper page iframe_url={iframe_url}")
                helper_page = context.new_page()
                attach_page_capture(helper_page)
                helper_page.set_content("<html><body></body></html>")
                helper_page.evaluate(
                    "(iframeUrl) => { const iframe = document.createElement('iframe'); iframe.src = iframeUrl; iframe.width = 1280; iframe.height = 720; iframe.style.position = 'fixed'; iframe.style.top = '0'; iframe.style.left = '0'; iframe.style.zIndex = '2147483647'; document.body.appendChild(iframe); }",
                    iframe_url,
                )
                for wait_ms in (8000, 12000):
                    click_iframe(helper_page)
                    helper_page.wait_for_timeout(wait_ms)
                    log(f"generic helper wait_ms={wait_ms} candidates={len(candidates)} frames={len(helper_page.frames)}")
                    if candidates:
                        break
                    sources = frame_sources(helper_page)
                    if sources:
                        log(f"resolved generic helper source url={sources[0]}")
                        browser.close()
                        return build_result(helper_page, sources[0])

        if not candidates:
            browser.close()
            raise RuntimeError("Playwright did not observe a playable media request")

        best = sorted(candidates, key=candidate_sort_key)[0]
        result = {
            "title": page_title or page.title() or "FBStream event",
            "streamUrl": best["url"],
            "streamFormat": stream_format(best["url"]) or "hls",
            "httpHeaders": build_headers(context, best["url"], best["headers"], best["pageUrl"]),
            "extractor": "playwright",
        }
        log(f"using captured candidate url={best['url']}")
        browser.close()
        return result


def main() -> int:
    event_url = sys.argv[1]
    page_title = sys.argv[2] if len(sys.argv) > 2 else "FBStream event"
    embed_url = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else None
    result = resolve_stream(event_url, page_title, embed_url)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
