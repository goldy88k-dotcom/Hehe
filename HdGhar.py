import http.cookiejar
import json
import urllib.error
import urllib.parse
import urllib.request
import ssl

TITLE = "HDGhar Scraper"
VERSION = "1.0.2"
DESCRIPTION = "Fetches streams from HDGhar via its API"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"

# Inheriting TMDB Key from your default scraper for IMDB -> TMDB conversion
TMDB_API_KEY = "92c1507cc18d85200e7a0b96abb373316" 

# Updated to the active working domain
HDGHAR_API = "https://hdghartv.com.pk" 

# Creating an unverified SSL context to prevent handshake errors on mirror domains
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

_cookiejar = http.cookiejar.CookieJar()
# Inject the custom SSL context into our urllib opener
_opener = urllib.request.build_opener(
    urllib.request.HTTPSHandler(context=ctx), 
    urllib.request.HTTPCookieProcessor(_cookiejar)
)

def _request(url, method="GET", data=None, headers=None):
    request_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9"
    }
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

def imdb_to_tmdb(imdb_id):
    find_url = "https://api.themoviedb.org/3/find/" + urllib.parse.quote(imdb_id)
    query = urllib.parse.urlencode({"api_key": TMDB_API_KEY, "external_source": "imdb_id"})
    status, body = _request(find_url + "?" + query)
    
    if status != 200:
        return None
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return None
        
    if data.get("movie_results"):
        item = data["movie_results"][0]
        return {"type": "movie", "tmdb_id": item["id"], "title": item.get("title")}
    if data.get("tv_results"):
        item = data["tv_results"][0]
        return {"type": "tv", "tmdb_id": item["id"], "title": item.get("name")}
    return None

def get_hdghar_streams(media_type, imdb_id, season=None, episode=None):
    tmdb_info = imdb_to_tmdb(imdb_id)
    if not tmdb_info:
        return []
        
    tmdb_id = str(tmdb_info["tmdb_id"])
    title = tmdb_info["title"]
    
    # 1. Search HDGhar API for the specific Title
    search_url = f"{HDGHAR_API}/api/search?q={urllib.parse.quote(title)}&type=all&page=1"
    headers = {"Referer": HDGHAR_API + "/", "Origin": HDGHAR_API}
    status, body = _request(search_url, headers=headers)
    
    if status != 200:
        return []
        
    try:
        search_data = json.loads(body)
    except Exception:
        return []
        
    movies = search_data.get("movies", [])
    series = search_data.get("series", [])
    all_items = movies + series
    
    # 2. Match the TMDB ID from the search results to get the internal _id
    target_id = None
    for item in all_items:
        if str(item.get("tmdbId")) == tmdb_id:
            target_id = item.get("_id")
            break
            
    if not target_id:
        return []
        
    # 3. Fetch link details using the extracted _id
    detail_type = "movie" if media_type == "movie" else "series"
    detail_url = f"{HDGHAR_API}/api/{detail_type}/{target_id}"
    
    status, body = _request(detail_url, headers=headers)
    if status != 200:
        return []
        
    try:
        detail_data = json.loads(body)
    except Exception:
        return []
        
    streaming_links = []
    
    # 4. Extract stream links
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
                
    streams = []
    # 5. Build the final output array
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
                        "Referer": HDGHAR_API + "/",
                        "Origin": HDGHAR_API
                    }
                }
            }
        })
        
    return streams

def get_streams(media_type, media_id, config=None):
    season = None
    episode = None
    imdb_id = media_id
    
    if ":" in media_id:
        parts = media_id.split(":", 2)
        imdb_id = parts[0]
        season = parts[1]
        episode = parts[2]
        
    if media_type == "movie":
        return get_hdghar_streams("movie", imdb_id)
    elif media_type == "series" and season and episode:
        return get_hdghar_streams("series", imdb_id, season, episode)
        
    return []
