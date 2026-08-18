"""
MegaSource Scraper for HDGharTV
"""
import json
import urllib.parse
import urllib.request
import traceback

TITLE = "HDGharTV"
VERSION = "1.0.0"
DESCRIPTION = "HDGhar TV movies and series scraper"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
TMDB_API_KEY = "1865f43a0549ca50d341dd9ab8b29f49"

# HDGharTV occasionally rotates its TLD, so we check multiple
DOMAINS = [
    "https://hdghartv.com", 
    "https://hdghartv.cc", 
    "https://hdghartv.top", 
    "https://hdghartv.in"
]

# --- Error Handling ---

def return_error(msg):
    """Forces an error stream to appear so MegaSource doesn't fail silently."""
    return [{
        "name": "HDGHAR ERROR",
        "title": str(msg),
        # Dummy video so Stremio/MegaSource doesn't reject the stream format
        "url": "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/TearsOfSteel.mp4",
        "behaviorHints": {
            "notMyMetadata": True,
            "proxyHeaders": {"request": {}}
        }
    }]

# --- HTTP & API Utilities ---

def _request(url, headers=None):
    req_headers = {"User-Agent": USER_AGENT}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', errors='replace')
    except Exception as e:
        return 0, str(e)

def get_tmdb_meta(media_id, media_type):
    tmdb_id = media_id
    if str(media_id).startswith("tt"):
        find_url = f"https://api.themoviedb.org/3/find/{media_id}?api_key={TMDB_API_KEY}&external_source=imdb_id"
        st, res = _request(find_url)
        if st == 200 and res:
            data = json.loads(res)
            results = data.get("tv_results") if media_type == "series" else data.get("movie_results")
            if results:
                tmdb_id = results[0].get("id")
            else:
                return None
        else:
            return None

    endpoint = "tv" if media_type == "series" else "movie"
    details_url = f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}?api_key={TMDB_API_KEY}"
    st, res = _request(details_url)
    if st != 200 or not res:
        return None
    data = json.loads(res)
    
    title = data.get("name") if media_type == "series" else data.get("title")
    rel_date = data.get("first_air_date") if media_type == "series" else data.get("release_date")
    year = rel_date[:4] if rel_date else ""
    
    return {"tmdb_id": tmdb_id, "title": title, "year": year}

# --- Main Scraper Entry Point ---

def get_streams(media_type, media_id, config=None):
    try:
        imdb_id = media_id
        season = episode = None
        
        # Parse media_id for TV series
        if ":" in media_id:
            parts = media_id.split(":", 2)
            imdb_id = parts[0]
            if len(parts) == 3:
                season = int(parts[1])
                episode = int(parts[2])
                
        meta = get_tmdb_meta(imdb_id, media_type)
        if not meta or not meta.get("tmdb_id"):
            return return_error(f"Failed to fetch TMDB Meta for {imdb_id}")
            
        tmdb_id = meta["tmdb_id"]
        title = meta["title"]
        
        # Discover the currently active domain
        api_host = None
        for d in DOMAINS:
            st, _ = _request(f"{d}/api/search?q=test&type=all&page=1")
            if st == 200:
                api_host = d
                break
                
        if not api_host:
            return return_error("All known HDGharTV domains failed to respond.")
            
        # 1. Search the HDGhar Database
        search_url = f"{api_host}/api/search?q={urllib.parse.quote(title)}&type=all&page=1"
        st, res = _request(search_url, headers={"Referer": f"{api_host}/"})
        if st != 200 or not res:
            return return_error(f"Search API Error {st}")
            
        data = json.loads(res)
        movies = data.get("movies", [])
        series = data.get("series", [])
        all_items = movies + series
        
        target_item = None
        for item in all_items:
            if str(item.get("tmdbId")) == str(tmdb_id):
                target_item = item
                break
                
        if not target_item:
            return return_error("Movie/Show not found in HDGharTV database.")
            
        item_id = target_item.get("_id")
        if not item_id:
            return return_error("Internal Item ID missing in search results.")
            
        # 2. Get the Stream Links
        mt = "series" if media_type == "series" else "movie"
        details_url = f"{api_host}/api/{mt}/{item_id}"
        st, res = _request(details_url, headers={"Referer": f"{api_host}/"})
        if st != 200 or not res:
            return return_error(f"Details API Error {st}")
            
        data = json.loads(res)
        streaming_links = []
        
        if media_type == "movie":
            streaming_links = data.get("streamingLinks", [])
        else:
            seasons = data.get("seasons", [])
            target_season = None
            for s in seasons:
                if str(s.get("seasonNumber")) == str(season):
                    target_season = s
                    break
            if not target_season:
                return return_error(f"Season {season} not found.")
                
            episodes = target_season.get("episodes", [])
            target_episode = None
            for e in episodes:
                if str(e.get("episodeNumber")) == str(episode):
                    target_episode = e
                    break
            if not target_episode:
                return return_error(f"Episode {episode} not found.")
                
            streaming_links = target_episode.get("streamingLinks", [])
            
        if not streaming_links:
            return return_error("No streaming links available for this title.")
            
        # 3. Format Output
        results = []
        for link in streaming_links:
            url = link.get("url")
            if not url:
                continue
                
            name = link.get("name", "")
            quality = "HD"
            if "2160" in name.lower() or "4k" in name.lower():
                quality = "4K"
            elif "1080" in name.lower():
                quality = "1080p"
            elif "720" in name.lower():
                quality = "720p"
            elif "480" in name.lower():
                quality = "480p"
                
            results.append({
                "name": TITLE,
                "title": f"HDGharTV | {quality} | {name}",
                "url": url,
                "behaviorHints": {
                    "notMyMetadata": True,
                    "proxyHeaders": {
                        "request": {
                            "User-Agent": USER_AGENT,
                            "Referer": f"{api_host}/"
                        }
                    }
                }
            })
            
        return results

    except Exception as e:
        return return_error(f"Fatal Crash: {str(e)} | {traceback.format_exc()[:100]}")
