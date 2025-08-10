import re
from urllib.parse import urljoin, urlparse
import httpx
import streamlit as st

st.set_page_config(page_title="M3U8 Finder", page_icon="🎯", layout="centered")

# ---------- your helpers (unchanged) ----------
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
    last_err = None
    for hdr in BROWSER_PROFILES:
        headers = {**hdr, "Referer": _referer_for(url)}
        try:
            with httpx.Client(headers=headers, follow_redirects=True, timeout=timeout) as c:
                r = c.get(url)
                if r.status_code == 406:
                    continue
                r.raise_for_status()
                return r.text, str(r.url)
        except Exception as e:
            last_err = e
            continue
    raise last_err or RuntimeError("Failed to fetch page")

def looks_like_master(url: str) -> bool:
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
# ----------------------------------------------

# Simple finders (requests-only)
M3U8_ABS = re.compile(r'https?://[^\s"\'<>]+\.m3u8(?:\?[^\s"\'<>]*)?', re.I)
SRC_ANY  = re.compile(r'''src\s*=\s*["']([^"']+)["']''', re.I)

def find_m3u8_in_html(html: str, base: str):
    out = []
    out += M3U8_ABS.findall(html)
    for m in SRC_ANY.finditer(html):
        val = m.group(1)
        if ".m3u8" in val.lower():
            out.append(urljoin(base, val))
    return list(dict.fromkeys(out))  # dedupe preserve order

def find_iframes(html: str, base: str):
    frames = []
    for m in SRC_ANY.finditer(html):
        val = m.group(1)
        ctx = html[max(0, m.start()-20):m.start()+20].lower()
        if "<iframe" in ctx:
            frames.append(urljoin(base, val))
    return list(dict.fromkeys(frames))

def choose_best(candidates: list[str]) -> str | None:
    if not candidates:
        return None
    masters = [u for u in candidates if "master" in u.lower()]
    for u in masters + candidates:
        if looks_like_master(u):
            return u
    return candidates[0]

def find_best_with_iframes(page_url: str, iframe_depth: int = 1, max_iframes: int = 8):
    html, final_url = fetch_text(page_url)
    candidates = find_m3u8_in_html(html, final_url)

    frontier = find_iframes(html, final_url)[:max_iframes]
    seen = set()
    for _ in range(iframe_depth):
        nxt = []
        for f in frontier:
            if f in seen: continue
            seen.add(f)
            try:
                ihtml, ifinal = fetch_text(f, timeout=12.0)
            except Exception:
                continue
            candidates += find_m3u8_in_html(ihtml, ifinal)
            nxt += find_iframes(ihtml, ifinal)[:max_iframes]
        frontier = nxt

    candidates = list(dict.fromkeys(candidates))
    return choose_best(candidates), candidates

# ---------------- UI ----------------
st.title("🎯 Master M3U8 Finder (Streamlit)")

url = st.text_input("Page URL", placeholder="https://example.com/watch/123")
col1, col2 = st.columns([1,1])
with col1:
    depth = st.selectbox("Iframe depth", [0,1,2], index=1)
with col2:
    run = st.button("Find M3U8", type="primary")

st.divider()

if run:
    if not url:
        st.warning("Paste a URL first.")
    else:
        try:
            with st.spinner("Scanning (requests-only)…"):
                best, candidates = find_best_with_iframes(url, iframe_depth=int(depth))
        except Exception as e:
            st.error(f"Fetch failed: {e}")
        else:
            if not candidates:
                st.warning("No .m3u8 found in static HTML/iframes. This site may build the URL via JavaScript at runtime.")
            else:
                st.success("Done")
                st.subheader("Best (master) URL")
                st.code(best or candidates[0], language=None)
                with st.expander("All candidates"):
                    for u in candidates:
                        st.write(u)

st.caption("Tip: If this misses JS-built links, deploy a Playwright version on Render/Railway.")
