"""
Use OpenAI (gpt-4.1-mini + web_search_preview) to identify each listing's
bike and estimate its original MSRP in CAD. Caches per-item results to
msrp_cache.json so reruns only call the API for new listings.

Output: enriched_bikes.csv = bikes.csv + {llm_brand, llm_model, llm_year,
llm_msrp_cad, llm_is_bike, llm_bike_type, llm_confidence, llm_notes}.
"""

import argparse
import base64
import json
import os
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
from openai import OpenAI

ROOT = Path(__file__).parent
CSV_IN = ROOT / "bikes.csv"
CSV_OUT = ROOT / "enriched_bikes.csv"
CACHE = ROOT / "msrp_cache.json"
IMAGE_CACHE = ROOT / "msrp_image_cache.json"
IMAGE_BYTES_DIR = ROOT / "listing_images"

MODEL = "gpt-5.4-mini"

SYSTEM = """You are a bicycle pricing assistant. Given a Facebook Marketplace listing's title and description, do all of the following:

1. Decide if this listing is for a complete bicycle. A complete bicycle has a frame, wheels, drivetrain. Listings for parts (tubes, tires, wheelsets, helmets, jerseys), accessories, motorcycles, kids' bikes/balance bikes, and unrelated items are NOT bikes.

2. CRITICAL — bait-and-switch detection. Facebook Marketplace is full of listings where the title is a popular bike (e.g., "Felt gravel bike", "Kona Rove", "2023 Felt Gravel bike") but the description describes something entirely different (a cruiser, a women's hybrid, marine pricing, motorcycle parts, etc.). The DESCRIPTION is the truth; the TITLE is often clickbait. Rules:
   - If the description does not describe the bike named in the title, IGNORE the title and identify the bike from the description.
   - If the description is vague or generic ("ladies bike", "speed bike", "perfect for kids", "28cm", a bare measurement, marine/boat/motorcycle text, real estate text), AND the title is suspicious, set is_bike=false OR set confidence="low" with msrp_cad=null. Do NOT default to the title's bike model.
   - Title patterns that are commonly bait: "Felt gravel bike" (often actually a cruiser or unrelated item), "Kona Rove" (when description has no Kona/Rove specifics), "2023 Felt Gravel bike".
   - Only assign a specific brand+model if the description contains corroborating details: matching brand name, matching model name, matching components, matching frame size/material, matching colour, etc.

3. If it IS a bike, extract: brand, model name (most specific tier you can justify from the description), year (if mentioned), and bike_type (one of: gravel, cyclocross, road, endurance_road, mountain, hardtail_mtb, fat_bike, hybrid, cruiser, commuter, fixie, touring, e_bike, bmx, kids, other).

4. Use web search to look up the original MSRP at launch in CAD. If the bike was sold in USD, convert at 1.35 USD->CAD. If you cannot find a specific MSRP, estimate based on similar bikes from the same brand/year/tier and mark confidence as "low". Do NOT estimate MSRP for vague generic listings.

Reply with strict JSON only, no markdown, no commentary:
{
  "is_bike": true | false,
  "brand": "<string or null>",
  "model": "<string or null>",
  "year": <int or null>,
  "bike_type": "<string or null>",
  "msrp_cad": <number or null>,
  "confidence": "high" | "medium" | "low" | "unknown",
  "title_desc_match": true | false,
  "notes": "<short note, e.g. source url, model trim assumed, why title was ignored>"
}"""

IMAGE_SYSTEM = """You are a bicycle pricing assistant. You are looking at a Facebook Marketplace listing where the text alone wasn't enough to identify the bike. You now have the listing photo as well.

Use the photo as your primary evidence. Read decals and head-badges, look at frame silhouette (gravel/road/MTB/hybrid/cruiser/BMX/kids), tube shapes, fork (rigid/suspension), drivetrain (1x/2x, derailleur brand if visible), brakes (rim/disc, mechanical/hydraulic), wheels, handlebars (drop/flat/riser), and overall build tier.

Tasks:
1. Decide is_bike: complete bicycle (frame + wheels + drivetrain) only. Parts/accessories/exercise machines/motorcycles/kids' balance bikes => false.
2. If a bike, identify brand and model name as specifically as the photo + text supports. If you can only see a generic frame with no readable decal, leave brand/model null and set confidence="low".
3. Pick a bike_type from: gravel, cyclocross, road, endurance_road, mountain, hardtail_mtb, fat_bike, hybrid, cruiser, commuter, fixie, touring, e_bike, bmx, kids, other.
4. Estimate MSRP at launch in CAD. If you can read a brand+model from the photo, use web search to find the original MSRP. If you can only narrow it to "generic department-store hybrid" or "no-name big-box mountain bike", give a conservative MSRP estimate ($150-$400 typical for big-box, $400-$800 for entry brand-name) and mark confidence="low". Do NOT invent specific MSRPs for unidentifiable bikes.

Reply with strict JSON only, no markdown:
{
  "is_bike": true | false,
  "brand": "<string or null>",
  "model": "<string or null>",
  "year": <int or null>,
  "bike_type": "<string or null>",
  "msrp_cad": <number or null>,
  "confidence": "high" | "medium" | "low" | "unknown",
  "image_helped": true | false,
  "notes": "<short note: what you saw in the photo, decal text, build tier>"
}"""


