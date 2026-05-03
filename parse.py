"""
Parse Facebook Marketplace listing HTML files into a CSV.

Extracts: title, price (CAD), description, condition, location, creation date,
sold status, plus inferred fields (brand, year, frame size, wheel size, frame
material, groupset) from the title + description text.
"""

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
LISTINGS_DIR = ROOT / "listings"
OUT_CSV = ROOT / "bikes.csv"

BRANDS = [
    "Trek", "Specialized", "Giant", "Cannondale", "Norco", "Felt", "Cervelo",
    "Cervélo", "Scott", "Bianchi", "Salsa", "Surly", "Kona", "Marin", "Devinci",
    "Rocky Mountain", "Rocky", "Diamondback", "GT", "Fuji", "BMC", "Pinarello",
    "Orbea", "Canyon", "Focus", "Cube", "Ridley", "Ribble", "3T", "Argon 18",
    "Lapierre", "Look", "Merida", "Liv", "Wilier", "Genesis", "Kinesis", "Brodie",
    "Opus", "Louis Garneau", "Garneau", "Raleigh", "Schwinn", "Jamis", "All-City",
    "State Bicycle", "Reid", "Vitus", "Ribble", "Polygon", "Pivot", "Yeti",
    "Mongoose", "CCM", "Supercycle",
]
BRAND_RE = re.compile(r"\b(" + "|".join(re.escape(b) for b in BRANDS) + r")\b", re.I)

WHEEL_PATTERNS = [
    (re.compile(r"\b700\s*c\b", re.I), "700c"),
    (re.compile(r"\b650\s*b\b", re.I), "650b"),
    (re.compile(r"\b29\s*(?:er|\")", re.I), "29"),
    (re.compile(r"\b27\.5\s*(?:er|\")?", re.I), "27.5"),
    (re.compile(r"\b26\s*(?:er|\")", re.I), "26"),
]

MATERIAL_PATTERNS = [
    (re.compile(r"\bcarbon\b", re.I), "carbon"),
    (re.compile(r"\btitanium\b|\bti\s+frame\b", re.I), "titanium"),
    (re.compile(r"\b(?:cromo|cro-?mo|chromoly|steel|columbus|reynolds)\b", re.I), "steel"),
    (re.compile(r"\b(?:aluminum|aluminium|alloy)\b", re.I), "aluminum"),
]

GROUPSET_PATTERNS = [
    (re.compile(r"\bdura[\s-]?ace\b", re.I), "Dura-Ace"),
    (re.compile(r"\bultegra\b", re.I), "Ultegra"),
    (re.compile(r"\b105\b", re.I), "105"),
    (re.compile(r"\btiagra\b", re.I), "Tiagra"),
    (re.compile(r"\bsora\b", re.I), "Sora"),
    (re.compile(r"\bclaris\b", re.I), "Claris"),
    (re.compile(r"\bgrx\b", re.I), "GRX"),
    (re.compile(r"\bred\s*(?:axs|etap)?\b", re.I), "SRAM Red"),
    (re.compile(r"\bforce\s*(?:axs|etap)?\b", re.I), "SRAM Force"),
    (re.compile(r"\brival\s*(?:axs|etap)?\b", re.I), "SRAM Rival"),
    (re.compile(r"\bapex\s*(?:axs|etap)?\b", re.I), "SRAM Apex"),
    (re.compile(r"\bekar\b", re.I), "Campagnolo Ekar"),
]

SIZE_NUMERIC_RE = re.compile(r"\b(4[2-9]|5[0-9]|6[0-4])\s*cm\b", re.I)
SIZE_LETTER_RE = re.compile(r"\b(X{0,2}S|S|M|L|X{1,3}L)\b(?:\s*(?:size|frame))?", re.I)
YEAR_RE = re.compile(r"\b(19[89]\d|20[0-2]\d)\b")

