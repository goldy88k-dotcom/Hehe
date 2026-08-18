"""
MegaSource Scraper for Cineby (v4 - Endpoint Fixed)
"""
import base64
import json
import urllib.parse
import urllib.request
import traceback

TITLE = "Cineby"
VERSION = "1.0.4"
DESCRIPTION = "Multi-server movie and TV streaming from Videasy network"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Referer": "https://www.cineby.at/",
    "Origin": "https://www.cineby.at/"
}
TMDB_API_KEY = "1865f43a0549ca50d341dd9ab8b29f49"

# --- Error Handling ---

def return_error(msg):
    """Forces an error stream to appear so MegaSource doesn't fail silently."""
    return [{
        "name": "CINEBY ERROR",
        "title": str(msg),
        # Dummy video so Stremio/MegaSource doesn't reject the stream format
        "url": "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/TearsOfSteel.mp4",
        "behaviorHints": {
            "notMyMetadata": True,
            "proxyHeaders": {"request": {}}
        }
    }]

# --- HTTP & API Utilities ---

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

def get_api_host():
    # Try both potential GitHub URL variations for domains.json
    for repo in ["nuvio-plugin", "nuvio_plugin"]:
        url = f"https://raw.githubusercontent.com/sapariyaneel/{repo}/refs/heads/main/domains.json"
        status, raw = _request(url)
        if status == 200 and raw:
            try:
                domains = json.loads(raw)
                host = domains.get("speedracelight")
                if host:
                    return host.rstrip('/')
            except:
                pass
    return "https://api.speedracelight.com"

def get_tmdb_meta(media_id, media_type):
    tmdb_id = media_id
    if str(media_id).startswith("tt"):
        find_url = f"https://api.themoviedb.org/3/find/{media_id}?api_key={TMDB_API_KEY}&external_source=imdb_id"
        st, res = _request(find_url)
        if st == 200 and res:
            data = json.loads(res)
            results = data.get("tv_results") if media_type == "series" else data.get("movie_results")
            if results:
                tmdb_id = results[0].get("id")
            else:
                return None
        else:
            return None

    endpoint = "tv" if media_type == "series" else "movie"
    details_url = f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}?api_key={TMDB_API_KEY}&append_to_response=external_ids"
    st, res = _request(details_url)
    if st != 200 or not res:
        return None
    data = json.loads(res)
    
    title = data.get("name") if media_type == "series" else data.get("title")
    rel_date = data.get("first_air_date") if media_type == "series" else data.get("release_date")
    year = rel_date[:4] if rel_date else ""
    ext_ids = data.get("external_ids", {})
    imdb_id = ext_ids.get("imdb_id") or data.get("imdb_id", "")
    
    return {"tmdb_id": tmdb_id, "title": title, "year": year, "imdb_id": imdb_id}

# --- Cineby Decryption Cipher ---

def _fmix32(h):
    h = h & 0xFFFFFFFF
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & 0xFFFFFFFF
    h ^= h >> 16
    return h & 0xFFFFFFFF

def _rotl32(x, r):
    x = x & 0xFFFFFFFF
    r = r & 0x1F
    if r == 0:
        return x
    return ((x << r) | (x >> (32 - r))) & 0xFFFFFFFF

def _fnv1a32(data_bytes):
    h = 0x811C9DC5
    for b in data_bytes:
        h = ((h ^ b) * 0x1000193) & 0xFFFFFFFF
    return _fmix32(h)

def _make_keystream_state(seed_str, tmdb_id):
    slots = [None] * 61
    seed_bytes = seed_str.encode('utf-8')
    fnv = _fnv1a32(seed_bytes)
    fmix_tmdb = _fmix32((int(tmdb_id) ^ 0x9E3779B9) & 0xFFFFFFFF)
    acc = _fmix32(fnv ^ fmix_tmdb) & 0xFFFFFFFF

    for i in range(8):
        idx = acc % 61
        acc = _rotl32((acc + 0x9E3779B9) & 0xFFFFFFFF, 7 + (7 & i))
        slots[idx] = (acc ^ _fmix32(acc)) & 0xFFFFFFFF
        acc = _fmix32((acc + idx) & 0xFFFFFFFF)

    return {"slots": slots, "acc": _fmix32((0xA5A5A5A5 ^ acc) & 0xFFFFFFFF)}

