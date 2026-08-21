import json
import urllib.error
import urllib.parse
import urllib.request

TITLE = "PlayIMDB Scraper"
VERSION = "1.0.0"
DESCRIPTION = "Scraper for PlayIMDB (streamdata.vaplayer.ru) for MegaSource"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# Base API endpoint extracted from the Nuvio JS plugin
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

def get_streams(media_type, media_id, config=None):
    imdb_id = media_id
    season = None
    episode = None
    
    # Parse media_id format (e.g., tt0944947:1:1 for series)
    if ":" in media_id:
        parts = media_id.split(":", 2)
        if len(parts) == 3:
            imdb_id = parts[0]
            season = parts[1]
            episode = parts[2]
        
    # The API expects 'tv' for series
    fetch_type = "tv" if media_type == "series" else "movie"
    
    # Construct the target URL
    url = f"{BASE_API}?id={imdb_id}&type={fetch_type}"
    if fetch_type == "tv" and season and episode:
        url += f"&s={season}&e={episode}"
        
    # Specific headers required by the PlayIMDB API source
    custom_headers = {
        'Origin': 'https://nextgencloudfabric.com',
        'Referer': 'https://nextgencloudfabric.com/'
    }
    
    status, body = _request(url, headers=custom_headers)
    
    streams = []
    if status == 200:
        try:
            data = json.loads(body)
            
            # Verify status and parse stream URLs from the response
            if data.get("data") and data["data"].get("stream_urls"):
                
                # Optionally parse subtitles if the API returns them
                subtitles = []
                if data["data"].get("default_subs"):
                    for sub in data["data"]["default_subs"]:
                        subtitles.append({
                            "id": sub.get("code", ""),
                            "url": sub.get("url", ""),
                            "lang": sub.get("lang", "")
                        })

                # Iterate through all available stream URLs
                for idx, stream_url in enumerate(data["data"]["stream_urls"]):
                    
                    # Basic format parsing (MP4 or HLS)
                    format_str = "MP4" if ".mp4" in stream_url.lower() else "HLS" if ".m3u8" in stream_url.lower() else "Stream"
                    server_name = f"Server {idx + 1} - {format_str}"

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