def call_llm(client, item_id, title, desc):
    user = f"Title: {title}\n\nDescription: {desc[:1500]}"
    resp = client.responses.create(
        model=MODEL,
        instructions=SYSTEM,
        input=user,
        tools=[{"type": "web_search_preview"}],
    )
    text = resp.output_text or ""
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = text.replace("```", "")
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {"is_bike": None, "_raw": text[:200]}
    raw = m.group(0)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fix common issues: trailing commas, single quotes, newlines in strings.
        cleaned = re.sub(r",\s*([}\]])", r"\1", raw)
        cleaned = cleaned.replace("\n", " ")
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            return {"is_bike": None, "_parse_error": str(e)[:120], "_raw": raw[:200]}


def load_cache():
    if CACHE.exists():
        return json.loads(CACHE.read_text())
    return {}


def save_cache(cache):
    CACHE.write_text(json.dumps(cache, indent=2))


def load_image_cache():
    if IMAGE_CACHE.exists():
        return json.loads(IMAGE_CACHE.read_text())
    return {}


def save_image_cache(cache):
    IMAGE_CACHE.write_text(json.dumps(cache, indent=2))


def fetch_image_bytes(item_id, image_url):
    """Download image to listing_images/<item_id>.jpg, cached on disk."""
    IMAGE_BYTES_DIR.mkdir(exist_ok=True)
    out = IMAGE_BYTES_DIR / f"{item_id}.jpg"
    if out.exists() and out.stat().st_size > 0:
        return out.read_bytes()
    req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    out.write_bytes(data)
    return data


def call_llm_with_image(client, item_id, title, desc, image_bytes):
    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:image/jpeg;base64,{b64}"
    user_content = [
        {"type": "input_text", "text": f"Title: {title}\n\nDescription: {desc[:1500]}"},
        {"type": "input_image", "image_url": data_url},
    ]
    resp = client.responses.create(
        model=MODEL,
        instructions=IMAGE_SYSTEM,
        input=[{"role": "user", "content": user_content}],
        tools=[{"type": "web_search_preview"}],
    )
    text = resp.output_text or ""
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = text.replace("```", "")
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {"is_bike": None, "_raw": text[:200]}
    raw = m.group(0)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        cleaned = re.sub(r",\s*([}\]])", r"\1", raw)
        cleaned = cleaned.replace("\n", " ")
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            return {"is_bike": None, "_parse_error": str(e)[:120], "_raw": raw[:200]}


