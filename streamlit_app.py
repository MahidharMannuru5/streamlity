import httpx
from urllib.parse import urlparse

# Two realistic browser profiles
BROWSER_PROFILES = [
    {  # Desktop Chrome
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36"),
        "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                   "image/avif,image/webp,*/*;q=0.8"),
        "Accept-Language": "en-US,en;q=0.9",
    },
    {  # Android Chrome
        "User-Agent": ("Mozilla/5.0 (Linux; Android 12; Pixel 6) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Mobile Safari/537.36"),
        "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
        "Accept-Language": "en-US,en;q=0.9",
    },
]

def _referer_for(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}/"

def fetch_text(url: str, timeout: float = 20.0):
    """
    Fetch HTML with realistic headers. Retry across two UA/Accept profiles.
    Also sets Referer to the site root (many sites require it).
    """
    last_err = None
    for hdr in BROWSER_PROFILES:
        headers = {**hdr, "Referer": _referer_for(url)}
        try:
            with httpx.Client(headers=headers, follow_redirects=True, timeout=timeout) as c:
                r = c.get(url)
                # Some sites answer 406 unless Accept matches; try again if so
                if r.status_code == 406:
                    continue
                r.raise_for_status()
                return r.text, str(r.url)
        except Exception as e:
            last_err = e
            continue
    # If we got here, all profiles failed
    raise last_err or RuntimeError("Failed to fetch page")

def looks_like_master(url: str) -> bool:
    """
    Fetch a playlist URL quickly using the same header profiles.
    Some CDNs require a Referer header matching the site.
    """
    for hdr in BROWSER_PROFILES:
        headers = {**hdr, "Referer": _referer_for(url)}
        try:
            with httpx.Client(headers=headers, follow_redirects=True, timeout=8.0) as c:
                r = c.get(url)
                if r.status_code == 406:
                    continue
                r.raise_for_status()
                text = r.text[:200_000]
                return "#EXT-X-STREAM-INF" in text
        except Exception:
            continue
    return False
