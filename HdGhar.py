import http.cookiejar
import json
import re
import urllib.error
import urllib.parse
import urllib.request

TITLE = "HDGhar Scraper"
VERSION = "1.1.0"
DESCRIPTION = "Fetches streams from HDGhar via its API"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"

TMDB_API_KEY = "92c1507cc18d85200e7a0b96abb37316"
HDGHAR_API = "https://hdghartv.cc"

_cookiejar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_cookiejar))

def _request(url, method="GET", data=None, headers=None):
    request_headers = {"User-Agent": USER_AGENT}
    if headers:
        request_headers.update(headers)
    body = None
    if method == "POST":
        if isinstance(data, dict):
            body = urllib.parse.urlencode(data).encode("utf-8")
        elif data is not None:
            body = data
    req = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with _opener.open(req, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except Exception:
        return 0, ""

def get_streams(media_type, media_id, config=None):
    imdb_id = media_id
    season = episode = None
    if ":" in media_id:
        parts = media_id.split(":", 2)
        imdb_id, season, episode = parts[0], parts[1], parts[2]
        
    # 1. TMDB Lookup
    find_url = "https://api.themoviedb.org/3/find/" + urllib.parse.quote(imdb_id)
    query = urllib.parse.urlencode({"api_key": TMDB_API_KEY, "external_source": "imdb_id"})
    status, body = _request(find_url + "?" + query)
    
    if status != 200:
        return [{"name": TITLE, "title": f"TMDB Error: {status}", "url": "http://127.0.0.1/error.mp4"}]
        
    try:
        data = json.loads(body)
    except Exception:
        return [{"name": TITLE, "title": "TMDB Parse Error", "url": "http://127.0.0.1/error.mp4"}]
        
    tmdb_id = None
    title = ""
    if media_type == "movie" and data.get("movie_results"):
        item = data["movie_results"][0]
        tmdb_id = str(item.get("id"))
        title = item.get("title", "")
    elif media_type == "series" and data.get("tv_results"):
        item = data["tv_results"][0]
        tmdb_id = str(item.get("id"))
        title = item.get("name", "")
        
    if not tmdb_id or not title:
        return [{"name": TITLE, "title": "No TMDB Match Found", "url": "http://127.0.0.1/error.mp4"}]
        
    # 2. HDGhar Search
    search_url = f"{HDGHAR_API}/api/search?q={urllib.parse.quote(title)}&type=all&page=1"
    headers = {"Referer": HDGHAR_API + "/", "Accept": "application/json"}
    status, body = _request(search_url, headers=headers)
    
    if status != 200:
        return [{"name": TITLE, "title": f"HDGhar Search Error: HTTP {status}", "url": "http://127.0.0.1/error.mp4"}]
        
    try:
        search_data = json.loads(body)
    except Exception:
        return [{"name": TITLE, "title": "HDGhar Search JSON Error", "url": "http://127.0.0.1/error.mp4"}]
        
    movies = search_data.get("movies", [])
    series = search_data.get("series", [])
    all_items = movies + series
    
    target_id = None
    for item in all_items:
        if str(item.get("tmdbId")) == tmdb_id:
            target_id = item.get("_id")
            break
            
    if not target_id:
        return [{"name": TITLE, "title": "No Match in HDGhar Search", "url": "http://127.0.0.1/error.mp4"}]
        
    # 3. HDGhar Details Fetch
    detail_type = "movie" if media_type == "movie" else "series"
    detail_url = f"{HDGHAR_API}/api/{detail_type}/{target_id}"
    
    status, body = _request(detail_url, headers=headers)
    if status != 200:
        return [{"name": TITLE, "title": f"HDGhar Details Error: HTTP {status}", "url": "http://127.0.0.1/error.mp4"}]
        
    try:
        detail_data = json.loads(body)
    except Exception:
        return [{"name": TITLE, "title": "HDGhar Details JSON Error", "url": "http://127.0.0.1/error.mp4"}]
        
    streaming_links = []
    if media_type == "movie":
        streaming_links = detail_data.get("streamingLinks", [])
    else:
        seasons = detail_data.get("seasons", [])
        for s in seasons:
            if str(s.get("seasonNumber")) == str(season):
                episodes = s.get("episodes", [])
                for e in episodes:
                    if str(e.get("episodeNumber")) == str(episode):
                        streaming_links = e.get("streamingLinks", [])
                        break
                break
                
    if not streaming_links:
        return [{"name": TITLE, "title": "No Streaming Links Found in JSON", "url": "http://127.0.0.1/error.mp4"}]
        
    streams = []
    for link in streaming_links:
        url = link.get("url")
        if not url:
            continue
            
        link_name = link.get("name", "")
        
        quality = "HD"
        if "2160p" in link_name.lower() or "4k" in link_name.lower():
            quality = "4K 2160p"
        elif "1080p" in link_name.lower():
            quality = "1080p"
        elif "720p" in link_name.lower():
            quality = "720p"
            
        audio = ""
        if "dual" in link_name.lower() or "multi" in link_name.lower():
            audio = "Dual-Audio"
        elif "hindi" in link_name.lower() or "hin" in link_name.lower():
            audio = "Hindi"
            
        stream_title = f"{quality} {audio} - {link_name}".strip()
            
        streams.append({
            "name": TITLE,
            "title": stream_title,
            "url": url,
            "behaviorHints": {
                "notMyMetadata": True,
                "proxyHeaders": {
                    "request": {
                        "User-Agent": USER_AGENT,
                        "Referer": HDGHAR_API + "/"
                    }
                }
            }
        })
        
    return streams
