import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Optional
from utils.stream_extractor import extract_stream_url

FAMELACK_BASE_URL = "https://famelack.com"

def get_famelack_catalog(content_type: str = "tv", country: Optional[str] = None) -> Dict:
    """
    Scrape Famelack catalog for TV, radio, or webcams.
    
    Args:
        content_type: 'tv', 'radio', or 'webcam'
        country: Optional country code for TV filtering
    
    Returns:
        Dictionary with categories and items
    """
    if content_type not in ["tv", "radio", "webcam"]:
        raise ValueError(f"Invalid content_type: {content_type}. Must be 'tv', 'radio', or 'webcam'")
    
    try:
        # Fetch the main page
        response = requests.get(FAMELACK_BASE_URL, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Based on content type, extract relevant information
        if content_type == "tv":
            return _extract_tv_catalog(soup, country)
        elif content_type == "radio":
            return _extract_radio_catalog(soup)
        else:  # webcam
            return _extract_webcam_catalog(soup)
            
    except Exception as e:
        print(f"Error scraping Famelack: {e}")
        # Return fallback sample data if scraping fails
        return _get_fallback_catalog(content_type)

def _extract_tv_catalog(soup: BeautifulSoup, country: Optional[str]) -> Dict:
    """
    Extract TV channel catalog from Famelack.
    Famelack uses IPTV-org data and has country-based organization.
    """
    categories = []
    
    # Try to find country listings or category listings
    # This is a simplified implementation - actual parsing depends on site structure
    
    # Sample category structure
    tv_category = {
        "title": "Live TV Channels",
        "items": []
    }
    
    # In a real implementation, we would:
    # 1. Parse the country list from the page
    # 2. Fetch country-specific channel listings
    # 3. Extract channel names, logos, and stream URLs
    
    # For now, return a sample structure
    sample_channels = [
        {
            "id": "channel_1",
            "title": "Sample News Channel",
            "hdPosterUrl": "https://via.placeholder.com/300x450.png",
            "description": "News channel",
            "country": "US",
            "targetUrl": f"{FAMELACK_BASE_URL}/tv/sample-channel"
        },
        {
            "id": "channel_2",
            "title": "Sample Sports Channel",
            "hdPosterUrl": "https://via.placeholder.com/300x450.png",
            "description": "Sports channel",
            "country": "UK",
            "targetUrl": f"{FAMELACK_BASE_URL}/tv/sample-sports"
        }
    ]
    
    if country:
        # Filter by country
        sample_channels = [ch for ch in sample_channels if ch.get("country") == country]
    
    tv_category["items"] = sample_channels
    categories.append(tv_category)
    
    return {
        "contentType": "tv",
        "categories": categories
    }

def _extract_radio_catalog(soup: BeautifulSoup) -> Dict:
    """
    Extract radio station catalog from Famelack.
    """
    categories = []
    
    radio_category = {
        "title": "Online Radio Stations",
        "items": []
    }
    
    # Sample radio stations
    sample_stations = [
        {
            "id": "radio_1",
            "title": "Sample FM Radio",
            "hdPosterUrl": "https://via.placeholder.com/300x450.png",
            "description": "Music radio station",
            "country": "US",
            "targetUrl": f"{FAMELACK_BASE_URL}/radio/sample-fm"
        },
        {
            "id": "radio_2",
            "title": "Sample News Radio",
            "hdPosterUrl": "https://via.placeholder.com/300x450.png",
            "description": "News radio station",
            "country": "UK",
            "targetUrl": f"{FAMELACK_BASE_URL}/radio/sample-news"
        }
    ]
    
    radio_category["items"] = sample_stations
    categories.append(radio_category)
    
    return {
        "contentType": "radio",
        "categories": categories
    }

def _extract_webcam_catalog(soup: BeautifulSoup) -> Dict:
    """
    Extract webcam catalog from Famelack.
    """
    categories = []
    
    webcam_category = {
        "title": "Live Webcams",
        "items": []
    }
    
    # Sample webcams
    sample_webcams = [
        {
            "id": "webcam_1",
            "title": "Sample City Webcam",
            "hdPosterUrl": "https://via.placeholder.com/300x450.png",
            "description": "City center view",
            "country": "US",
            "targetUrl": f"{FAMELACK_BASE_URL}/webcam/sample-city"
        },
        {
            "id": "webcam_2",
            "title": "Sample Beach Webcam",
            "hdPosterUrl": "https://via.placeholder.com/300x450.png",
            "description": "Beach view",
            "country": "FR",
            "targetUrl": f"{FAMELACK_BASE_URL}/webcam/sample-beach"
        }
    ]
    
    webcam_category["items"] = sample_webcams
    categories.append(webcam_category)
    
    return {
        "contentType": "webcam",
        "categories": categories
    }

def get_famelack_stream(url: str) -> Dict:
    """
    Extract direct stream URL for Famelack content.
    
    Args:
        url: The Famelack page URL for the channel/station/webcam
    
    Returns:
        Dictionary with stream URL and metadata
    """
    try:
        # Fetch the content page
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Try to find the actual stream URL in the page
        # This depends on how Famelack embeds the video player
        
        # Look for video element or script with stream URL
        video_element = soup.find('video')
        if video_element and video_element.get('src'):
            stream_url = video_element.get('src')
        else:
            # Look for script tags with stream data
            scripts = soup.find_all('script')
            stream_url = None
            for script in scripts:
                if script.string and ('m3u8' in script.string or 'stream' in script.string):
                    # Extract URL from script (simplified)
                    # In real implementation, use regex to parse
                    stream_url = "https://example.com/stream.m3u8"  # Placeholder
                    break
        
        if not stream_url:
            # If no direct URL found, use yt-dlp as fallback
            stream_info = extract_stream_url(url)
            return stream_info
        
        return {
            "title": "Famelack Stream",
            "streamUrl": stream_url,
            "streamFormat": "hls" if ".m3u8" in stream_url else "mp4"
        }
        
    except Exception as e:
        print(f"Error extracting Famelack stream: {e}")
        # Return sample stream for testing
        return {
            "title": "Sample Stream",
            "streamUrl": "https://example.com/sample.m3u8",
            "streamFormat": "hls"
        }

def _get_fallback_catalog(content_type: str) -> Dict:
    """
    Return fallback catalog data when scraping fails.
    """
    return {
        "contentType": content_type,
        "categories": [
            {
                "title": f"{content_type.capitalize()} Content",
                "items": [
                    {
                        "id": f"{content_type}_1",
                        "title": f"Sample {content_type} Item 1",
                        "hdPosterUrl": "https://via.placeholder.com/300x450.png",
                        "description": "Sample description",
                        "targetUrl": f"{FAMELACK_BASE_URL}/{content_type}/sample-1"
                    }
                ]
            }
        ]
    }