# (brand, model_canonical, regex) — first match wins. Patterns tolerate
# spaces / dashes and are case-insensitive. Models cover gravel + CX +
# all-road / endurance bikes that gravel buyers cross-shop.
MODEL_PATTERNS = [
    ("Trek", "Checkpoint", r"\bcheckpoint\b"),
    ("Trek", "Domane Gravel", r"\bdomane\s+gravel\b"),
    ("Trek", "Boone", r"\bboone\b"),
    ("Trek", "Crockett", r"\bcrockett\b"),
    ("Trek", "Domane", r"\bdomane\b"),
    ("Specialized", "Diverge", r"\bdiverge\b"),
    ("Specialized", "Crux", r"\bcrux\b"),
    ("Specialized", "AWOL", r"\bawol\b"),
    ("Specialized", "Sequoia", r"\bsequoia\b"),
    ("Specialized", "Roubaix", r"\broubaix\b"),
    ("Cannondale", "Topstone", r"\btopstone\b"),
    ("Cannondale", "Slate", r"\bslate\b"),
    ("Cannondale", "CAADX", r"\bcaad\s*x\b"),
    ("Cannondale", "Synapse", r"\bsynapse\b"),
    ("Giant", "Revolt", r"\brevolt\b"),
    ("Giant", "TCX", r"\btcx\b"),
    ("Giant", "Defy", r"\bdefy\b"),
    ("Giant", "Contend", r"\bcontend\b"),
    ("Liv", "Devote", r"\bdevote\b"),
    ("Salsa", "Warbird", r"\bwarbird\b"),
    ("Salsa", "Cutthroat", r"\bcutthroat\b"),
    ("Salsa", "Journeyer", r"\bjourneyer\b"),
    ("Salsa", "Vaya", r"\bvaya\b"),
    ("Salsa", "Stormchaser", r"\bstormchaser\b"),
    ("Salsa", "Fargo", r"\bfargo\b"),
    ("Kona", "Rove", r"\brove\b"),
    ("Kona", "Sutra", r"\bsutra\b"),
    ("Kona", "Libre", r"\blibre\b"),
    ("Kona", "Jake the Snake", r"\bjake\s+the\s+snake\b"),
    ("Kona", "Major Jake", r"\bmajor\s+jake\b"),
    ("Kona", "Jake", r"\bjake\b"),
    ("Surly", "Straggler", r"\bstraggler\b"),
    ("Surly", "Midnight Special", r"\bmidnight\s+special\b"),
    ("Surly", "Cross-Check", r"\bcross[\s-]?check\b"),
    ("Surly", "Disc Trucker", r"\bdisc\s+trucker\b"),
    ("Surly", "Long Haul Trucker", r"\blong\s+haul\s+trucker\b|\blht\b"),
    ("Surly", "Preamble", r"\bpreamble\b"),
    ("Fuji", "Jari", r"\bjari\b"),
    ("Jamis", "Renegade", r"\brenegade\b"),
    ("Bianchi", "Allroad", r"\ball[\s-]?road\b.{0,12}\bbianchi\b|\bbianchi\b.{0,12}\ball[\s-]?road\b"),
    ("Orbea", "Terra", r"\bterra\b"),
    ("Canyon", "Inflite", r"\binflite\b"),
    ("Canyon", "Grail", r"\bgrail\b"),
    ("Canyon", "Grizl", r"\bgrizl\b"),
    ("Canyon", "Endurace", r"\bendurace\b"),
    ("BMC", "URS", r"\burs\b"),
    ("BMC", "Roadmachine X", r"\broadmachine\s+x\b"),
    ("Cervelo", "Aspero", r"\baspero\b"),
    ("Cervelo", "Caledonia", r"\bcaledonia\b"),
    ("3T", "Exploro", r"\bexploro\b"),
    ("Marin", "Gestalt", r"\bgestalt\b"),
    ("Marin", "Four Corners", r"\bfour\s+corners\b"),
    ("Marin", "Nicasio", r"\bnicasio\b"),
    ("Marin", "Headlands", r"\bheadlands\b"),
    ("Norco", "Search", r"\bsearch\b\s*xr?\b|\bnorco\b.{0,15}\bsearch\b"),
    ("Norco", "Threshold", r"\bthreshold\b"),
    ("Norco", "Bigfoot", r"\bbigfoot\b"),
    ("Devinci", "Hatchet", r"\bhatchet\b"),
    ("Cervelo", "Soloist", r"\bsoloist\b"),
    ("Argon 18", "Dark Matter", r"\bdark\s+matter\b"),
    ("Felt", "Broam", r"\bbroam\b"),
    ("Felt", "VR", r"\bfelt\s+vr\b"),
    ("Felt", "F-Series", r"\bfelt\s+f\d+\b"),
    ("Open", "U.P.", r"\bopen\s+u\.?p\.?\b"),
    ("Open", "WI.DE", r"\bopen\s+wi\.?de\.?\b"),
    ("Bombtrack", "Hook", r"\bbombtrack\b.{0,15}\bhook\b|\bhook\s*ext\b"),
    ("All-City", "Cosmic Stallion", r"\bcosmic\s+stallion\b"),
    ("All-City", "Macho King", r"\bmacho\s+king\b"),
    ("All-City", "Space Horse", r"\bspace\s+horse\b"),
    ("All-City", "Gorilla Monsoon", r"\bgorilla\s+monsoon\b"),
    ("Wilier", "Jena", r"\bjena\b"),
    ("Wilier", "Rave SLR", r"\brave\s+slr\b"),
    ("Pinarello", "Grevil", r"\bgrevil\b"),
    ("Lauf", "True Grit", r"\btrue\s+grit\b"),
    ("Lauf", "Seigla", r"\bseigla\b"),
    ("Cinelli", "Hobootleg", r"\bhobootleg\b"),
    ("Genesis", "Croix de Fer", r"\bcroix\s+de\s+fer\b"),
    ("Genesis", "Vagabond", r"\bvagabond\b"),
    ("Ridley", "Kanzo", r"\bkanzo\b"),
    ("Ridley", "X-Trail", r"\bx[\s-]?trail\b"),
    ("Diamondback", "Haanjo", r"\bhaanjo\b"),
    ("Vitus", "Substance", r"\bsubstance\b"),
    ("Vitus", "Energie", r"\benergie\b"),
    ("Ribble", "Gravel", r"\bribble\b.{0,10}\bgravel\b"),
    ("Cube", "Nuroad", r"\bnuroad\b"),
    ("Cube", "Cross Race", r"\bcube\b.{0,15}\bcross\s+race\b"),
    ("Focus", "Atlas", r"\bfocus\b.{0,10}\batlas\b"),
    ("Focus", "Mares", r"\bmares\b"),
    ("Focus", "Paralane", r"\bparalane\b"),
    ("Rocky Mountain", "Solo", r"\brocky\s+mountain\b.{0,10}\bsolo\b"),
    ("Brodie", "Romax", r"\bromax\b"),
    ("Brodie", "Ronin", r"\bronin\b"),
    ("Garneau", "Gennix", r"\bgennix\b"),
    ("Garneau", "Steeple", r"\bsteeple\b"),
    ("Opus", "Spark", r"\bopus\b.{0,10}\bspark\b"),
    ("Opus", "Citato", r"\bcitato\b"),
    ("Pivot", "Vault", r"\bvault\b"),
    ("Yeti", "ARC", r"\byeti\b.{0,10}\barc\b"),
    ("Bianchi", "Zolder", r"\bzolder\b"),
    ("Bianchi", "Impulso", r"\bimpulso\b"),
    ("Bianchi", "Volpe", r"\bvolpe\b"),
]
MODEL_PATTERNS = [(b, m, re.compile(p, re.I)) for b, m, p in MODEL_PATTERNS]

