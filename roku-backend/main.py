import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware


from scrapers.famelack_scraper import get_famelack_catalog, get_famelack_stream
from scrapers.moviebox_scraper import get_moviebox_catalog, get_moviebox_detail, get_moviebox_stream
from scrapers.fbstream_scraper import get_fbstream_catalog, get_fbstream_stream
from utils.playback_proxy import _safe_resource_url, proxy_playback_request, register_playback_session

load_dotenv()


def configure_logging() -> None:
    log_dir = Path(__file__).resolve().parent / "logs"
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=os.getenv("ROKU_BACKEND_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "backend.log", encoding="utf-8"),
        ],
        force=True,
    )


configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Roku Content Middleware",
    description="Unified backend for Famelack, MovieBox, and FBStream Roku apps",
    version="1.0.0",
)

# Enable CORS for Roku device access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== Famelack Endpoints =====

@app.get("/api/famelack/catalog")
def famelack_catalog(
    content_type: str = Query("tv", description="Content type: tv, radio, or webcam"),
    country: Optional[str] = Query(None, description="Filter by country code (e.g., US, UK)"),
):
    """
    Get Famelack catalog for live TV, radio, or webcams.
    Can filter by country for TV channels.
    """
    try:
        return get_famelack_catalog(content_type, country)
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@app.get("/api/famelack/stream")
def famelack_stream(url: str = Query(..., description="Source URL from Famelack")):
    """
    Extract direct stream URL for Famelack content.
    Handles IPTV m3u8 playlists and direct stream links.
    """
    try:
        return get_famelack_stream(url)
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


# ===== MovieBox Endpoints =====

@app.get("/api/moviebox/catalog")
def moviebox_catalog(
    category: Optional[str] = Query(None, description="Category slug (e.g., popular-series, action-movies)"),
):
    """
    Get MovieBox catalog for movies and TV series.
    Can filter by category.
    """
    try:
        return get_moviebox_catalog(category)
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@app.get("/api/moviebox/detail/{content_id}")
def moviebox_detail(content_id: str):
    """
    Get detailed information for a MovieBox TV series or movie.
    For TV series, includes seasons and episodes.
    """
    try:
        return get_moviebox_detail(content_id)
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@app.get("/api/moviebox/stream")
def moviebox_stream(url: str = Query(..., description="Source URL from MovieBox")):
    """
    Extract direct stream URL for MovieBox content.
    """
    try:
        return get_moviebox_stream(url)
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


# ===== FBStream Endpoints =====

@app.get("/api/fbstream/catalog")
async def fbstream_catalog(
    category: str = Query("live-now", description="FBStream sport category slug (e.g., football, basketball, live-now)"),
):
    """Get scheduled sports events for an FBStream category."""
    logger.info("FBStream catalog request category=%s", category)
    try:
        payload = await run_in_threadpool(get_fbstream_catalog, category)
        item_count = 0
        if payload.get("categories"):
            for catalog_category in payload["categories"]:
                item_count += len(catalog_category.get("items") or [])
        logger.info("FBStream catalog response category=%s items=%s", category, item_count)
        return payload
    except Exception as error:
        logger.exception("FBStream catalog failed category=%s", category)
        raise HTTPException(status_code=500, detail=str(error))


@app.get("/api/fbstream/stream")
async def fbstream_stream(
    request: Request,
    url: str = Query(..., description="Event page URL from FBStream"),
):
    """Resolve an FBStream event page to a proxied playable stream."""
    client_host = request.client.host if request.client else "unknown"
    logger.info("FBStream stream request client=%s url=%s", client_host, url)
    try:
        stream_info = await run_in_threadpool(get_fbstream_stream, url)
        payload = await run_in_threadpool(register_playback_session, request, url, stream_info)
        logger.info(
            "FBStream stream resolved client=%s extractor=%s playback_id=%s format=%s direct=%s proxied=%s",
            client_host,
            payload.get("extractor"),
            payload.get("playbackId"),
            payload.get("streamFormat"),
            _safe_resource_url(payload.get("directStreamUrl")),
            _safe_resource_url(payload.get("playbackUrl")),
        )
        return payload
    except Exception as error:
        logger.exception("FBStream stream resolution failed client=%s url=%s", client_host, url)
        raise HTTPException(status_code=500, detail=str(error))


@app.get("/api/fbstream/proxy/{playback_id}", name="fbstream_proxy")
@app.get("/api/fbstream/proxy/{playback_id}/{resource_name}", name="fbstream_proxy_named")
async def fbstream_proxy(
    request: Request,
    playback_id: str,
    resource_name: Optional[str] = None,
    url: Optional[str] = Query(None, description="Nested upstream HLS resource URL"),
    ctx: Optional[str] = Query(None, description="Encoded playback session context for proxy recovery"),
):
    """Proxy and rewrite FBStream media requests so Roku does not need site tokens or custom headers."""
    client_host = request.client.host if request.client else "unknown"
    logger.info(
        "FBStream proxy request client=%s playback_id=%s target=%s",
        client_host,
        playback_id,
        _safe_resource_url(url),
    )
    try:
        response = await run_in_threadpool(proxy_playback_request, request, playback_id, url, get_fbstream_stream, ctx)
        logger.info(
            "FBStream proxy response client=%s playback_id=%s status=%s content_type=%s",
            client_host,
            playback_id,
            response.status_code,
            response.headers.get("content-type"),
        )
        return response
    except HTTPException:
        logger.exception(
            "FBStream proxy HTTP failure client=%s playback_id=%s target=%s",
            client_host,
            playback_id,
            _safe_resource_url(url),
        )
        raise
    except Exception as error:
        logger.exception(
            "FBStream proxy failure client=%s playback_id=%s target=%s",
            client_host,
            playback_id,
            _safe_resource_url(url),
        )
        raise HTTPException(status_code=500, detail=str(error))


# ===== Health Check =====

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "Roku Content Middleware"}


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("SERVER_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
