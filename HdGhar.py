import json
import urllib.parse
import urllib.request
import traceback

TITLE = "HDGhar Scraper"
VERSION = "2.0.0"
DESCRIPTION = "Dynamic domain fetching scraper for HDGhar"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"

# Your personal TMDB Key
TMDB_API_KEY = "b78ae12f6a9ed6fb82f78f12207a29a9"

def return_error(msg):
    """Uses a real video URL so Stremio actually displays the error message."""
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
    # 1. Try fetching the latest domain from Nuvio's GitHub list
    for repo in ["nuvio-plugin", "nuvio_plugin"]:
        url = f"https://raw.githubusercontent.com/sapariyaneel/{repo}/refs/heads/main/domains.json"
        status, raw = _request(url)
        if status == 200 and raw:
            try:
                domains = json.loads(raw)
                # Look for hdghartv in the Nuvio JSON
                host = domains.get("hdghartv") or domains.get("hdghar")
                if host and host not in hosts:
                    hosts.append(host.rstrip('/'))
            except:
                pass
                
    # 2. Add known fallbacks just in case the JSON is empty
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
                
        # --- TMDB Lookup ---
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
            
        # --- HDGhar Dynamic Search Loop ---
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
                    break # Found the active domain! Exit the loop.
                except Exception:
                    last_error = f"JSON Parse error on {host}"
            else:
                last_error = f"HTTP {s_status} on {host}"
                
        if not working_host or not search_data:
            # If all domains fail (e.g. they all 404), display the exact error in Stremio!
            return return_error(f"All domains failed. Last error: {last_error}")
            
        # --- Process Search Results ---
        movies = search_data.get("movies", [])
        series = search_data.get("series", [])
        all_items = movies + series
        
        target_id = None
        for item in all_items:
            if str(item.get("tmdbId")) == tmdb_id:
                target_id = item.get("_id")
                break
                
        if not target_id:
            return return_error(f"Media searched successfully on {working_host}, but no matching TMDB ID found in results.")
            
        # --- Fetch Media Details ---
        detail_type = "movie" if media_type == "movie" else "series"
        detail_url = f"{working_host}/api/{detail_type}/{target_id}"
        
        d_status, d_body = _request(detail_url, headers={"Referer": working_host + "/"})
        if d_status != 200:
            return return_error(f"Details API Error: HTTP {d_status} on {detail_url}")
            
        try:
            detail_data = json.loads(d_body)
        except Exception:
            return return_error(f"Failed to parse Details JSON from {detail_url}")
            
        # --- Extract Streaming Links ---
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
            return return_error(f"Successfully scraped {working_host}, but no streaming URLs were found inside the JSON data.")
            
        # --- Format Output for Stremio ---
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
                            "Referer": working_host + "/",
                            "Origin": working_host
                        }
                    }
                }
            })
            
        return streams

    except Exception as e:
        return return_error(f"Fatal Python Crash: {str(e)} | {traceback.format_exc()[:100]}")
