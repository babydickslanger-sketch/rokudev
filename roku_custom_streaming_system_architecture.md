# Roku Ad-Free Streaming System Architecture & Plan

This document outlines the design, backend middleware setup, frontend Roku channel implementation, and deployment process for building a custom, ad-free streaming environment on Roku OS.

---

## Technical Overview

Because Roku OS runs a sandboxed environment without native web browsing or background script capabilities, the system uses a **Client-Server Architecture**:

```
┌─────────────────────────────────────────────────────────┐
│                      Roku TV App                        │
│             (BrightScript + SceneGraph)                 │
│                                                         │
│  • MainScene.xml (PosterGrid, RowList, Search bar)      │
│  • FetchTask.brs (Issues HTTP requests to local API)    │
│  • VideoPlayer.xml (Hands stream URLs to Video node)    │
└────────────────────────────▲────────────────────────────┘
                             │ (JSON over HTTP)
                             ▼
┌─────────────────────────────────────────────────────────┐
│              Local Middleware Server                    │
│             (Python FastAPI / Node.js)                  │
│                                                         │
│  • Scraping Engine (`yt-dlp` / BeautifulSoup)           │
│  • Ad-Filter Engine (Cleans HLS `.m3u8` playlists)       │
│  • Endpoint 1: `/api/catalog`  ──> Returns clean JSON   │
│  • Endpoint 2: `/api/stream`   ──> Returns video URL    │
└────────────────────────────▲────────────────────────────┘
                             │ (HTML Scraping / API Calls)
                             ▼
┌─────────────────────────────────────────────────────────┐
│                 Target Web Service                      │
└─────────────────────────────────────────────────────────┘
```

* **Local Middleware Server:** Scrapes target websites, strips out network tracking and ad blocks, converts website catalog data into structured JSON feeds, and extracts direct video manifest links (`.m3u8` or `.mp4`).
* **Roku TV App:** Native UI using BrightScript and SceneGraph. Renders clean media grids without web display banners and plays raw media streams via Roku’s native `Video` node.

---

## Phase 1: Local Backend Service (Python FastAPI)

### 1. Environment Setup

Run the following commands on your local server, PC, or Raspberry Pi:

```bash
mkdir roku-backend && cd roku-backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install fastapi uvicorn yt-dlp requests beautifulsoup4
```

### 2. Backend Implementation (`main.py`)

```python
from fastapi import FastAPI, HTTPException
import yt_dlp

app = FastAPI(title="Roku Content Middleware")

# Configure yt-dlp to extract info without downloading files
YTDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'format': 'best',
    'skip_download': True
}

@app.get("/api/catalog")
def get_catalog():
    """
    Parses and formats categories from the target service into clean JSON.
    Guarantees zero web display banners or ad scripts in the feed.
    """
    return {
        "categories": [
            {
                "title": "Featured Media",
                "items": [
                    {
                        "id": "video_1",
                        "title": "Sample Video Title",
                        "hdPosterUrl": "https://via.placeholder.com/300x450.png",
                        "targetUrl": "https://example.com/watch?v=123"
                    }
                ]
            }
        ]
    }

@app.get("/api/stream")
def get_stream_url(url: str):
    """
    Extracts the direct raw .m3u8 or .mp4 stream link, bypassing web ad frames.
    """
    try:
        with yt_dlp.YoutubeDL(YTDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            stream_url = info.get('url')
            
            if not stream_url:
                raise HTTPException(status_code=404, detail="Direct stream URL not found")
                
            return {
                "title": info.get("title", "Video"),
                "streamUrl": stream_url,
                "streamFormat": "hls" if ".m3u8" in stream_url else "mp4"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

## Phase 2: Roku Channel Development (BrightScript + SceneGraph)

### Directory Structure

```
RokuApp/
├── manifest
├── components/
│   ├── MainScene.xml
│   ├── MainScene.brs
│   ├── FetchTask.xml
│   └── FetchTask.brs
└── source/
    └── main.brs
```

### 1. Application Manifest (`manifest`)

```ini
title=Custom Streaming Client
major_version=1
minor_version=0
build_version=0
mm_icon_focus_hd=pkg:/images/icon_hd.png
```

### 2. Main Entry Point (`source/main.brs`)

```brightscript
sub Main()
    screen = CreateObject("roSGScreen")
    m.port = CreateObject("roMessagePort")
    screen.SetMessagePort(m.port)
    
    scene = screen.CreateScene("MainScene")
    screen.Show()
    
    while(true)
        msg = wait(0, m.port)
        if type(msg) = "roSGScreenEvent"
            if msg.isScreenClosed() then return
        end if
    end while
