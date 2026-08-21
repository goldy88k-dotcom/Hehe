import json
import urllib.error
import urllib.parse
import urllib.request

TITLE = "PlayIMDB Scraper"
VERSION = "1.0.1"
DESCRIPTION = "Scraper for PlayIMDB (vaplayer) for MegaSource"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# TMDB Key extracted from the MegaSource Default scraper
TMDB_API_KEY = "92c1507cc18d85200e7a0b96abb37316"
BASE_API = "https://streamdata.vaplayer.ru/api.php"

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
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except Exception:
        return 0, ""

def imdb_to_tmdb(imdb_id):
    """Converts IMDB ID to TMDB ID using the TMDB API."""
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
    
    # Many VAPlayer integrations expect 'imdb=' instead of 'id='
    # Let's also fetch the TMDB ID in case the API strictly expects TMDB as obfuscated in the original JS
    tmdb_id = imdb_to_tmdb(imdb_id)
    
    # We will prioritize IMDB, but fallback to TMDB if required by the API implementation
    if tmdb_id:
        url = f"{BASE_API}?tmdb={tmdb_id}&type={fetch_type}"
    else:
        url = f"{BASE_API}?imdb={imdb_id}&type={fetch_type}"

    if fetch_type == "tv" and season and episode:
        url += f"&s={season}&e={episode}"
        
    # Extracted headers from Nuvio JS + mandatory X-Requested-With
    custom_headers = {
        'Origin': 'https://nextgencloudfabric.com',
        'Referer': 'https://nextgencloudfabric.com/',
        'X-Requested-With': 'XMLHttpRequest'
    }
    
    status, body = _request(url, headers=custom_headers)
    
    streams = []
    if status == 200:
        try:
            data = json.loads(body)
            
            if data.get("data") and data["data"].get("stream_urls"):
                subtitles = []
                if data["data"].get("default_subs"):
                    for sub in data["data"]["default_subs"]:
                        subtitles.append({
                            "id": sub.get("code", ""),
                            "url": sub.get("url", ""),
                            "lang": sub.get("lang", "")
                        })

                for idx, stream_url in enumerate(data["data"]["stream_urls"]):
                    format_str = "MP4" if ".mp4" in stream_url.lower() else "HLS" if ".m3u8" in stream_url.lower() else "Stream"
                    
                    # Deduce quality if embedded in URL
                    quality = "1080p"
                    if "4k" in stream_url.lower(): quality = "4K"
                    elif "720p" in stream_url.lower(): quality = "720p"
                    
                    server_name = f"Server {idx + 1} - {quality} ({format_str})"

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
                    
                    if subtitles:
                        stream_obj["subtitles"] = subtitles
                        
                    streams.append(stream_obj)
        except (ValueError, TypeError):
            pass
            
    return streams
