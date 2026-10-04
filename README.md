# Roku Streaming Apps - Famelack, MovieBox & FBStream

This project contains three standalone Roku channels and a unified backend server for browsing Famelack (live TV, radio, webcams), MovieBox (movies, TV series), and FBStream (live sports schedules).

## Project Structure

```
roku-apps/
├── roku-backend/          # Unified Python FastAPI backend
│   ├── main.py           # FastAPI server
│   ├── scrapers/         # Website scrapers
│   ├── utils/            # Stream extraction & ad filtering
│   ├── requirements.txt  # Python dependencies
│   └── .env              # Configuration
├── roku-famelack/        # Famelack Roku app (standalone)
│   ├── manifest
│   ├── source/
│   ├── components/
│   └── images/
├── roku-moviebox/        # MovieBox Roku app (standalone)
│   ├── manifest
│   ├── source/
│   ├── components/
│   └── images/
├── roku-fbstream/        # FBStream Roku app (standalone)
│   ├── manifest
│   ├── source/
│   └── components/
├── roku-streaming-hub/   # Unified Roku app (recommended)
│   ├── manifest
│   ├── source/
│   ├── components/
│   └── images/
└── roku-streaming-hub.zip # Pre-packaged unified app for sideloading
```

## Architecture

The system uses a client-server architecture:

1. **Backend Server** (Python FastAPI):
   - Scrapes Famelack, MovieBox, and FBStream websites
   - Extracts video streams using yt-dlp
   - Provides clean JSON APIs for Roku apps
   - Filters ads from HLS playlists

2. **Roku Streaming Hub** (Unified App - Recommended):
   - Single app with main menu to choose between services
   - Famelack: Live TV channels by country, Online radio stations, Live webcams
   - MovieBox: Movies and TV series catalog, Category browsing, TV series detail view
   - FBStream: Live and scheduled sports events by sport category
   - Streamlined interface with shared components

3. **Standalone Apps** (Optional):
   - **Famelack Roku App**: Live TV, Radio & Webcams with tabbed interface
   - **MovieBox Roku App**: Movies & TV Series with category browsing

**Note about YouTube/Playlet:**
Playlet (YouTube client) requires DRM and complex library loading that cannot be easily integrated into a unified app. It should be installed as a separate app from the official Playlet zip file.

## Setup Instructions

### 1. Backend Server Setup

#### Prerequisites
- Python 3.12 (or 3.11)
- Windows, Mac, or Linux

#### Installation

```bash
# Navigate to backend directory
cd roku-backend

# Create virtual environment
uv venv --python 3.12

# Activate virtual environment
# On Windows:
.venv\Scripts\activate
# On Mac/Linux:
source .venv/bin/activate

# Install dependencies
pip install fastapi uvicorn yt-dlp requests beautifulsoup4 python-dotenv playwright

# Install Playwright's bundled browser for headless extraction
python -m playwright install chromium
```

#### Configuration

Edit `.env` file and update `SERVER_IP` to your local IP address:

```env
SERVER_IP=192.168.1.100
```

Find your IP address:
- Windows: `ipconfig`
- Mac: `ifconfig`
- Linux: `ip addr`

#### Run the Server

```bash
python main.py
```

The server will start on `http://0.0.0.0:8000`

#### Test the Server

```bash
# Health check
curl http://localhost:8000/health

# Famelack catalog
curl http://localhost:8000/api/famelack/catalog

# MovieBox catalog
curl http://localhost:8000/api/moviebox/catalog
```

### 2. Roku App Setup

#### Prerequisites
- Roku device with Developer Mode enabled
- Roku and server on the same network

#### Enable Developer Mode on Roku

1. Press the following sequence on your Roku remote:
   - `Home` (3x)
   - `Up` (2x)
   - `Right`, `Left`, `Right`, `Left`, `Right`

2. Note the device IP address shown on screen

3. Select **Enable installer and restart**

4. Set a developer password

#### Update Backend IP in Roku Apps

**For Unified Roku Streaming Hub:**

Edit the following files and update the backend IP to your server IP:

**Main Menu Scene** - `roku-streaming-hub/components/MainMenuScene.brs`:
```brightscript
m.backendIp = "http://192.168.1.100:8000"
```

**Famelack Scene** - `roku-streaming-hub/components/FamelackScene.brs`:
```brightscript
m.backendIp = "http://192.168.1.100:8000"
```

**MovieBox Scene** - `roku-streaming-hub/components/MovieBoxScene.brs`:
```brightscript
m.backendIp = "http://192.168.1.100:8000"
```

**FBStream Scene** - `roku-streaming-hub/components/FBStreamScene.brs`:
```brightscript
m.backendIp = "http://192.168.1.100:8000"
```

**For Standalone Apps (Optional):**

**Famelack App** - `roku-famelack/components/MainScene.brs`:
```brightscript
m.backendIp = "http://192.168.1.100:8000"
```

**MovieBox App** - `roku-moviebox/components/MainScene.brs`:
```brightscript
m.backendIp = "http://192.168.1.100:8000"
```

**FBStream App** - `roku-fbstream/components/MainScene.brs`:
```brightscript
m.backendIp = "http://192.168.1.100:8000"
```

**MovieBox Detail Scene** - `roku-moviebox/components/DetailScene.brs`:
```brightscript
m.backendIp = "http://192.168.1.100:8000"
```

#### Add App Icons

The unified app already includes updated icons for Famelack and MovieBox. Replace the placeholder if needed:
- `roku-streaming-hub/images/icon_hd.png`

For standalone apps:
- `roku-famelack/images/icon_hd.png`
- `roku-moviebox/images/icon_hd.png`

#### Package and Install

**Recommended: Use the Unified Roku Streaming Hub**

