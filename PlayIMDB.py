"""
MegaSource Scraper for PlayIMDb
Converts PlayIMDb Nuvio provider (streamdata.vaplayer.ru) to Python for MegaSource
"""
import json
import urllib.parse
import urllib.request
import traceback

TITLE = "PlayIMDb"
VERSION = "1.0.0"
DESCRIPTION = "High-Speed Direct Streaming via VAPlayer API"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# Using the public Nuvio TMDB API Key
TMDB_API_KEY = "1865f43a0549ca50d341dd9ab8b29f49"
BASE_API = "https://streamdata.vaplayer.ru/api.php"

HEADERS = {
    "User-Agent": USER_AGENT,
    "Origin": "https://nextgencloudfabric.com",
    "Referer": "https://nextgencloudfabric.com/"
}

# --- Error Handling Helper ---

def return_error(msg):
    """Returns an error stream visible inside Stremio."""
    return [{
        "name": "PLAYIMDB ERROR",
        "title": str(msg),
        "url": "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/TearsOfSteel.mp4",
        "behaviorHints": {
            "notMyMetadata": True,
            "proxyHeaders": {"request": {}}
        }
    }]

# --- HTTP Request Utility ---

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

# --- TMDB Metadata Lookup ---

def get_tmdb_id(imdb_id, media_type):
    """Converts IMDB ID (tt...) to TMDB ID."""
    if not str(imdb_id).startswith("tt"):
        return imdb_id

    find_url = f"https://api.themoviedb.org/3/find/{imdb_id}?api_key={TMDB_API_KEY}&external_source=imdb_id"
    status, body = _request(find_url)
    if status != 200 or not body:
        return None

    try:
        data = json.loads(body)
        results = data.get("tv_results") if media_type == "series" else data.get("movie_results")
        if results and len(results) > 0:
            return results[0].get("id")
    except Exception:
        pass

    return None

# --- Quality & Audio Parsing ---

def parse_metadata(file_name):
    """Parses file_name string to determine resolution and audio track."""
    fn = str(file_name).lower()

    # Resolution
    if "4k" in fn or "2160p" in fn or "uhd" in fn:
        quality = "4K UHD"
        badge = "4K"
        rank = 4
    elif "1080p" in fn or "fhd" in fn:
        quality = "1080p FHD"
        badge = "1080p"
        rank = 3
    elif "720p" in fn or "hd" in fn:
        quality = "720p HD"
        badge = "720p"
        rank = 2
    else:
        quality = "SD"
        badge = "SD"
        rank = 1

    # Audio
    if "dual" in fn:
        audio = "Dual-Audio"
    elif "multi" in fn:
        audio = "Multilingual"
    elif "hindi" in fn:
        audio = "Hindi-Audio"
    elif "english" in fn:
        audio = "English-Audio"
    else:
        audio = "Original-Audio"

    return quality, badge, audio, rank

# --- Main Entry Point ---

def get_streams(media_type, media_id, config=None):
    try:
        imdb_id = media_id
        season = episode = None
        if ":" in media_id:
            parts = media_id.split(":", 2)
            imdb_id = parts[0]
            if len(parts) == 3:
                season = parts[1]
                episode = parts[2]

        # 1. Convert IMDB ID -> TMDB ID
        tmdb_id = get_tmdb_id(imdb_id, media_type)
        if not tmdb_id:
            return return_error(f"Could not resolve TMDB ID for {imdb_id}")

        # 2. Build PlayIMDb VAPlayer API URL
        api_type = "tv" if media_type == "series" else "movie"
        api_url = f"{BASE_API}?id={tmdb_id}&type={api_type}"
        if media_type == "series" and season and episode:
            api_url += f"&season={season}&episode={episode}"

        # 3. Fetch Stream Payload
        status, body = _request(api_url, headers=HEADERS)
        if status != 200 or not body:
            return return_error(f"VAPlayer API Error: HTTP {status}")

        try:
            payload = json.loads(body)
        except Exception:
            return return_error("Failed to parse VAPlayer JSON response.")

        # Check API status code (200 or 0xc8)
        status_code = payload.get("status_code")
        status_text = str(payload.get("status", "")).lower()
        if status_code != 200 and status_code != 0xc8 and status_text != "success":
            return return_error(f"VAPlayer API returned non-success status: {status_code}")

        data_obj = payload.get("data", {})
        stream_urls = data_obj.get("stream_urls", [])
        if not stream_urls:
            return return_error("No stream URLs found in PlayIMDb response.")

        file_name = data_obj.get("file_name", "")
        quality, badge, audio, rank = parse_metadata(file_name)

        # 4. Format Subtitles (if present)
        subtitles = []
        raw_subs = payload.get("default_subs", [])
        if isinstance(raw_subs, list):
            for sub in raw_subs:
                sub_url = sub.get("url")
                if sub_url:
                    subtitles.append({
                        "id": sub.get("code") or sub.get("lang", "sub"),
                        "url": sub_url,
                        "lang": sub.get("lang", "Subtitle")
                    })

        # 5. Format Streams for Stremio
        raw_results = []
        for index, stream_url in enumerate(stream_urls):
            server_name = f"Server {index + 1}"
            fmt_type = "M3U8" if ".m3u8" in stream_url.lower() else "MP4"

            stream_card = {
                "name": f"{TITLE} [{badge}]",
                "title": f"🎬 {quality} | 🔊 {audio}\n🖥️ {server_name} ({fmt_type})",
                "url": stream_url,
                "behaviorHints": {
                    "notMyMetadata": True,
                    "proxyHeaders": {
                        "request": {
                            "User-Agent": USER_AGENT,
                            "Referer": "https://nextgencloudfabric.com/",
                            "Origin": "https://nextgencloudfabric.com/",
                            "Accept": "*/*",
                            "Accept-Language": "en-US,en;q=0.9"
                        }
                    }
                }
            }

            if subtitles:
                stream_card["subtitles"] = subtitles

            raw_results.append({
                "rank": rank,
                "stream": stream_card
            })

        raw_results.sort(key=lambda x: x["rank"], reverse=True)
        return [item["stream"] for item in raw_results]

    except Exception as e:
        return return_error(f"Fatal Crash: {str(e)} | {traceback.format_exc()[:100]}")
