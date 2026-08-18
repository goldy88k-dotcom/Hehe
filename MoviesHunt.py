"""
MegaSource Scraper for MoviesHunt (Translated from MoviesHunt.pdf)
"""
import json
import re
import urllib.parse
import urllib.request
import traceback

TITLE = "MoviesHunt"
VERSION = "1.0.1"
DESCRIPTION = "Hollywood & Bollywood Movies via MoviesHunt scraper"
USER_AGENT = "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
TMDB_API_KEY = "439c478a771f35c05022f9feabcca01c"

MOVIESHUNT_BASE = "https://movieshunt.eu.org"

def return_error(msg):
    return [{
        "name": "MOVIESHUNT ERROR",
        "title": str(msg),
        "url": "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/TearsOfSteel.mp4",
        "behaviorHints": {
            "notMyMetadata": True,
            "proxyHeaders": {"request": {}}
        }
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

def get_tmdb_meta(media_id):
    tmdb_id = media_id
    if str(media_id).startswith("tt"):
        find_url = f"https://api.themoviedb.org/3/find/{media_id}?api_key={TMDB_API_KEY}&external_source=imdb_id"
        st, res = _request(find_url)
        if st == 200 and res:
            data = json.loads(res)
            results = data.get("movie_results", [])
            if results:
                tmdb_id = results[0].get("id")
            else:
                return None
        else:
            return None

    details_url = f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={TMDB_API_KEY}"
    st, res = _request(details_url)
    if st != 200 or not res:
        return None
    data = json.loads(res)
    
    return {
        "tmdb_id": tmdb_id,
        "title": data.get("title"),
        "release_date": data.get("release_date", "")
    }

def parse_search_results(html):
    results = []
    # Match entry titles just like the JS plugin
    entries = re.findall(r'<h\d[^>]*class="[^"]*entry-title[^"]*"[^>]*>([\s\S]*?)</h\d>', html, re.IGNORECASE)
    for entry in entries:
        link_match = re.search(r'<a[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>', entry, re.IGNORECASE)
        if link_match:
            url = link_match.group(1)
            if url.startswith('/'):
                url = MOVIESHUNT_BASE + url
            title_clean = re.sub(r'<[^>]+>', '', link_match.group(2)).strip()
            if len(title_clean) > 5:
                results.append({"title": title_clean, "url": url})
    return results

def get_streams(media_type, media_id, config=None):
    try:
        if media_type != "movie":
            return []
            
        meta = get_tmdb_meta(media_id)
        if not meta or not meta.get("title"):
            return return_error(f"Failed to fetch metadata for {media_id}")
            
        movie_title = meta["title"]
        
        # Search site using MoviesHunt query format
        search_query = urllib.parse.quote(movie_title)
        search_url = f"{MOVIESHUNT_BASE}/index.php?s={search_query}"
        
        st, html = _request(search_url, headers={"Referer": f"{MOVIESHUNT_BASE}/"})
        if st != 200 or not html:
            return return_error(f"Search request failed with status {st}")
            
        search_results = parse_search_results(html)
        if not search_results:
            return return_error(f"No search results found for '{movie_title}'")
            
        # Grab the first matching page link
        target_page_url = search_results[0]["url"]
        st, page_html = _request(target_page_url, headers={"Referer": MOVIESHUNT_BASE + "/"})
        
        if st != 200 or not page_html:
            return return_error("Failed to load target movie page.")
            
        # Extract Abhilinks redirect button URL
        abhilinks_match = re.search(r'href="(https://abhilinks\.(?:life|site)/[^"]+)"[^>]*class="btn"[^>]*>', page_html, re.IGNORECASE)
        if not abhilinks_match:
            abhilinks_match = re.search(r'href="(https://abhilinks\.(?:life|site)/[^"]+)"', page_html, re.IGNORECASE)
            
        if not abhilinks_match:
            return return_error("Could not find direct download redirect link.")
            
        redirect_url = abhilinks_match.group(1)
        st, redirect_html = _request(redirect_url, headers={"Referer": target_page_url})
        
        if st != 200 or not redirect_html:
            return return_error("Failed to resolve redirect host.")
            
        # Extract direct bucket or hubcloud links inside the final page
        links = re.findall(r'href="([^"]+)"', redirect_html, re.IGNORECASE)
        valid_streams = []
        
        for link in links:
            if any(domain in link for domain in ["fsl-buckets", "r2.dev", "hubcloud", "workers.dev"]) and not any(x in link for x in ["telegram", "tg://", "pixeldrain"]):
                valid_streams.append(link)
                
        if not valid_streams:
            return return_error("No playable media streams found on final host page.")
            
        results = []
        for idx, stream_url in enumerate(valid_streams[:3]): # Limit to top 3 streams
            results.append({
                "name": TITLE,
                "title": f"MoviesHunt | Direct Stream {idx + 1}",
                "url": stream_url,
                "behaviorHints": {
                    "notMyMetadata": True,
                    "proxyHeaders": {
                        "request": {
                            "User-Agent": USER_AGENT,
                            "Referer": MOVIESHUNT_BASE + "/"
                        }
                    }
                }
            })
            
        return results

    except Exception as e:
        return return_error(f"Fatal Crash: {str(e)}")