def looks_like_bike(row):
    desc = str(row.get("description") or "")
    title = str(row.get("title") or "")
    if row.get("title_brand_mismatch"):
        return False
    text = f"{title} {desc}".lower()
    if not re.search(r"\b(bike|bicycle|cyclocross|frame|drivetrain|shimano|sram)\b", text):
        return False
    if re.search(r"\b(motorcycle|ducati|harley|apartment|condo|for rent|piano|guitar)\b", text):
        return False
    price = row.get("price_cad")
    if pd.isna(price) or price < 200 or price > 15000:
        return False
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Cap calls (for testing)")
    parser.add_argument("--workers", type=int, default=6, help="Parallel API calls")
    parser.add_argument("--all", action="store_true", help="Run on every row, not just bike-shaped")
    parser.add_argument(
        "--image-fallback",
        action="store_true",
        help="For rows where text pass said is_bike=true but msrp_cad is null, "
             "rerun with the listing photo attached.",
    )
    args = parser.parse_args()

    df = pd.read_csv(CSV_IN)
    print(f"Loaded {len(df)} listings")

    client = OpenAI()
    cache = load_cache()

    if args.image_fallback:
        image_cache = load_image_cache()
        candidates = []
        for _, r in df.iterrows():
            item_id = str(r["item_id"])
            text_result = cache.get(item_id, {})
            if text_result.get("is_bike") is not True:
                continue
            if text_result.get("msrp_cad") is not None:
                continue
            if item_id in image_cache and "_error" not in image_cache[item_id]:
                continue
            image_url = r.get("image_url")
            if not image_url or pd.isna(image_url):
                continue
            candidates.append(
                (item_id, str(r.get("title") or ""), str(r.get("description") or ""), str(image_url))
            )
        print(f"Image fallback candidates (is_bike=true, msrp=null, not cached): {len(candidates)}")

        if args.limit:
            candidates = candidates[: args.limit]
            print(f"--limit applied: will call API for {len(candidates)} listings")

        def img_work(args_):
            item_id, title, desc, image_url = args_
            try:
                img_bytes = fetch_image_bytes(item_id, image_url)
            except Exception as e:
                return item_id, {"_error": f"image fetch: {str(e)[:160]}"}
            for attempt in range(3):
                try:
                    return item_id, call_llm_with_image(client, item_id, title, desc, img_bytes)
                except Exception as e:
                    if attempt == 2:
                        return item_id, {"_error": str(e)[:200]}
                    time.sleep(2 ** attempt)

        done = 0
        if candidates:
            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                futs = [ex.submit(img_work, c) for c in candidates]
                for fut in as_completed(futs):
                    item_id, result = fut.result()
                    image_cache[item_id] = result
                    done += 1
                    if done % 5 == 0 or done == len(candidates):
                        save_image_cache(image_cache)
                        print(f"  [{done}/{len(candidates)}] image-cached", flush=True)
            save_image_cache(image_cache)

        gained_msrp = sum(
            1
            for v in image_cache.values()
            if v.get("is_bike") is True and v.get("msrp_cad") is not None
        )
        print(f"  Image pass total with MSRP: {gained_msrp}")
    else:
        image_cache = load_image_cache() if IMAGE_CACHE.exists() else {}

        if not args.all:
            mask = df.apply(looks_like_bike, axis=1)
            targets = df[mask].copy()
            print(f"Bike-shaped (basic filter): {len(targets)}")
        else:
            targets = df.copy()

        pending = [
            (str(r["item_id"]), str(r.get("title") or ""), str(r.get("description") or ""))
            for _, r in targets.iterrows()
            if str(r["item_id"]) not in cache
        ]
        print(f"Cache hits: {len(targets) - len(pending)}, calls needed: {len(pending)}")

        if args.limit:
            pending = pending[: args.limit]
            print(f"--limit applied: will call API for {len(pending)} listings")

        def work(args_):
            item_id, title, desc = args_
            for attempt in range(3):
                try:
                    return item_id, call_llm(client, item_id, title, desc)
                except Exception as e:
                    if attempt == 2:
                        return item_id, {"_error": str(e)[:200]}
                    time.sleep(2 ** attempt)

        done = 0
        if pending:
            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                futs = [ex.submit(work, p) for p in pending]
                for fut in as_completed(futs):
                    item_id, result = fut.result()
                    cache[item_id] = result
                    done += 1
                    if done % 5 == 0 or done == len(pending):
                        save_cache(cache)
                        print(f"  [{done}/{len(pending)}] cached", flush=True)
            save_cache(cache)

    enriched_cols = {
        "llm_is_bike": [], "llm_brand": [], "llm_model": [], "llm_year": [],
        "llm_bike_type": [], "llm_msrp_cad": [], "llm_confidence": [], "llm_notes": [],
        "llm_source": [],
    }
    for _, r in df.iterrows():
        item_id = str(r["item_id"])
        c = cache.get(item_id, {}) or {}
        img = image_cache.get(item_id, {}) or {}
        # Prefer image-pass result when it gives us an MSRP we didn't have from text.
        use_image = (
            img.get("is_bike") is True
            and img.get("msrp_cad") is not None
            and c.get("msrp_cad") is None
        )
        chosen = img if use_image else c
        enriched_cols["llm_is_bike"].append(chosen.get("is_bike"))
        enriched_cols["llm_brand"].append(chosen.get("brand"))
        enriched_cols["llm_model"].append(chosen.get("model"))
        enriched_cols["llm_year"].append(chosen.get("year"))
        enriched_cols["llm_bike_type"].append(chosen.get("bike_type"))
        enriched_cols["llm_msrp_cad"].append(chosen.get("msrp_cad"))
        enriched_cols["llm_confidence"].append(chosen.get("confidence"))
        enriched_cols["llm_notes"].append((chosen.get("notes") or "")[:200])
        enriched_cols["llm_source"].append("image" if use_image else ("text" if c else ""))

    out = df.copy()
    for k, v in enriched_cols.items():
        out[k] = v
    out.to_csv(CSV_OUT, index=False)
    print(f"\nWrote {CSV_OUT}")

    have_msrp = sum(1 for x in enriched_cols["llm_msrp_cad"] if x is not None)
    bikes = sum(1 for x in enriched_cols["llm_is_bike"] if x is True)
    print(f"  is_bike=true: {bikes}")
    print(f"  has MSRP:     {have_msrp}")
    type_counts = pd.Series(enriched_cols["llm_bike_type"]).value_counts()
    print(f"\nBike type distribution:")
    print(type_counts.head(15).to_string())


if __name__ == "__main__":
    main()