GRAVEL_OR_CX_RE = re.compile(
    r"\b(gravel|cyclocross|cyclo-?cross|\bcx\b|all[\s-]?road|adventure\s+bike|"
    r"drop[\s-]?bar|bikepacking|gran\s*fondo|endurance\s+road)\b",
    re.I,
)

CONDITION_MAP = {
    "PC_NEW": "new",
    "PC_USED_LIKE_NEW": "like_new",
    "PC_USED_GOOD": "good",
    "PC_USED_FAIR": "fair",
}


def extract_field(html, key, value_pattern):
    m = re.search(rf'"{key}"\s*:\s*{value_pattern}', html)
    return m.group(1) if m else None


LISTING_PHOTO_RE = re.compile(
    r'"listing_photos"\s*:\s*\[\s*\{[^]]*?"uri"\s*:\s*"([^"]+)"'
)


def extract_primary_image_url(html):
    m = LISTING_PHOTO_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(f'"{m.group(1)}"')
    except json.JSONDecodeError:
        return None


def parse_listing(path):
    html = path.read_text(encoding="utf-8", errors="replace")
    item_id = path.stem

    title = extract_field(html, "marketplace_listing_title", r'"((?:[^"\\]|\\.)*)"')
    price_text = extract_field(html, "formatted_price", r'\{"text":"((?:[^"\\]|\\.)*)"')
    price_amount = extract_field(html, "listing_price", r'\{"amount":"([^"]+)"')
    desc = extract_field(html, "redacted_description", r'\{"text":"((?:[^"\\]|\\.)*)"')
    cond_raw = extract_field(html, "condition", r'"([A-Z_]+)"')
    loc_city = extract_field(html, "reverse_geocode", r'\{"city":"((?:[^"\\]|\\.)*)"')
    lat = extract_field(html, "latitude", r"([\d.\-]+)")
    lng = extract_field(html, "longitude", r"([\d.\-]+)")
    ctime = extract_field(html, "creation_time", r"(\d+)")
    is_sold = extract_field(html, "is_sold", r"(true|false)")

    def unescape(s):
        if s is None:
            return None
        try:
            decoded = json.loads(f'"{s}"')
        except json.JSONDecodeError:
            decoded = s
        return decoded.encode("utf-16", "surrogatepass").decode("utf-16", "replace")

    title = unescape(title) or ""
    desc = unescape(desc) or ""
    price_text = unescape(price_text) or ""
    loc_city = unescape(loc_city) or ""

    price = None
    if price_amount:
        try:
            price = float(price_amount)
        except ValueError:
            pass
    if price is None and price_text:
        m = re.search(r"([\d,]+(?:\.\d+)?)", price_text)
        if m:
            price = float(m.group(1).replace(",", ""))

    text = f"{title} {desc}"

    def first_brand(s):
        if not s:
            return None
        bm = BRAND_RE.search(s)
        if not bm:
            return None
        b = bm.group(1).title()
        if b.lower() == "rocky":
            return "Rocky Mountain"
        if b.lower() == "garneau":
            return "Louis Garneau"
        return b

    brand_desc = first_brand(desc)
    brand_title = first_brand(title)
    brand = brand_desc or brand_title

    year = None
    ym = YEAR_RE.search(desc) or YEAR_RE.search(title)
    if ym:
        year = int(ym.group(1))

    wheel_size = None
    for pat, label in WHEEL_PATTERNS:
        if pat.search(text):
            wheel_size = label
            break

    material = None
    for pat, label in MATERIAL_PATTERNS:
        if pat.search(text):
            material = label
            break

    groupset = None
    for pat, label in GROUPSET_PATTERNS:
        if pat.search(text):
            groupset = label
            break

    frame_size = None
    sm = SIZE_NUMERIC_RE.search(text)
    if sm:
        frame_size = sm.group(1) + "cm"
    else:
        for sm in SIZE_LETTER_RE.finditer(text):
            tok = sm.group(1).upper()
            if tok in {"S", "M", "L", "XS", "XL", "XXL", "XXXL"}:
                frame_size = tok
                break

    condition = CONDITION_MAP.get(cond_raw or "", cond_raw)

    is_gravel = bool(re.search(r"\bgravel\b", text, re.I))
    is_gravel_or_cx = bool(GRAVEL_OR_CX_RE.search(text))
    title_brand_mismatch = bool(brand_title and brand_desc and brand_title.lower() != brand_desc.lower())

    model = None
    matched_brand = None
    for b, m, pat in MODEL_PATTERNS:
        if not pat.search(desc):
            continue
        # Require the brand word to also appear in the description, to filter
        # out bait listings ("Kona Rove" title with cruiser desc) and false
        # positives like Xbox games matching "Substance" or ski boots matching
        # "Diverge".
        brand_re = re.compile(r"\b" + re.escape(b).replace(r"\ ", r"\s+") + r"\b", re.I)
        if not brand_re.search(desc):
            continue
        model = m
        matched_brand = b
        break
    if matched_brand and not brand:
        brand = matched_brand
    if matched_brand:
        is_gravel_or_cx = True

    return {
        "item_id": item_id,
        "title": title,
        "price_cad": price,
        "price_text": price_text,
        "is_sold": is_sold == "true",
        "is_gravel_in_text": is_gravel,
        "is_gravel_or_cx": is_gravel_or_cx,
        "model": model,
        "title_brand": brand_title,
        "desc_brand": brand_desc,
        "title_brand_mismatch": title_brand_mismatch,
        "condition": condition,
        "brand": brand,
        "year": year,
        "frame_size": frame_size,
        "wheel_size": wheel_size,
        "frame_material": material,
        "groupset": groupset,
        "city": loc_city,
        "latitude": float(lat) if lat else None,
        "longitude": float(lng) if lng else None,
        "creation_date": (
            datetime.fromtimestamp(int(ctime), tz=timezone.utc).date().isoformat()
            if ctime else None
        ),
        "url": f"https://www.facebook.com/marketplace/item/{item_id}/",
        "description": desc[:500],
        "image_url": extract_primary_image_url(html),
    }


