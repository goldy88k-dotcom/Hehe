"""
MegaSource Scraper for DesiFlix
"""
import json
import urllib.error
import urllib.request

TITLE = "DesiFlix"
VERSION = "1.0.0"
DESCRIPTION = "Bollywood, Hollywood, and South Indian movies in Dual Language"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
BASE_URL = "https://manifest.desitvhub.eu.org"

def _request_json(url):
    """Helper function to fetch and parse JSON using only standard libraries."""
    req = urllib.request.Request(
        url, 
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            if response.status == 200:
                body = response.read().decode("utf-8", errors="replace")
                return json.loads(body)
    except Exception:
        pass
    return None

def get_streams(media_type, media_id, config=None):
    """
    Main function required by MegaSource protocol.
    """
    imdb_id = media_id
    season = episode = None
    
    # Parse media_id for TV series (format: tt0944947:1:1)
    if ":" in media_id:
        parts = media_id.split(":", 2)
        imdb_id = parts[0]
        if len(parts) == 3:
            season = parts[1]
            episode = parts[2]

    # Build the DesiFlix API URL
    if media_type == "movie":
        url = f"{BASE_URL}/stream/movie/{imdb_id}.json"
    elif media_type == "series" and season and episode:
        url = f"{BASE_URL}/stream/series/{imdb_id}:{season}:{episode}.json"
    else:
        return []

    # Fetch data
    data = _request_json(url)
    if not data or "streams" not in data or not isinstance(data["streams"], list):
        return []

    # Format the output for MegaSource
    results = []
    for stream in data["streams"]:
        video_url = stream.get("url")
        if video_url:
            stream_name = stream.get("name", TITLE)
            stream_title = stream.get("title", "DesiFlix Stream")
            
            results.append({
                "name": stream_name,
                "title": stream_title,
                "url": video_url,
                "behaviorHints": {
                    "notMyMetadata": True,
                    "proxyHeaders": {
                        "request": {
                            "User-Agent": USER_AGENT,
                            "Referer": BASE_URL + "/"
                        }
                    }
                }
            })
            
    return results
