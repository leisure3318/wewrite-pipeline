#!/usr/bin/env python3
"""
Generate images via gemini.google.com using Playwright + Netscape cookies.

Usage:
    python3 gemini_image_gen.py <prompt_file> <output_path> [options]

Options:
    --cookies <file>    Netscape cookies.txt (default: ~/Downloads/gemini.google.com_cookies.txt)
    --headless          Run headless (default: visible browser)
    --timeout <sec>     Wait timeout for image (default: 90)

The prompt file can be a plain .txt or a markdown file with YAML frontmatter
(frontmatter is stripped automatically).
"""

import argparse
import asyncio
import http.cookiejar
import re
import sys
from pathlib import Path

DEFAULT_COOKIES = Path.home() / "Downloads" / "gemini.google.com_cookies.txt"
GEMINI_URL = "https://gemini.google.com/app"


def load_netscape_cookies(path: str) -> list[dict]:
    """Convert Netscape cookies.txt → Playwright context format."""
    cj = http.cookiejar.MozillaCookieJar()
    cj.load(path, ignore_discard=True, ignore_expires=True)
    result = []
    for c in cj:
        entry = {
            "name": c.name,
            "value": c.value,
            "domain": c.domain,
            "path": c.path,
            "secure": bool(c.secure),
            "httpOnly": False,
            "sameSite": "Lax",
        }
        if c.expires:
            entry["expires"] = c.expires
        result.append(entry)
    return result


def read_prompt(prompt_file: str) -> str:
    """Read prompt from file, stripping YAML frontmatter if present."""
    content = Path(prompt_file).read_text(encoding="utf-8")
    if content.startswith("---"):
        m = re.match(r"^---\n.*?\n---\n*", content, re.DOTALL)
        if m:
            content = content[m.end():]
    return content.strip()


async def generate(prompt: str, output: str, cookies_file: str, headless: bool, timeout: int) -> bool:
    try:
        from playwright.async_api import async_playwright, TimeoutError as PWTimeout
    except ImportError:
        print("[gemini] ERROR: playwright not installed. Run: pip install playwright && playwright install chromium")
        return False

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cookies = load_netscape_cookies(cookies_file)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        await ctx.add_cookies(cookies)
        page = await ctx.new_page()

        print(f"[gemini] Opening {GEMINI_URL} ...")
        try:
            await page.goto(GEMINI_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"[gemini] ERROR: Failed to load Gemini: {e}")
            await browser.close()
            return False

        await page.wait_for_timeout(3000)

        # Find input field — try multiple selectors across Gemini UI versions
        input_selectors = [
            'div[contenteditable="true"][role="textbox"]',
            'rich-textarea div[contenteditable="true"]',
            'div[contenteditable="true"]',
            'textarea',
        ]

        input_el = None
        for sel in input_selectors:
            try:
                el = page.locator(sel).first
                await el.wait_for(state="visible", timeout=5000)
                input_el = el
                print(f"[gemini] Input found via: {sel}")
                break
            except PWTimeout:
                continue

        if input_el is None:
            await page.screenshot(path="/tmp/gemini-no-input.png")
            print("[gemini] ERROR: Input field not found. Screenshot: /tmp/gemini-no-input.png")
            print("[gemini] Hint: cookies may have expired. Re-export from browser.")
            await browser.close()
            return False

        # Clear and type prompt
        await input_el.click()
        await input_el.fill("")
        await input_el.type(prompt[:4000], delay=5)  # cap at 4000 chars, Gemini limit
        await page.wait_for_timeout(300)
        await page.keyboard.press("Enter")
        print(f"[gemini] Prompt submitted ({min(len(prompt), 4000)} chars). Waiting up to {timeout}s...")

        # Poll for generated image
        img_selectors = [
            # Gemini image response containers
            'div[data-response-id] img[src^="blob:"]',
            'div[data-response-id] img[src^="https://"]',
            'model-response img[src]',
            # Generic fallback: any new large image in the response area
            'div[jsname] img[width][height]',
        ]

        found_img = None
        t0 = asyncio.get_event_loop().time()
        dots = 0
        while (asyncio.get_event_loop().time() - t0) < timeout:
            for sel in img_selectors:
                try:
                    imgs = await page.query_selector_all(sel)
                    # Filter: skip tiny icons and UI elements
                    for img in imgs:
                        w = await img.get_attribute("width")
                        src = await img.get_attribute("src")
                        if src and (w is None or int(w or "0") > 100):
                            found_img = img
                            break
                    if found_img:
                        break
                except Exception:
                    pass
            if found_img:
                break
            await page.wait_for_timeout(2000)
            dots += 1
            if dots % 5 == 0:
                elapsed = int(asyncio.get_event_loop().time() - t0)
                print(f"[gemini] Still waiting... {elapsed}s elapsed")

        if found_img is None:
            await page.screenshot(path="/tmp/gemini-timeout.png")
            print(f"[gemini] TIMEOUT after {timeout}s. Screenshot: /tmp/gemini-timeout.png")
            await browser.close()
            return False

        # Save image
        src = await found_img.get_attribute("src") or ""
        print(f"[gemini] Image found (src: {src[:60]}...)")

        try:
            if src.startswith("blob:") or src.startswith("data:"):
                # Screenshot element as fallback
                await found_img.screenshot(path=str(output_path))
                print(f"[gemini] ✓ Saved via element screenshot: {output_path}")
            else:
                # Download via network
                import urllib.request
                urllib.request.urlretrieve(src, str(output_path))
                print(f"[gemini] ✓ Downloaded: {output_path}")
        except Exception as e:
            print(f"[gemini] ERROR saving image: {e}")
            await browser.close()
            return False

        await browser.close()
        return output_path.exists() and output_path.stat().st_size > 1000


def main():
    ap = argparse.ArgumentParser(description="Generate image via Gemini web UI")
    ap.add_argument("prompt_file", help="Prompt .md or .txt file")
    ap.add_argument("output_path", help="Output path (e.g. cover.jpeg)")
    ap.add_argument("--cookies", default=str(DEFAULT_COOKIES), help="Netscape cookies.txt")
    ap.add_argument("--headless", action="store_true", help="Run headless (no browser window)")
    ap.add_argument("--timeout", type=int, default=90, help="Max seconds to wait for image")
    args = ap.parse_args()

    if not Path(args.cookies).exists():
        print(f"[gemini] ERROR: Cookies file not found: {args.cookies}")
        print("[gemini] Export from Chrome: EditThisCookie → Export (Netscape format)")
        sys.exit(1)

    prompt = read_prompt(args.prompt_file)
    if not prompt:
        print("[gemini] ERROR: Empty prompt")
        sys.exit(1)

    print(f"[gemini] Prompt preview: {prompt[:120]}...")
    ok = asyncio.run(generate(prompt, args.output_path, args.cookies, args.headless, args.timeout))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