The unified app (`roku-streaming-hub.zip`) is pre-packaged and ready to sideload. It includes both Famelack and MovieBox in a single app with a main menu.

```bash
# The unified app is already packaged:
# roku-streaming-hub.zip
```

**Install on Roku:**

1. Open browser to `http://<YOUR_ROKU_IP>`

2. Login with username `rokudev` and your developer password

3. Go to **Application Installer**

4. Upload `roku-streaming-hub.zip`

5. Click **Install**

6. Launch the app from your Roku home screen

**Packaging Apps for Roku Sideloading:**

To package all apps with standard POSIX zip structure (avoiding Windows backslash errors):

```bash
python package_apps.py
```

This generates `roku-streaming-hub.zip`, `famelack.zip`, `moviebox.zip`, and `fbstream.zip` ready for sideloading.

## API Endpoints

### Famelack Endpoints

```
GET /api/famelack/catalog?content_type={tv|radio|webcam}&country={US|UK|...}
GET /api/famelack/stream?url={source_url}
```

### MovieBox Endpoints

```
GET /api/moviebox/catalog?category={popular-series|anime|action-movies|...}
GET /api/moviebox/detail/{content_id}
GET /api/moviebox/stream?url={source_url}
```

### FBStream Endpoints

```
GET /api/fbstream/catalog?category={live-now|football|nfl|basketball|...}
GET /api/fbstream/stream?url={event_page_url}
GET /api/fbstream/proxy/{playback_id}?url={upstream_media_or_playlist_url}
```

`/api/fbstream/stream` now resolves the event page to a proxied playback URL. The backend playback proxy rewrites HLS playlists and fetches segments, keys, and nested manifests with the required upstream headers/cookies so the Roku app can play the returned URL directly.

For Roku playback troubleshooting, backend logs include a correlated proxy trace for each playback ID: resource type, query-redacted URL, upstream status/content type/byte count/latency, HLS variant and media-playlist details, AES key length validation, and MPEG-TS packet sync validation. `ffprobe` inspects the first unencrypted MPEG-TS segment when available; encrypted segments are explicitly marked as skipped because probing ciphertext cannot identify codecs. Signed query values and key bytes are not included in these diagnostics.

FBStream master playlists are limited to the highest advertised rendition at or below 486 lines for Roku compatibility. This avoids selecting the tested 720p H.264 High Level 4.2 stream on a Roku Express 3900; its tested 864x486 H.264 Main Level 4.1 rendition remains available.

#### Optional FBStream extraction settings

- `PLAYWRIGHT_PROXY_SERVER=http://127.0.0.1:8080`
  - Routes backend Playwright traffic through a local proxy such as mitmproxy, Charles, or Fiddler Everywhere for inspection.
- `YTDLP_COOKIES_FROM_BROWSER=chrome`
  - Lets the yt-dlp CLI reuse browser cookies when a provider requires them.
- `STREAMLINK_PATH=C:\\Users\\<you>\\AppData\\Local\\Programs\\Streamlink\\bin\\streamlink.exe`
  - Overrides the detected Streamlink executable path if needed.

### Health Check

```
GET /health
```

## Running the Server in Background

### Automatic Startup at Login (Recommended)

To have the backend server start automatically when you log in to Windows:

**Option 1: Automated Setup**
```powershell
# Run as Administrator
cd D:\roku-apps
.\setup_autostart.ps1
```

**Option 2: Manual Setup via Task Scheduler**
1. Open **Task Scheduler**
2. Create Basic Task named "Roku Backend Server"
3. Trigger: "When I log on"
4. Action: Start a program
5. Program: `wscript.exe`
6. Arguments: `"D:\roku-apps\roku-backend\start_server_hidden.vbs"`

**Option 3: Startup Folder**
1. Press `Win + R` and type: `shell:startup`
2. Create shortcut to: `D:\roku-apps\roku-backend\start_server_hidden.vbs`

See `setup_autostart_manual.md` for detailed instructions.

### Windows (PowerShell - Manual Start)

```powershell
# Start in background
Start-Process python -ArgumentList "main.py" -WorkingDirectory "D:\roku-apps\roku-backend" -WindowStyle Hidden
```

### Linux/Mac (systemd)

Create `/etc/systemd/system/roku-backend.service`:

```ini
[Unit]
Description=Roku Content Middleware
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/roku-backend
ExecStart=/path/to/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable roku-backend
sudo systemctl start roku-backend
```

## Troubleshooting

### Server won't start
- Check if port 8000 is already in use
- Verify Python and dependencies are installed
- Check `.env` file configuration

### Roku app can't connect to server
- Verify server is running
- Check Roku and server are on same network
- Confirm SERVER_IP in Roku app matches server IP
- Check firewall settings (port 8000 must be open)

### Stream playback fails
- Stream URLs may be geo-restricted
- yt-dlp may need updates: `pip install --upgrade yt-dlp`
- Check if stream URL is valid in browser

### Scraping errors
- Website structure may have changed
- Check scraper logs for errors
- Websites may block scraping (consider rate limiting)

## Legal Notice

This project is for educational and personal use only. The apps link to publicly available streams and do not host content. Users are responsible for ensuring compliance with applicable laws and terms of service.

## Security Considerations

- The server is designed for local network use only
- Do not expose the server to the public internet
- Use strong developer passwords on Roku
- Keep dependencies updated

## Future Enhancements

- Implement proper website scraping (currently using sample data)
- Add caching for catalog data
- Implement search functionality
- Add favorites/watchlist features
- Create proper Roku icons
- Add error handling and retry logic
- Implement rate limiting for scraping
- Add user authentication (if needed)

## Support

For issues or questions:
1. Check the troubleshooting section
2. Review server logs
3. Test API endpoints with curl
4. Verify network connectivity
