import re
from typing import Dict, Optional

def clean_hls_playlist(playlist_content: str) -> str:
    """
    Remove ad segments from HLS playlist.
    
    Removes ad-related tags like:
    - #EXT-X-CUE-OUT
    - #EXT-X-CUE-IN
    - #EXT-X-DISCONTINUITY (when associated with ads)
    - #EXT-X-AD-BACKUP
    
    Args:
        playlist_content: The raw HLS playlist content
    
    Returns:
        Cleaned playlist content without ad segments
    """
    lines = playlist_content.split('\n')
    cleaned_lines = []
    in_ad_segment = False
    
    for line in lines:
        # Check for ad-related tags
        if line.startswith('#EXT-X-CUE-OUT'):
            in_ad_segment = True
            continue  # Skip this line
        
        if line.startswith('#EXT-X-CUE-IN'):
            in_ad_segment = False
            continue  # Skip this line
        
        if line.startswith('#EXT-X-AD-BACKUP'):
            continue  # Skip this line
        
        # Handle discontinuity tags - only skip if in ad segment
        if line.startswith('#EXT-X-DISCONTINUITY'):
            if in_ad_segment:
                continue  # Skip discontinuity in ad segment
            # Keep discontinuity for non-ad segments (e.g., quality changes)
        
        # Skip segment URLs if we're in an ad segment
        if in_ad_segment and not line.startswith('#'):
            continue  # Skip this segment URL
        
        # Keep the line
        cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)

def has_ad_markers(playlist_content: str) -> bool:
    """
    Check if playlist contains ad markers.
    
    Args:
        playlist_content: The HLS playlist content
    
    Returns:
        True if ad markers are present
    """
    ad_markers = [
        '#EXT-X-CUE-OUT',
        '#EXT-X-CUE-IN',
        '#EXT-X-AD-BACKUP'
    ]
    
    for marker in ad_markers:
        if marker in playlist_content:
            return True
    
    return False

def filter_ad_segments_from_url(playlist_url: str) -> str:
    """
    Fetch HLS playlist from URL, remove ad segments, and return cleaned URL.
    
    Note: This function returns the cleaned playlist content directly.
    For actual use, you'd need to proxy the playlist or serve it locally.
    
    Args:
        playlist_url: The HLS playlist URL
    
    Returns:
        Cleaned playlist content
    """
    import requests
    
    try:
        response = requests.get(playlist_url, timeout=10)
        response.raise_for_status()
        
        playlist_content = response.text
        
        if has_ad_markers(playlist_content):
            return clean_hls_playlist(playlist_content)
        
        return playlist_content
        
    except Exception as e:
        print(f"Error filtering ad segments: {e}")
        # Return original content if filtering fails
        return playlist_content

def get_ad_free_manifest(original_url: str) -> Dict:
    """
    Get ad-free manifest information.
    
    In a production environment, this would:
    1. Fetch the original manifest
    2. Remove ad segments
    3. Serve the cleaned manifest from a local endpoint
    4. Return the local endpoint URL to the Roku app
    
    For this implementation, we'll return the original URL with a note
    that ad filtering would require a proxy server.
    
    Args:
        original_url: The original manifest URL
    
    Returns:
        Dictionary with manifest information
    """
    return {
        "streamUrl": original_url,
        "adFiltered": False,
        "note": "Ad filtering requires a proxy server to serve cleaned manifests"
    }
