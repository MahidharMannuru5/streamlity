import asyncio
import shutil
from playwright.async_api import async_playwright
import streamlit as st

st.set_page_config(page_title="M3U8 Finder (Playwright)", page_icon="🎯", layout="centered")
st.title("🎯 Master M3U8 Finder — JS-capable (Playwright)")

def chromium_path():
    # Use system Chromium installed via packages.txt
    return shutil.which("chromium") or shutil.which("chromium-browser") or "/usr/bin/chromium"

async def find_m3u8_runtime(url: str, wait_seconds: int = 12):
    """Open the page in headless Chromium, watch for .m3u8 requests, pick best."""
    m3u8s = []
    seen = set()

    def maybe_add(u: str):
        if not u:
            return
        if ".m3u8" not in u.lower():
            return
        if u in seen:
            return
        seen.add(u)
        m3u8s.append(u)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=chromium_path(),   # <-- system chromium
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36")
        )
        page = await context.new_page()

        page.on("request", lambda req: maybe_add(req.url))
        page.on("response", lambda res: maybe_add(res.url))

        await page.goto(url, wait_until="domcontentloaded")

        # Try common play triggers (root + iframes)
        common_selectors = ["video", ".vjs-big-play-button", "button:has-text('Play')", "[autoplay]", "[data-play]"]
        async def try_clicks(frame):
            for sel in common_selectors:
                try:
                    await frame.click(sel, timeout=1200)
                except:
                    pass

        await try_clicks(page)
        for f in page.frames:
            try:
                await try_clicks(f)
            except:
                pass

        # brief idle + wait window for network activity
        try:
            await page.wait_for_load_state("networkidle", timeout=4000)
        except:
            pass
        await page.wait_for_timeout(wait_seconds * 1000)

        await browser.close()

    # Pick "best": prefer URL containing "master", else first seen
    masters = [u for u in m3u8s if "master" in u.lower()]
    best = masters[0] if masters else (m3u8s[0] if m3u8s else None)
    return best, m3u8s

# ----- UI -----
url = st.text_input("Page URL", placeholder="https://example.com/watch/123")
wait_seconds = st.slider("Listen duration (seconds)", 5, 30, 12)
run = st.button("Find M3U8", type="primary")

st.caption("This uses the system Chromium installed via packages.txt. First run after deploy may take ~1–2 min to build the container.")

st.divider()

if run:
    if not url:
        st.warning("Paste a URL first.")
    else:
        with st.spinner("Opening headless browser & sniffing network…"):
            try:
                best, found = asyncio.run(find_m3u8_runtime(url, wait_seconds=wait_seconds))
            except Exception as e:
                st.error(f"Playwright error: {e}")
            else:
                if not found:
                    st.warning("No .m3u8 requests observed. Site may block headless or use DRM.")
                else:
                    st.success("Done")
                    st.subheader("Best (picked from requests)")
                    st.code(best or "", language=None)
                    st.download_button("Download best URL", data=(best or ""), file_name="m3u8.txt", mime="text/plain")
                    with st.expander("All .m3u8 URLs seen"):
                        for u in found:
                            st.write(u)
                            