def main():
    rows = []
    files = sorted(LISTINGS_DIR.glob("*.html"))
    print(f"Parsing {len(files)} files...")
    for i, f in enumerate(files, 1):
        try:
            rows.append(parse_listing(f))
        except Exception as e:
            print(f"  [{i}/{len(files)}] {f.name} ERROR: {e}")
        if i % 100 == 0:
            print(f"  parsed {i}/{len(files)}")

    cols = list(rows[0].keys())
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {len(rows)} rows to {OUT_CSV}")

    have_price = sum(1 for r in rows if r["price_cad"] is not None)
    have_brand = sum(1 for r in rows if r["brand"])
    have_year = sum(1 for r in rows if r["year"])
    have_wheel = sum(1 for r in rows if r["wheel_size"])
    have_size = sum(1 for r in rows if r["frame_size"])
    have_mat = sum(1 for r in rows if r["frame_material"])
    have_grp = sum(1 for r in rows if r["groupset"])
    have_model = sum(1 for r in rows if r["model"])
    have_gravel_cx = sum(1 for r in rows if r["is_gravel_or_cx"])
    print(f"  price:    {have_price}/{len(rows)}")
    print(f"  brand:    {have_brand}/{len(rows)}")
    print(f"  year:     {have_year}/{len(rows)}")
    print(f"  wheel:    {have_wheel}/{len(rows)}")
    print(f"  size:     {have_size}/{len(rows)}")
    print(f"  material: {have_mat}/{len(rows)}")
    print(f"  groupset: {have_grp}/{len(rows)}")
    print(f"  model:    {have_model}/{len(rows)}")
    print(f"  gravel/cx:{have_gravel_cx}/{len(rows)}")


if __name__ == "__main__":
    main()
