import os, subprocess, asyncio
from playwright.async_api import async_playwright
import streamlit as st

# Make Playwright download browsers into the app dir (works on Streamlit Cloud)
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")

def ensure_chromium():
    # Install Chromium once per container start. First run may take ~1–2 minutes.
    try:
        subprocess.run(
            ["python", "-m", "playwright", "install", "chromium"],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
    except subprocess.CalledProcessError as e:
        # Log a short snippet in the UI if needed
        st.write("Chromium install output (truncated):")
        st.code((e.stdout or b"").decode(errors="ignore")[-1000:])

async def find_m3u8_runtime(url, wait_seconds=12):
    m3u8s = set()
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36")
        )
        page = await context.new_page()

        def maybe_add(u):
            if u and ".m3u8" in u.lower():
                m3u8s.add(u)

        page.on("request", lambda req: maybe_add(req.url))
        page.on("response", lambda res: maybe_add(res.url))

        await page.goto(url, wait_until="domcontentloaded")

        for sel in ["video", "button:has-text('Play')", "[autoplay]", "[data-play]", ".vjs-big-play-button"]:
            try:
                await page.click(sel, timeout=2000)
            except:
                pass

        await page.wait_for_timeout(wait_seconds * 1000)
        await browser.close()

    ordered = list(m3u8s)
    masters = [u for u in ordered if "master" in u.lower()]
    best = masters[0] if masters else (ordered[0] if ordered else None)
    return best, ordered

# ---------- UI ----------
st.set_page_config(page_title="M3U8 Finder (Playwright)", page_icon="🎯", layout="centered")
st.title("🎯 Master M3U8 Finder — JS-capable (Playwright)")

url = st.text_input("Page URL", placeholder="https://example.com/watch/123")
wait_seconds = st.slider("Listen duration (seconds)", 5, 30, 12)
run = st.button("Find M3U8", type="primary")
st.caption("First run may download Chromium — be patient.")

if run:
    if not url:
        st.warning("Paste a URL first.")
    else:
        with st.spinner("Installing/ensuring Chromium… (first run can take a minute)"):
            ensure_chromium()
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
                    st.code(best, language=None)
                    with st.expander("All .m3u8 URLs seen"):
                        for u in found:
                            st.write(u)
                            