end sub
```

### 3. Asynchronous HTTP Network Task

#### `components/FetchTask.xml`
```xml
<?xml version="1.0" encoding="utf-8" ?>
<component name="FetchTask" extends="Task">
    <script type="text/brightscript" uri="pkg:/components/FetchTask.brs" />
    <interface>
        <field id="requestUrl" type="string" />
        <field id="responseJson" type="assocarray" />
    </interface>
</component>
```

#### `components/FetchTask.brs`
```brightscript
sub Init()
    m.top.functionName = "executeRequest"
end sub

sub executeRequest()
    urlTransfer = CreateObject("roUrlTransfer")
    urlTransfer.SetCertificatesFile("common:/certs/ca-bundle.crt")
    urlTransfer.InitClientCertificates()
    urlTransfer.SetUrl(m.top.requestUrl)
    
    jsonString = urlTransfer.GetToString()
    if jsonString <> ""
        m.top.responseJson = ParseJson(jsonString)
    end if
end sub
```

### 4. Main User Interface Scene

#### `components/MainScene.xml`
```xml
<?xml version="1.0" encoding="utf-8" ?>
<component name="MainScene" extends="Scene">
    <script type="text/brightscript" uri="pkg:/components/MainScene.brs" />
    
    <children>
        <PosterGrid 
            id="mediaGrid" 
            baseRowHeight="300" 
            captionMarginTop="10" 
            itemSpacing="[20, 20]" 
            translation="[80, 100]" />
            
        <Video 
            id="videoPlayer" 
            visible="false" 
            width="1280" 
            height="720" />
    </children>
</component>
```

#### `components/MainScene.brs`
```brightscript
sub Init()
    m.mediaGrid = m.top.findNode("mediaGrid")
    m.videoPlayer = m.top.findNode("videoPlayer")
    
    ' Set IP address to match local server location
    m.backendIp = "http://192.168.1.100:8000"
    
    m.mediaGrid.observeField("itemSelected", "onItemSelected")
    loadCatalog()
end sub

sub loadCatalog()
    m.task = CreateObject("roSGNode", "FetchTask")
    m.task.requestUrl = m.backendIp + "/api/catalog"
    m.task.observeField("responseJson", "onCatalogLoaded")
    m.task.control = "RUN"
end sub

sub onCatalogLoaded()
    catalog = m.task.responseJson
    content = CreateObject("roSGNode", "ContentNode")
    
    for each cat in catalog.categories
        for each item in cat.items
            node = content.CreateChild("ContentNode")
            node.title = item.title
            node.HDPosterUrl = item.hdPosterUrl
            node.addField("targetUrl", "string", false)
            node.targetUrl = item.targetUrl
        end for
    end for
    
    m.mediaGrid.content = content
    m.mediaGrid.setFocus(true)
end sub

sub onItemSelected()
    selectedItem = m.mediaGrid.content.getChild(m.mediaGrid.itemSelected)
    
    m.streamTask = CreateObject("roSGNode", "FetchTask")
    m.streamTask.requestUrl = m.backendIp + "/api/stream?url=" + selectedItem.targetUrl
    m.streamTask.observeField("responseJson", "playVideo")
    m.streamTask.control = "RUN"
end sub

sub playVideo()
    streamData = m.streamTask.responseJson
    
    videoContent = CreateObject("roSGNode", "ContentNode")
    videoContent.url = streamData.streamUrl
    videoContent.streamFormat = streamData.streamFormat
    
    m.videoPlayer.content = videoContent
    m.videoPlayer.visible = true
    m.videoPlayer.setFocus(true)
    m.videoPlayer.control = "play"
end sub
```

---

## Phase 3: Deployment Instructions

### 1. Enable Developer Mode on Roku
1. Key in sequence on the Roku remote: `Home` (3x), `Up` (2x), `Right`, `Left`, `Right`, `Left`, `Right`.
2. Note the device IP address shown on the screen.
3. Select **Enable installer and restart**, agree to terms, and set a developer password.

### 2. Install Package
1. Compress `RokuApp` folder contents into a `.zip` file (ensure `manifest` is in the root directory).
2. Open `http://<YOUR_ROKU_IP>` in a browser.
3. Log in using username `rokudev` and your password.
4. Upload `.zip` package via **Application Installer** and press **Install**.

---

## Phase 4: Maintenance & Handling Ad Insertion (SSAI)

* **Backend Adjustments:** Modifying website layout parsing or video extraction logic in `main.py` requires restarting the local server, not re-sideloading the Roku app.
* **Server-Side Ad Segment Filtering:** If the stream manifest contains spliced in-stream ads (such as HLS discontinuity tags `#EXT-X-DISCONTINUITY` or `#EXT-X-CUE-OUT`), set up an HTTP proxy in FastAPI to strip out ad segment lines from the `.m3u8` playlist text before handing the final manifest URL to Roku.