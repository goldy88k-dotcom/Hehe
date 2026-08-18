"""
MegaSource Scraper for HDGharTV (v3)
"""
import json
import urllib.parse
import urllib.request
import traceback

TITLE = "HDGharTV"
VERSION = "1.0.3"
DESCRIPTION = "HDGhar TV movies and series scraper"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
TMDB_API_KEY = "1865f43a0549ca50d341dd9ab8b29f49"

# We'll use the main API endpoint from the plugin logic
API_HOST = "https://hdghartv.cc"

def return_error(msg):
    return [{
        "name": "HDGHAR ERROR",
        "title": str(msg),
        "url": "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/TearsOfSteel.mp4",
        "behaviorHints": {
            "notMyMetadata": True,
            "proxyHeaders": {"request": {}}
        }
    }]

def _request(url, headers=None):
    req_headers = {"User-Agent": USER_AGENT}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
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
    return {"tmdb_id": tmdb_id, "title": title}

def get_streams(media_type, media_id, config=None):
    try:
        imdb_id = media_id
        season = episode = None
        
        if ":" in media_id:
            parts = media_id.split(":", 2)
            imdb_id = parts[0]
            if len(parts) == 3:
                season = int(parts[1])
                episode = int(parts[2])
                
        meta = get_tmdb_meta(imdb_id, media_type)
        if not meta or not meta.get("tmdb_id"):
            return return_error(f"Failed TMDB lookup for {imdb_id}")
            
        tmdb_id = meta["tmdb_id"]
        title = meta["title"]
        
        # Search HDGhar API
        search_url = f"{API_HOST}/api/search?q={urllib.parse.quote(title)}&type=all&page=1"
        st, res = _request(search_url, headers={"Referer": f"{API_HOST}/"})
        
        if st != 200 or not res:
            return return_error(f"Search failed with code {st}")
            
        data = json.loads(res)
        all_items = data.get("movies", []) + data.get("series", [])
        
        target_item = None
        for item in all_items:
            # Match by TMDB ID or loose title match if ID field differs
            if str(item.get("tmdbId")) == str(tmdb_id):
                target_item = item
                break
                
        # Fallback to name matching if TMDB ID isn't indexed identically on their backend
        if not target_item:
            for item in all_items:
                if title.lower() in item.get("title", "").lower() or title.lower() in item.get("name", "").lower():
                    target_item = item
                    break
                    
        if not target_item:
            return return_error(f"Could not find '{title}' on HDGhar DB")
            
        item_id = target_item.get("_id")
        mt = "series" if media_type == "series" else "movie"
        
        details_url = f"{API_HOST}/api/{mt}/{item_id}"
        st, res = _request(details_url, headers={"Referer": f"{API_HOST}/"})
        
        if st != 200 or not res:
            return return_error(f"Details failed with code {st}")
            
        data = json.loads(res)
        streaming_links = []
        
        if media_type == "movie":
            streaming_links = data.get("streamingLinks", [])
        else:
            seasons = data.get("seasons", [])
            for s in seasons:
                if str(s.get("seasonNumber")) == str(season):
                    for e in s.get("episodes", []):
                        if str(e.get("episodeNumber")) == str(episode):
                            streaming_links = e.get("streamingLinks", [])
                            break
                    break
                    
        if not streaming_links:
            return return_error("Found title, but streaming links list was empty.")
            
        results = []
        for link in streaming_links:
            url = link.get("url")
            if not url:
                continue
            results.append({
                "name": TITLE,
                "title": f"HDGharTV | Dual-Audio",
                "url": url,
                "behaviorHints": {
                    "notMyMetadata": True,
                    "proxyHeaders": {
                        "request": {
                            "User-Agent": USER_AGENT,
                            "Referer": f"{API_HOST}/"
                        }
                    }
                }
            })
            
        return results

    except Exception as e:
        return return_error(f"Crash: {str(e)}")
