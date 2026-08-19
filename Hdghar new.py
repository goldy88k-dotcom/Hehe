import json
import urllib.parse
import urllib.request
import traceback

TITLE = "HDGhar"
VERSION = "2.0.3"
DESCRIPTION = "Dynamic domain scraper for HDGhar with resolution badges"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"

# Public Nuvio TMDB Key (From Cineby)
TMDB_API_KEY = "1865f43a0549ca50d341dd9ab8b29f49"


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
    req_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*"
    }
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

def get_dynamic_hosts():
    hosts = []
    # Fetch from Nuvio's domains.json to guarantee long-term stability
    for repo in ["nuvio-plugin", "nuvio_plugin"]:
        url = f"https://raw.githubusercontent.com/sapariyaneel/{repo}/refs/heads/main/domains.json"
        status, raw = _request(url)
        if status == 200 and raw:
            try:
                domains = json.loads(raw)
                host = domains.get("hdghartv") or domains.get("hdghar")
                if host and host not in hosts:
                    hosts.append(host.rstrip('/'))
            except:
                pass
    
    # Standard fallbacks
    fallbacks = [
        "https://hdghartv.cc",
        "https://hdghartv.com.pk",
        "https://hdghartv.net",
        "https://api.hdghartv.cc",
        "https://hdghar.tv"
    ]
    for fb in fallbacks:
        if fb not in hosts:
            hosts.append(fb)
    return hosts

def parse_stream_info(link):
    """Deep search across all keys to accurately extract quality and audio details."""
    quality_raw = str(link.get("quality", ""))
    name_raw = str(link.get("name", ""))
    url_raw = str(link.get("url", ""))
    res_raw = str(link.get("resolution", ""))
    
    # Combine all fields to catch resolution tags embedded anywhere in the metadata
    full_text = f"{quality_raw} {name_raw} {res_raw} {url_raw}".lower()
    
    rank = 1
    quality = "HD"
    
    if "2160p" in full_text or "4k" in full_text or "uhd" in full_text:
        quality = "4K 2160p"
        rank = 4
    elif "1080p" in full_text or "fhd" in full_text:
        quality = "1080p"
        rank = 3
    elif "720p" in full_text or "hd" in full_text:
        quality = "720p"
        rank = 2
    elif "480p" in full_text or "sd" in full_text:
        quality = "480p"
        rank = 1
    elif quality_raw:
        quality = quality_raw.upper()
        
    audio = "Dual-Audio"
    if ("hindi" in full_text or "hin" in full_text) and not ("multi" in full_text or "dual" in full_text):
        audio = "Hindi"
    elif "english" in full_text or "eng" in full_text:
        audio = "English"
        
    return quality, audio, rank

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
                
        # 1. TMDB Lookup
        find_url = f"https://api.themoviedb.org/3/find/{imdb_id}?api_key={TMDB_API_KEY}&external_source=imdb_id"
        status, body = _request(find_url)
        
        if status != 200:
            return return_error(f"TMDB Error {status}: Failed to convert IMDB ID.")
            
        try:
            data = json.loads(body)
        except Exception:
            return return_error("Failed to parse TMDB JSON response.")
            
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
            return return_error("Media found, but TMDB returned no title or ID.")
            
        # 2. HDGhar Dynamic Search
        hosts = get_dynamic_hosts()
        search_data = None
        working_host = None
        last_error = ""
        
        encoded_title = urllib.parse.quote(title, safe="")
        
        for host in hosts:
            search_url = f"{host}/api/search?q={encoded_title}&type=all&page=1"
            headers = {"Referer": host + "/", "Origin": host}
            
            s_status, s_body = _request(search_url, headers=headers)
            if s_status == 200:
                try:
                    search_data = json.loads(s_body)
                    working_host = host
                    break
                except Exception:
                    last_error = f"JSON Parse error on {host}"
            else:
                last_error = f"HTTP {s_status} on {host}"
                
        if not working_host or not search_data:
            return return_error(f"All domains failed. Last error: {last_error}")
            
        movies = search_data.get("movies", [])
        series = search_data.get("series", [])
        all_items = movies + series
        
        target_item = None
        for item in all_items:
            if str(item.get("tmdbId")) == tmdb_id:
                target_item = item
                break
                
        if not target_item:
            return return_error(f"Media searched successfully on {working_host}, but no matching TMDB ID found.")
            
        candidates = [c for c in [target_item.get("_id"), target_item.get("url"), target_item.get("slug")] if c]
            
        # 3. Multi-Path Details Fetch
        paths_to_try = []
        if media_type == "movie":
            for c in candidates:
                paths_to_try.extend([f"/api/movies/public/{c}", f"/api/movie/public/{c}", f"/api/movies/{c}"])
        else:
            for c in candidates:
                paths_to_try.extend([f"/api/series/public/{c}", f"/api/tv/public/{c}", f"/api/series/{c}"])
            
        detail_data = None
        working_detail_url = ""
        
        for path in paths_to_try:
            detail_url = f"{working_host}{path}"
            d_status, d_body = _request(detail_url, headers={"Referer": working_host + "/"})
            if d_status == 200:
                try:
                    detail_data = json.loads(d_body)
                    working_detail_url = detail_url
                    break
                except Exception:
                    pass
                    
        if not detail_data:
            return return_error(f"Details API 404: Tried {paths_to_try[:3]} and all failed.")
            
        # 4. Extract Streaming Links
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
            return return_error(f"Scraped {working_detail_url}, but no streaming URLs found.")
            
        # 5. Format Output & Attach Badges
        raw_streams = []
        for link in streaming_links:
            url = link.get("url")
            if not url:
                continue
                
            link_name = link.get("name", "")
            quality, audio, rank = parse_stream_info(link)
            
            # Displays quality right on the primary stream button tag!
            stream_name = f"{TITLE} [{quality}]"
            
            # Formats detail line
            stream_title = f"🎬 {quality} | 🔊 {audio}"
            if link_name:
                stream_title += f"\n📄 {link_name}"
                
            raw_streams.append({
                "rank": rank,
                "stream": {
                    "name": stream_name,
                    "title": stream_title,
                    "url": url,
                    "behaviorHints": {
                        "notMyMetadata": True,
                        "proxyHeaders": {
                            "request": {
                                "User-Agent": USER_AGENT,
                                "Referer": working_host + "/",
                                "Origin": working_host
                            }
                        }
                    }
                }
            })
            
        # Sort streams so 4K / 1080p appear at the top
        raw_streams.sort(key=lambda x: x["rank"], reverse=True)
        return [item["stream"] for item in raw_streams]

    except Exception as e:
        return return_error(f"Fatal Python Crash: {str(e)} | {traceback.format_exc()[:100]}")
