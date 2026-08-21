import http.cookiejar
import json
import urllib.error
import urllib.parse
import urllib.request

TITLE = "PlayIMDB Scraper"
VERSION = "1.0.2"
DESCRIPTION = "PlayIMDB (vaplayer) for MegaSource"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# TMDB Key required to map MegaSource's IMDB IDs to TMDB IDs
TMDB_API_KEY = "92c1507cc18d85200e7a0b96abb37316"
BASE_API = "https://streamdata.vaplayer.ru/api.php"

# Re-implementing the CookieJar to persist sessions for anti-bot checks
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

def imdb_to_tmdb(imdb_id):
    """Converts IMDB ID to TMDB ID."""
    find_url = "https://api.themoviedb.org/3/find/" + urllib.parse.quote(imdb_id)
    query = urllib.parse.urlencode({"api_key": TMDB_API_KEY, "external_source": "imdb_id"})
    status, body = _request(find_url + "?" + query)
    if status == 200:
        try:
            data = json.loads(body)
            if data.get("movie_results"):
                return data["movie_results"][0]["id"]
            if data.get("tv_results"):
                return data["tv_results"][0]["id"]
        except (ValueError, TypeError):
            pass
    return None

def get_streams(media_type, media_id, config=None):
    imdb_id = media_id
    season = None
    episode = None
    
    if ":" in media_id:
        parts = media_id.split(":", 2)
        if len(parts) == 3:
            imdb_id = parts[0]
            season = parts[1]
            episode = parts[2]
        
    fetch_type = "tv" if media_type == "series" else "movie"
    tmdb_id = imdb_to_tmdb(imdb_id)
    
    # Required API Headers to mimic the web player
    custom_headers = {
        'Origin': 'https://nextgencloudfabric.com',
        'Referer': 'https://nextgencloudfabric.com/',
        'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
    }
    
    streams = []
    
    # Dual-query strategy: try TMDB natively first, fallback to IMDB
    queries = []
    if tmdb_id:
        queries.append(f"?id={tmdb_id}&type={fetch_type}")
    queries.append(f"?imdb={imdb_id}&type={fetch_type}")
    
    for q in queries:
        url = BASE_API + q
        if fetch_type == "tv" and season and episode:
            url += f"&s={season}&e={episode}"
            
        status, body = _request(url, headers=custom_headers)
        
        if status == 200:
            try:
                data = json.loads(body)
                if data.get("data") and data["data"].get("stream_urls"):
                    for idx, stream_url in enumerate(data["data"]["stream_urls"]):
                        s_lower = stream_url.lower()
                        
                        # Parse Quality & Format
                        quality = "1080p"
                        if "4k" in s_lower: quality = "4K"
                        elif "720p" in s_lower: quality = "720p"
                        
                        format_str = "MP4" if ".mp4" in s_lower else "HLS"
                        server_name = f"PlayIMDB {quality} - {format_str} {idx + 1}"

                        stream_obj = {
                            "name": TITLE,
                            "title": server_name,
                            "url": stream_url,
                            "behaviorHints": {
                                "notMyMetadata": True,
                                "proxyHeaders": {
                                    "request": {
                                        "User-Agent": USER_AGENT,
                                        "Origin": custom_headers["Origin"],
                                        "Referer": custom_headers["Referer"],
                                    }
                                }
                            }
                        }
                        streams.append(stream_obj)
                        
                    # Stop fallback queries if we successfully grabbed streams
                    if streams:
                        break 
            except (ValueError, TypeError):
                pass
                
    return streams
