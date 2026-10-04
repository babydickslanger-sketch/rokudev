from mitmproxy import http
import logging

logger = logging.getLogger(__name__)

class AntiBotBypass:
    """Mitmproxy addon to bypass anti-bot measures for streaming servers."""
    
    def __init__(self):
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36"
        self.accept_language = "en-US,en;q=0.9"
        self.accept_encoding = "gzip, deflate, br"
    
    def request(self, flow: http.HTTPFlow) -> None:
        """Modify outgoing requests to bypass anti-bot detection."""
        url = flow.request.pretty_url.lower()
        
        # Target the problematic streaming servers
        if any(host in url for host in ["owledge.cc", "seckyes.cc", "nasig.live", "owlsig.cc"]):
            logger.info(f"AntiBotBypass: Modifying request to {flow.request.host}")
            
            # Add/modify headers to look like a real browser
            flow.request.headers["User-Agent"] = self.user_agent
            flow.request.headers["Accept"] = "*/*"
            flow.request.headers["Accept-Language"] = self.accept_language
            flow.request.headers["Accept-Encoding"] = self.accept_encoding
            flow.request.headers["Connection"] = "keep-alive"
            flow.request.headers["Sec-Fetch-Dest"] = "empty"
            flow.request.headers["Sec-Fetch-Mode"] = "cors"
            flow.request.headers["Sec-Fetch-Site"] = "cross-site"
            
            # Add referer if not present
            if "Referer" not in flow.request.headers:
                flow.request.headers["Referer"] = "https://fbstream.is/"
            
            # Remove suspicious headers
            flow.request.headers.pop("X-Forwarded-For", None)
            flow.request.headers.pop("X-Real-IP", None)
    
    def response(self, flow: http.HTTPFlow) -> None:
        """Handle responses from streaming servers."""
        url = flow.request.pretty_url.lower()
        
        if any(host in url for host in ["owledge.cc", "seckyes.cc", "nasig.live", "owlsig.cc"]):
            logger.info(f"AntiBotBypass: Response from {flow.request.host} status={flow.response.status_code}")
            
            # Add CORS headers to allow Roku access
            flow.response.headers["Access-Control-Allow-Origin"] = "*"
            flow.response.headers["Access-Control-Allow-Methods"] = "GET, HEAD, OPTIONS"
            flow.response.headers["Access-Control-Allow-Headers"] = "*"
            flow.response.headers["Cache-Control"] = "no-store"

addons = [AntiBotBypass()]