def _next_keystream_word(state, counter):
    slots = state["slots"]
    acc = state["acc"]
    idx = acc % 61
    
    is_defined = slots[idx] is not None
    slot_val = slots[idx] if is_defined else 0
    
    imul_val = (0x9E3779B9 * (counter + 1)) & 0xFFFFFFFF
    mixed = (slot_val ^ imul_val) & 0xFFFFFFFF
    
    if is_defined:
        combined = (acc | mixed) & 0xFFFFFFFF
    else:
        combined = (acc ^ mixed) & 0xFFFFFFFF
        
    r1 = idx & 0x1F
    r2 = (idx * 7) & 0x1F
    
    rot1 = _rotl32((combined + acc) & 0xFFFFFFFF, r1)
    rot2 = _rotl32(acc, r2)
    
    word = _fmix32(((rot1 ^ rot2) + 0x9E3779B9) & 0xFFFFFFFF)
    slots[idx] = word
    state["acc"] = word
    return word

def _generate_keystream(seed_str, tmdb_id, length):
    state = _make_keystream_state(seed_str, tmdb_id)
    keystream = bytearray(length)
    byte_idx = 0
    word_idx = 0
    
    while byte_idx < length:
        word = _next_keystream_word(state, word_idx)
        word_idx += 1
        
        keystream[byte_idx] = word & 0xFF
        byte_idx += 1
        if byte_idx < length:
            keystream[byte_idx] = (word >> 8) & 0xFF
            byte_idx += 1
        if byte_idx < length:
            keystream[byte_idx] = (word >> 16) & 0xFF
            byte_idx += 1
        if byte_idx < length:
            keystream[byte_idx] = (word >> 24) & 0xFF
            byte_idx += 1
            
    return keystream

def decrypt_sources_payload(enc_str, seed_str, tmdb_id):
    padding = '=' * (-len(enc_str) % 4)
    b64_str = enc_str.replace('-', '+').replace('_', '/') + padding
    data_bytes = base64.b64decode(b64_str)
    
    keystream = _generate_keystream(seed_str, tmdb_id, len(data_bytes))
    decrypted = bytearray(len(data_bytes))
    for i in range(len(data_bytes)):
        decrypted[i] = data_bytes[i] ^ keystream[i]
        
    if decrypted[:4] != b'mvm1':
        raise ValueError("Decryption failed: invalid magic header")
        
    return decrypted[4:].decode('utf-8', errors='replace')

# --- Main Scraper Entry Point ---

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
                
        meta = get_tmdb_meta(imdb_id, media_type)
        if not meta or not meta.get("tmdb_id"):
            return return_error(f"Failed to fetch TMDB Meta for {imdb_id}")
            
        tmdb_id = meta["tmdb_id"]
        api_host = get_api_host()
        
        # 1. Fetch encryption seed
        seed_status, seed_res = _request(f"{api_host}/seed?mediaId={tmdb_id}", headers=HEADERS)
        if seed_status != 200:
            return return_error(f"Seed API Error {seed_status} at {api_host}")
            
        try:
            seed = json.loads(seed_res).get("seed")
        except Exception:
            return return_error(f"JSON Parse Error on Seed: {seed_res[:50]}")
            
        if not seed:
            return return_error("Seed key was empty.")
            
        # 2. Fetch encrypted sources payload
        params = urllib.parse.urlencode({
            "title": meta.get("title", ""),
            "mediaType": "tv" if media_type == "series" else "movie",
            "year": meta.get("year", ""),
            "episodeId": str(episode if media_type == "series" and episode else 1),
            "seasonId": str(season if media_type == "series" and season else 1),
            "tmdbId": str(tmdb_id),
            "imdbId": meta.get("imdb_id", ""),
            "enc": "2",
            "seed": seed
        })
        
        # FIXED ENDPOINT: /cdn/sources-with-title
        sources_url = f"{api_host}/cdn/sources-with-title?{params}"
        sources_status, sources_enc = _request(sources_url, headers=HEADERS)
        
        if sources_status != 200:
            return return_error(f"Sources API Error {sources_status}. URL: {sources_url[:60]}...")
            
        # 3. Decrypt payload
        try:
            decrypted_json_str = decrypt_sources_payload(sources_enc.strip(), seed, tmdb_id)
            payload = json.loads(decrypted_json_str)
        except Exception as decrypt_err:
            return return_error(f"Decryption Crash: {decrypt_err}")
            
        sources = payload.get("sources", [])
        if not sources:
            return return_error("Decrypted successfully, but no streams were inside the payload.")
            
        results = []
        for src in sources:
            stream_url = src.get("url")
            if stream_url:
                quality = src.get("quality", "HD")
                results.append({
                    "name": TITLE,
                    "title": f"Cineby | {quality}",
                    "url": stream_url,
                    "behaviorHints": {
                        "notMyMetadata": True,
                        "proxyHeaders": {
                            "request": {
                                "User-Agent": USER_AGENT,
                                "Referer": "https://www.cineby.at/",
                                "Origin": "https://www.cineby.at/"
                            }
                        }
                    }
                })
                
        return results

    except Exception as e:
        return return_error(f"Fatal Crash: {str(e)} | {traceback.format_exc()[:100]}")



