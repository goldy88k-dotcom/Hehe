"""
MegaSource Scraper for PlayIMDb (v1.0.3 - X-Ray Mode)
Converts PlayIMDb Nuvio provider to Python for MegaSource
"""
import json
import urllib.parse
import urllib.request
import traceback

TITLE = "PlayIMDb"
VERSION = "1.0.3"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

TMDB_API_KEY = "1865f43a0549ca50d341dd9ab8b29f49"
BASE_API = "https://streamdata.vaplayer.ru/api.php"

HEADERS = {
    "User-Agent": USER_AGENT,
    "Origin": "https://nextgencloudfabric.com",
    "Referer": "https://nextgencloudfabric.com/",
    "Accept": "application/json, text/plain, */*"
}

def return_error(msg):
    return [{
        "name": "PLAYIMDB DEBUG",
        "title": str(msg),
        "url": "http://127.0.0.1/debug.mp4",
        "behaviorHints": {"notMyMetadata": True}
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

def get_tmdb_id(imdb_id, media_type):
    if not str(imdb_id).startswith("tt"):
        return imdb_id
    url = f"https://api.themoviedb.org/3/find/{imdb_id}?api_key={TMDB_API_KEY}&external_source=imdb_id"
    st, bd = _request(url)
    if st == 200 and bd:
        try:
            data = json.loads(bd)
            res = data.get("tv_results") if media_type == "series" else data.get("movie_results")
            if res and len(res) > 0:
                return str(res[0].get("id"))
        except:
            pass
    return None

def parse_metadata(file_name):
    fn = str(file_name).lower()
    if "4k" in fn or "2160p" in fn or "uhd" in fn:
        return "4K UHD", "4K", 4
    elif "1080p" in fn or "fhd" in fn:
        return "1080p FHD", "1080p", 3
    elif "720p" in fn or "hd" in fn:
        return "720p HD", "720p", 2
    return "SD", "SD", 1

def parse_audio(file_name):
    fn = str(file_name).lower()
    if "dual" in fn: return "Dual-Audio"
    if "multi" in fn: return "Multilingual"
    if "hindi" in fn: return "Hindi-Audio"
    if "english" in fn: return "English-Audio"
    return "Original-Audio"

def get_streams(media_type, media_id, config=None):
    try:
        imdb_id = media_id
        season = episode = None
        if ":" in media_id:
            parts = media_id.split(":", 2)
            imdb_id, season, episode = parts[0], parts[1], parts[2]

        # 1. Convert IMDB to TMDB
        tmdb_id = get_tmdb_id(imdb_id, media_type)
        if not tmdb_id:
            return return_error(f"Failed to find TMDB ID for {imdb_id}")

        api_type = "tv" if media_type == "series" else "movie"
        
        # 2. Build URL with correct &s= and &e= params!
        api_url = f"{BASE_API}?id={tmdb_id}&type={api_type}"
        if media_type == "series" and season and episode:
            api_url += f"&s={season}&e={episode}"

        status, body = _request(api_url, headers=HEADERS)
        if status != 200 or not body:
            return return_error(f"HTTP Error {status} on {api_url}")

        try:
            payload = json.loads(body)
        except Exception:
            return return_error("Failed to parse VAPlayer JSON response.")

        data_obj = payload.get("data", {}) if isinstance(payload, dict) else {}
        stream_urls = data_obj.get("stream_urls", []) if isinstance(data_obj, dict) else []

        if not stream_urls:
            # THIS PRINTS THE EXACT SERVER RESPONSE TO YOUR SCREEN
            debug_text = json.dumps(payload)[:250]
            return return_error(f"No URLs found.\nURL: {api_url}\nAPI Said: {debug_text}")

        file_name = data_obj.get("file_name", "")
        quality, badge, rank = parse_metadata(file_name)
        audio = parse_audio(file_name)

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
                            "Origin": "https://nextgencloudfabric.com/"
                        }
                    }
                }
            }
            raw_results.append({"rank": rank, "stream": stream_card})

        raw_results.sort(key=lambda x: x["rank"], reverse=True)
        return [item["stream"] for item in raw_results]

    except Exception as e:
        return return_error(f"Fatal Crash: {str(e)} | {traceback.format_exc()[:100]}")
