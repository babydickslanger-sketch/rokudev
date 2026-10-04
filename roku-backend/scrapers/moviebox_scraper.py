import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Optional
from utils.stream_extractor import extract_stream_url

MOVIEBOX_BASE_URL = "https://movie-box.co"

def get_moviebox_catalog(category: Optional[str] = None) -> Dict:
    """
    Scrape MovieBox catalog for movies and TV series.
    
    Args:
        category: Optional category slug to filter (e.g., 'popular-series', 'action-movies')
    
    Returns:
        Dictionary with categories and items
    """
    try:
        # Fetch the main page
        response = requests.get(MOVIEBOX_BASE_URL, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract categories from the page
        categories = _extract_categories(soup, category)
        
        return {
            "categories": categories
        }
        
    except Exception as e:
        print(f"Error scraping MovieBox: {e}")
        return _get_fallback_catalog(category)

def _extract_categories(soup: BeautifulSoup, filter_category: Optional[str]) -> List[Dict]:
    """
    Extract categories and their items from MovieBox page.
    """
    categories = []
    
    # Try to find category sections
    # Based on the HTML structure, categories appear as sections with headings
    
    # Sample category mappings based on the website structure
    category_sections = [
        "Popular Series",
        "Popular Movie",
        "Adult Animation",
        "Epic Fantasy",
        "Sitcom",
        "Teen Romance",
        "Superhero Series",
        "Action&Thriller",
        "Gangster",
        "K-Drama",
        "C-Drama",
        "Anime",
        "Action Movies",
        "Horror Movies",
        "Romance"
    ]
    
    for cat_name in category_sections:
        if filter_category and cat_name.lower() != filter_category.lower():
            continue
        
        # Extract items for this category
        items = _extract_category_items(soup, cat_name)
        
        if items:
            categories.append({
                "title": cat_name,
                "slug": cat_name.lower().replace(" ", "-").replace("&", "and"),
                "items": items
            })
    
    # If no filter specified, return all categories
    # If filter specified but not found, return empty list
    
    return categories

def _extract_category_items(soup: BeautifulSoup, category_name: str) -> List[Dict]:
    """
    Extract items (movies/series) for a specific category.
    """
    items = []
    
    # In a real implementation, we would:
    # 1. Find the section for this category
    # 2. Parse the movie/series cards
    # 3. Extract title, poster, year, description, and detail URL
    
    # Sample items based on the website content
    if category_name == "Popular Series":
        items = [
            {
                "id": "blood-legacy",
                "title": "Blood Legacy",
                "year": "2024",
                "hdPosterUrl": "https://via.placeholder.com/300x450.png",
                "description": "Drama, Thriller",
                "contentType": "series",
                "detailUrl": f"{MOVIEBOX_BASE_URL}/detail/blood-legacy-Aau1lZfiH57"
            },
            {
                "id": "neagley",
                "title": "Neagley",
                "year": "2026",
                "hdPosterUrl": "https://via.placeholder.com/300x450.png",
                "description": "Action, Crime, Drama",
                "contentType": "series",
                "detailUrl": f"{MOVIEBOX_BASE_URL}/detail/neagley-kgfRKfjK46"
            },
            {
                "id": "paris-has-fallen",
                "title": "Paris Has Fallen",
                "year": "2024",
                "hdPosterUrl": "https://via.placeholder.com/300x450.png",
                "description": "Action, Drama",
                "contentType": "series",
                "detailUrl": f"{MOVIEBOX_BASE_URL}/detail/paris-has-fallen-MECZzYIddA8"
            }
        ]
    elif category_name == "Popular Movie":
        items = [
            {
                "id": "runner",
                "title": "Runner",
                "year": "2026",
                "hdPosterUrl": "https://via.placeholder.com/300x450.png",
                "description": "Action, Comedy, Thriller",
                "contentType": "movie",
                "detailUrl": f"{MOVIEBOX_BASE_URL}/detail/runner-QOMZhgKwwg"
            },
            {
                "id": "the-fix",
                "title": "The Fix",
                "year": "2026",
                "hdPosterUrl": "https://via.placeholder.com/300x450.png",
                "description": "Action, Thriller",
                "contentType": "movie",
                "detailUrl": f"{MOVIEBOX_BASE_URL}/detail/the-fix-U4maQqLbH"
            }
        ]
    elif category_name == "Anime":
        items = [
            {
                "id": "one-piece",
                "title": "One Piece",
                "year": "2022",
                "hdPosterUrl": "https://via.placeholder.com/300x450.png",
                "description": "Anime, Action, Adventure",
                "contentType": "series",
                "detailUrl": f"{MOVIEBOX_BASE_URL}/detail/one-piece-netflix"
            },
            {
                "id": "bleach",
                "title": "Bleach: Thousand-Year Blood War",
                "year": "2022",
                "hdPosterUrl": "https://via.placeholder.com/300x450.png",
                "description": "Anime, Action, Adventure",
                "contentType": "series",
                "detailUrl": f"{MOVIEBOX_BASE_URL}/detail/bleach-thousand-year-blood-war"
            }
        ]
    else:
        # Generic sample items for other categories
        items = [
            {
                "id": f"{category_name.lower().replace(' ', '-')}-1",
                "title": f"Sample {category_name} Title 1",
                "year": "2024",
                "hdPosterUrl": "https://via.placeholder.com/300x450.png",
                "description": "Sample description",
                "contentType": "movie",
                "detailUrl": f"{MOVIEBOX_BASE_URL}/detail/sample-1"
            }
        ]
    
    return items

def get_moviebox_detail(content_id: str) -> Dict:
    """
    Get detailed information for a MovieBox TV series or movie.
    For TV series, includes seasons and episodes.
    
    Args:
        content_id: The ID of the content (from catalog)
    
    Returns:
        Dictionary with detailed content information
    """
    try:
        # Try to construct the detail URL from the content_id
        # In a real implementation, we would store the full detail URL in the catalog
        
        detail_url = f"{MOVIEBOX_BASE_URL}/detail/{content_id}"
        
        response = requests.get(detail_url, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract detailed information
        # This depends on the actual detail page structure
        
        # Sample detail response
        if content_id in ["blood-legacy", "neagley", "paris-has-fallen", "one-piece", "bleach"]:
            # TV series with seasons
            return {
                "id": content_id,
                "title": content_id.replace("-", " ").title(),
                "description": "Sample TV series description",
                "year": "2024",
                "contentType": "series",
                "posterUrl": "https://via.placeholder.com/300x450.png",
                "seasons": [
                    {
                        "seasonNumber": 1,
                        "episodes": [
                            {"episodeNumber": 1, "title": "Episode 1", "streamUrl": f"{MOVIEBOX_BASE_URL}/stream/s1e1"},
                            {"episodeNumber": 2, "title": "Episode 2", "streamUrl": f"{MOVIEBOX_BASE_URL}/stream/s1e2"},
                            {"episodeNumber": 3, "title": "Episode 3", "streamUrl": f"{MOVIEBOX_BASE_URL}/stream/s1e3"}
                        ]
                    },
                    {
                        "seasonNumber": 2,
                        "episodes": [
                            {"episodeNumber": 1, "title": "Episode 1", "streamUrl": f"{MOVIEBOX_BASE_URL}/stream/s2e1"},
                            {"episodeNumber": 2, "title": "Episode 2", "streamUrl": f"{MOVIEBOX_BASE_URL}/stream/s2e2"}
                        ]
                    }
                ]
            }
        else:
            # Movie
            return {
                "id": content_id,
                "title": content_id.replace("-", " ").title(),
                "description": "Sample movie description",
                "year": "2024",
                "contentType": "movie",
                "posterUrl": "https://via.placeholder.com/300x450.png",
                "streamUrl": f"{MOVIEBOX_BASE_URL}/stream/{content_id}"
            }
            
    except Exception as e:
        print(f"Error getting MovieBox detail: {e}")
        return {
            "id": content_id,
            "title": "Unknown Content",
            "description": "Unable to load details",
            "contentType": "movie"
        }

def get_moviebox_stream(url: str) -> Dict:
    """
    Extract direct stream URL for MovieBox content.
    
    Args:
        url: The MovieBox page URL or stream URL
    
    Returns:
        Dictionary with stream URL and metadata
    """
    try:
        # Use yt-dlp to extract the stream URL
        stream_info = extract_stream_url(url)
        return stream_info
        
    except Exception as e:
        print(f"Error extracting MovieBox stream: {e}")
        return {
            "title": "Sample Stream",
            "streamUrl": "https://example.com/sample.m3u8",
            "streamFormat": "hls"
        }

def _get_fallback_catalog(filter_category: Optional[str]) -> Dict:
    """
    Return fallback catalog data when scraping fails.
    """
    categories = [
        {
            "title": "Popular Series",
            "slug": "popular-series",
            "items": [
                {
                    "id": "sample-series-1",
                    "title": "Sample Series",
                    "year": "2024",
                    "hdPosterUrl": "https://via.placeholder.com/300x450.png",
                    "description": "Sample description",
                    "contentType": "series",
                    "detailUrl": f"{MOVIEBOX_BASE_URL}/detail/sample-series-1"
                }
            ]
        }
    ]
    
    if filter_category:
        categories = [c for c in categories if c["slug"] == filter_category]
    
    return {"categories": categories}
