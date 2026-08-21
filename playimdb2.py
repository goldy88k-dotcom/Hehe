import http.cookiejar
import json
import urllib.error
import urllib.parse
import urllib.request

TITLE = "PlayIMDB Scraper"
VERSION = "1.0.3"
DESCRIPTION = "PlayIMDB for MegaSource"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

TMDB_API_KEY = "92c1507cc18d85200e7a0b96abb37316"
BASE_API = "https://streamdata.vaplayer.ru/api.php"

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
    """Converts MegaSource IMDB ID into a TMDB ID."""
    find_url = f"https://api.themoviedb.org/3/find/{urllib.parse.quote(imdb_id)}"
    query = urllib.parse.urlencode({"api_key": TMDB_API_KEY, "external_source": "imdb_id"})
    status, body = _request(f"{find_url}?{query}")
    if status == 200:
        try:
            data = json.loads(body)
            if data.get("movie_results"):
                return data["movie_results"][0]["id"]
            if data.get("tv_results"):
                return data["tv_results"][0]["id"]
        except:
            pass
    return None

def get_streams(media_type, media_id, config=None):
    imdb_id = media_id
    season = None
    episode = None
    
    if ":" in media_id:
        parts = media_id.split(":", 2)
        if len(parts) == 3:
            imdb_id, season, episode = parts[0], parts[1], parts[2]
        
    fetch_type = "tv" if media_type == "series" else "movie"
    tmdb_id = imdb_to_tmdb(imdb_id)
    
    # Exact match to the JS headers (no extra Accept or X-Requested-With)
    custom_headers = {
        'Origin': 'https://nextgencloudfabric.com',
        'Referer': 'https://nextgencloudfabric.com/'
    }
    
    # Brute-force URL combinations since the Nuvio JS parameter was obfuscated
    queries = []
    if tmdb_id:
        queries.append(f"?id={tmdb_id}&type={fetch_type}")
        queries.append(f"?tmdb={tmdb_id}&type={fetch_type}")
    queries.append(f"?imdb={imdb_id}&type={fetch_type}")
    
    streams = []
    
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
                        
                        quality = "4K" if "4k" in s_lower else "720p" if "720p" in s_lower else "1080p"
                        format_str = "MP4" if ".mp4" in s_lower else "HLS"

                        streams.append({
                            "name": TITLE,
                            "title": f"PlayIMDB {quality} - {format_str} {idx + 1}",
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
                        })
                    
                    if streams:
                        break # Stop hitting endpoints if we secured links
            except:
                pass
                
    return streams
