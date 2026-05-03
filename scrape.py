"""
Scrape Facebook Marketplace gravel bike listings near Sherwood Park, AB.

First run: a browser window opens. Log into Facebook manually if prompted,
then press Enter in the terminal. Session is saved to storage_state.json
and reused on subsequent runs.

Output: listings/<item_id>.html  +  listings/index.json
"""

import argparse
import json
import random
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent
STATE_FILE = ROOT / "storage_state.json"
OUT_DIR = ROOT / "listings"
INDEX_FILE = OUT_DIR / "index.json"

SEARCH_URL = (
    "https://www.facebook.com/marketplace/104044399631602/search/"
    "?query=gravel%20bike&radius=30&exact=false"
)
ITEM_ID_RE = re.compile(r"/marketplace/item/(\d+)")


def human_pause(a=1.0, b=2.5):
    time.sleep(random.uniform(a, b))


def ensure_logged_in(playwright, headless=False):
    """Open a browser; if no saved session, wait for the user to log in."""
    browser = playwright.chromium.launch(headless=headless)
    if STATE_FILE.exists():
        ctx = browser.new_context(storage_state=str(STATE_FILE))
        return browser, ctx

    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto("https://www.facebook.com/login")
    print(">> Waiting for login (poll every 3s, timeout 10min)...", flush=True)
    deadline = time.time() + 600
    while time.time() < deadline:
        time.sleep(3)
        try:
            url = page.url
            cookies = {c["name"] for c in ctx.cookies()}
            if "c_user" in cookies and "/login" not in url and "checkpoint" not in url:
                print(">> Login detected. Saving session...", flush=True)
                time.sleep(2)
                ctx.storage_state(path=str(STATE_FILE))
                page.close()
                return browser, ctx
        except Exception as e:
            print(f"  poll error: {e}", flush=True)
    raise TimeoutError("Login not detected within 10 minutes")


def collect_listing_urls(page, max_listings, scroll_rounds=40, stagnant_limit=4):
    """Scroll the search results page and collect unique listing URLs.

    Stops early when max_listings is reached OR when `stagnant_limit`
    consecutive scrolls produce zero new listings (saturation).
    """
    page.goto(SEARCH_URL, wait_until="domcontentloaded")
    human_pause(2, 4)

    seen = {}
    stagnant = 0
    for i in range(scroll_rounds):
        anchors = page.eval_on_selector_all(
            "a[href*='/marketplace/item/']",
            "els => els.map(e => e.href)",
        )
        before = len(seen)
        for href in anchors:
            m = ITEM_ID_RE.search(href)
            if m:
                item_id = m.group(1)
                if item_id not in seen:
                    seen[item_id] = href.split("?")[0]
        added = len(seen) - before
        stagnant = stagnant + 1 if added == 0 else 0
        print(f"  scroll {i + 1}/{scroll_rounds}: {len(seen)} unique (+{added}, stagnant={stagnant})", flush=True)
        if len(seen) >= max_listings:
            break
        if stagnant >= stagnant_limit:
            print(f"  saturated after {stagnant} stagnant scrolls — stopping", flush=True)
            break
        page.mouse.wheel(0, 4000)
        human_pause(1.5, 3.0)

    return dict(list(seen.items())[:max_listings])


def download_listing(page, item_id, url):
    out = OUT_DIR / f"{item_id}.html"
    if out.exists():
        return "skipped"
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    human_pause(2, 4)
    try:
        page.wait_for_selector("div[role='main']", timeout=10000)
    except Exception:
        pass
    out.write_text(page.content(), encoding="utf-8")
    return "saved"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=40, help="Max listings to download")
    parser.add_argument("--headless", action="store_true", help="Run headless (only after first login)")
    args = parser.parse_args()

    OUT_DIR.mkdir(exist_ok=True)

    with sync_playwright() as pw:
        browser, ctx = ensure_logged_in(pw, headless=args.headless)
        page = ctx.new_page()

        print(f"Collecting listing URLs from search (target {args.max})...")
        listings = collect_listing_urls(page, args.max)
        print(f"Found {len(listings)} listings. Downloading...")

        results = []
        for i, (item_id, url) in enumerate(listings.items(), 1):
            try:
                status = download_listing(page, item_id, url)
                print(f"  [{i}/{len(listings)}] {item_id}  {status}", flush=True)
            except Exception as e:
                status = f"error: {e}"
                print(f"  [{i}/{len(listings)}] {item_id}  {status}", flush=True)
            results.append({"item_id": item_id, "url": url, "status": status})

        INDEX_FILE.write_text(json.dumps(results, indent=2), encoding="utf-8")

        ctx.storage_state(path=str(STATE_FILE))
        browser.close()

    print(f"\nDone. HTML in {OUT_DIR}/, index in {INDEX_FILE}")


if __name__ == "__main__":
    main()
