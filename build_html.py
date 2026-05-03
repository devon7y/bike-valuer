"""Generate a self-contained HTML frontend for browsing bike deals."""

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
DEALS_CSV = ROOT / "deals.csv"
ENRICHED_CSV = ROOT / "enriched_bikes.csv"
OUT = ROOT / "index.html"


def main():
    enriched = pd.read_csv(ENRICHED_CSV)
    deals = pd.read_csv(DEALS_CSV)
    deals_lookup = {str(r["item_id"]): r for _, r in deals.iterrows()}

    rows = []
    for _, r in enriched.iterrows():
        d = deals_lookup.get(str(r["item_id"]))
        pred = float(d["pred_price"]) if d is not None and pd.notna(d["pred_price"]) else None
        resid = float(d["residual_pct"]) if d is not None and pd.notna(d["residual_pct"]) else None
        rows.append({
            "title": str(r["title"]) if pd.notna(r["title"]) else "",
            "price": float(r["price_cad"]) if pd.notna(r["price_cad"]) else None,
            "pred": pred,
            "residual": resid,
            "msrp": float(r["llm_msrp_cad"]) if pd.notna(r["llm_msrp_cad"]) else None,
            "brand": str(r["llm_brand"]) if pd.notna(r["llm_brand"]) else "",
            "model": str(r["llm_model"]) if pd.notna(r["llm_model"]) else "",
            "year": int(r["llm_year"]) if pd.notna(r["llm_year"]) else (int(r["year"]) if pd.notna(r["year"]) else None),
            "type": str(r["llm_bike_type"]) if pd.notna(r["llm_bike_type"]) else "",
            "size": str(r["frame_size"]) if pd.notna(r["frame_size"]) else "",
            "material": str(r["frame_material"]) if pd.notna(r["frame_material"]) else "",
            "groupset": str(r["groupset"]) if pd.notna(r["groupset"]) else "",
            "condition": str(r["condition"]) if pd.notna(r["condition"]) else "",
            "city": str(r["city"]) if pd.notna(r["city"]) else "",
            "is_bike": bool(r["llm_is_bike"]) if pd.notna(r["llm_is_bike"]) else None,
            "url": str(r["url"]) if pd.notna(r["url"]) else "",
        })

    bike_types = sorted({r["type"] for r in rows if r["type"]})
    conditions = sorted({r["condition"] for r in rows if r["condition"]})
    data_json = json.dumps(rows, separators=(",", ":"))
    types_json = json.dumps(bike_types)
    conditions_json = json.dumps(conditions)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Bike Valuer — FB Marketplace deals near Sherwood Park</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; background: #f5f5f7; color: #1d1d1f; }}
  header {{ background: #1d1d1f; color: #f5f5f7; padding: 16px 24px; }}
  header h1 {{ margin: 0; font-size: 18px; font-weight: 600; }}
  header .sub {{ font-size: 13px; opacity: 0.7; margin-top: 4px; }}
  .filters {{ background: #fff; padding: 16px 24px; border-bottom: 1px solid #e0e0e0; display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-end; }}
  .filter {{ display: flex; flex-direction: column; gap: 4px; }}
  .filter label {{ font-size: 12px; font-weight: 600; color: #666; }}
  .filter input, .filter select {{ padding: 6px 8px; border: 1px solid #d0d0d0; border-radius: 6px; font-size: 14px; min-width: 100px; }}
  .filter input[type="number"] {{ width: 110px; }}
  .filter select[multiple] {{ height: 110px; min-width: 160px; }}
  .meta {{ padding: 8px 24px; background: #fff; border-bottom: 1px solid #e0e0e0; font-size: 13px; color: #666; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; }}
  th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #ececec; font-size: 13px; vertical-align: top; }}
  th {{ background: #fafafa; cursor: pointer; user-select: none; font-weight: 600; position: sticky; top: 0; }}
  th:hover {{ background: #f0f0f0; }}
  th .arrow {{ color: #999; margin-left: 4px; font-size: 11px; }}
  tr:hover td {{ background: #fafbfc; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.title {{ max-width: 320px; }}
  td.title a {{ color: #1d1d1f; text-decoration: none; }}
  td.title a:hover {{ text-decoration: underline; }}
  .residual-good {{ color: #15803d; font-weight: 600; }}
  .residual-bad {{ color: #b91c1c; }}
  .residual-neutral {{ color: #525252; }}
  .reset-btn {{ padding: 6px 12px; border: 1px solid #d0d0d0; background: #fff; border-radius: 6px; cursor: pointer; font-size: 13px; }}
  .reset-btn:hover {{ background: #f5f5f5; }}
  .empty {{ padding: 40px; text-align: center; color: #999; font-style: italic; }}
  details.about {{ background: #fff; border-bottom: 1px solid #e0e0e0; padding: 12px 24px; font-size: 13px; line-height: 1.55; color: #333; }}
  details.about summary {{ cursor: pointer; font-weight: 600; color: #1d1d1f; padding: 4px 0; user-select: none; }}
  details.about summary:hover {{ color: #0070c9; }}
  details.about[open] summary {{ margin-bottom: 8px; }}
  details.about h3 {{ font-size: 13px; margin: 14px 0 4px; color: #1d1d1f; }}
  details.about p {{ margin: 4px 0; }}
  details.about code {{ background: #f0f0f3; padding: 1px 5px; border-radius: 3px; font-size: 12px; }}
  details.about ul {{ margin: 4px 0 4px 18px; padding: 0; }}
  details.about li {{ margin: 2px 0; }}
  details.about .note {{ color: #666; font-style: italic; }}
</style>
</head>
<body>
<header>
  <h1>Bike Valuer</h1>
  <div class="sub">Facebook Marketplace gravel-search dump near Sherwood Park, AB. Ranked by depreciation-model residual: most-negative = best value.</div>
</header>

<details class="about">
  <summary>How these listings are generated &amp; how the deals are scored ▾</summary>

  <h3>1. Where the listings come from</h3>
  <p>
    Facebook Marketplace search for the term <code>gravel bike</code> centred on Sherwood Park, AB
    (location ID <code>104044399631602</code>) with a <strong>30 km radius</strong>. FB's own
    search ranker decides what's "relevant" — that's why the table also contains mountain
    bikes, BMX, e-bikes, kids' bikes, etc. The script just keeps whatever FB returned.
  </p>

  <h3>2. Identifying the bike &amp; its original MSRP</h3>
  <p>
    Each listing's title + description goes to an LLM (OpenAI <code>gpt-4.1-mini</code> with web
    search). It does three things:
  </p>
  <ul>
    <li>Decides if the listing is actually a complete bike (filters out parts, accessories, exercise machines, kids' balance bikes, bait listings).</li>
    <li>Extracts brand, model, year, and bike type from the description (the description is the truth — titles on FB are often clickbait).</li>
    <li>Searches the web for the bike's original MSRP at launch in CAD.</li>
  </ul>
  <p>
    For listings the text pass can't price (generic "blue mountain bike", no decals in the
    title/description), a second pass attaches the listing's primary photo and asks the LLM
    to read decals, frame silhouette, and drivetrain from the image, then look up an MSRP.
  </p>

  <h3>3. The depreciation model (how "Predicted" and "Residual %" are computed)</h3>
  <p>
    A single ridge regression on log-transformed prices:
  </p>
  <p>
    <code>log(price) = a · log(MSRP) + b · log(age + 1) + brand + bike_type + condition + groupset</code>
  </p>
  <ul>
    <li><strong>log(MSRP)</strong> — the dominant feature. A $4k-MSRP bike sells for roughly 2× a $2k-MSRP bike, all else equal. Coefficient typically lands around 0.7–1.0.</li>
    <li><strong>log(age+1)</strong> — depreciation. Most value is lost in the first 2-3 years and the curve flattens after; <code>log</code> captures that shape. Coefficient is negative.</li>
    <li><strong>Brand / bike type / condition / groupset</strong> — categorical "shifters." Each value gets its own learned offset (e.g. <code>like_new</code> bumps the predicted price up, <code>fair</code> bumps it down). Categories appearing fewer than 2 times are pooled to avoid overfitting to one-offs.</li>
    <li><strong>Why logs?</strong> Bike prices span $200 → $15k and depreciation is multiplicative ("loses ~20% per year"), not additive. Logs turn that into a straight line the model can fit.</li>
    <li><strong>Why ridge?</strong> A small penalty (<code>alpha=1.0</code>) on coefficient size keeps rare brands/groupsets from getting wild offsets when only 2-3 listings exist for them.</li>
  </ul>
  <p>
    The model predicts each bike's price, and <strong>Residual %</strong> = (asking − predicted) / predicted × 100.
    Most-negative = priced furthest below what the curve says a bike of that MSRP/age/brand/type/condition/groupset
    <em>should</em> sell for. The table sorts ascending by this column, so the top rows are
    the deepest discounts relative to the model.
  </p>

  <h3>4. What "Residual" really means &amp; caveats</h3>
  <ul>
    <li>The model is fit and scored on the same data (in-sample). It tells you "cheaper than its peers in this scrape," not a held-out forecast.</li>
    <li>MSRPs from the LLM are best-effort. For old or no-name bikes the LLM is asked to mark <code>confidence=low</code>; those still get a residual but it's noisier.</li>
    <li>Listings the LLM couldn't price (no MSRP found, or flagged as not-a-bike) appear in the table with em-dashes — they aren't ranked.</li>
    <li>Some listings are bait — title says one bike, description/photo describes another. The LLM is prompted to ignore the title when it conflicts with the description, but a few will still slip through.</li>
  </ul>

  <p class="note">
    Pipeline source: <a href="https://github.com/devon7y/bike-valuer" target="_blank" rel="noopener">github.com/devon7y/bike-valuer</a>.
    Run: scrape → parse → LLM enrich (text + image fallback) → ridge model → this page.
  </p>
</details>

<div class="filters">
  <div class="filter">
    <label>Min price (CAD)</label>
    <input type="number" id="minPrice" min="0" step="50" placeholder="0">
  </div>
  <div class="filter">
    <label>Max price (CAD)</label>
    <input type="number" id="maxPrice" min="0" step="50" placeholder="∞">
  </div>
  <div class="filter">
    <label>Min residual %</label>
    <input type="number" id="minResid" step="5" placeholder="−100">
  </div>
  <div class="filter">
    <label>Max residual %</label>
    <input type="number" id="maxResid" step="5" placeholder="+100">
  </div>
  <div class="filter">
    <label>Min year</label>
    <input type="number" id="minYear" min="1980" max="2030" step="1" placeholder="any">
  </div>
  <div class="filter">
    <label>Bike type (cmd/ctrl-click multi)</label>
    <select id="typeSel" multiple></select>
  </div>
  <div class="filter">
    <label>Condition (cmd/ctrl-click multi)</label>
    <select id="condSel" multiple></select>
  </div>
  <div class="filter">
    <label>Search title/brand/model</label>
    <input type="text" id="searchBox" placeholder="e.g. gravel, kona, carbon">
  </div>
  <div class="filter">
    <label>&nbsp;</label>
    <button class="reset-btn" id="resetBtn">Reset filters</button>
  </div>
</div>

<div class="meta" id="meta"></div>

<table id="tbl">
  <thead>
    <tr>
      <th data-key="residual">Residual %<span class="arrow">▲</span></th>
      <th data-key="price">Price<span class="arrow"></span></th>
      <th data-key="pred">Predicted<span class="arrow"></span></th>
      <th data-key="msrp">MSRP<span class="arrow"></span></th>
      <th data-key="brand">Brand<span class="arrow"></span></th>
      <th data-key="model">Model<span class="arrow"></span></th>
      <th data-key="year">Year<span class="arrow"></span></th>
      <th data-key="type">Type<span class="arrow"></span></th>
      <th data-key="condition">Cond.<span class="arrow"></span></th>
      <th data-key="title">Title / Link<span class="arrow"></span></th>
    </tr>
  </thead>
  <tbody id="tbody"></tbody>
</table>

<script>
const DATA = {data_json};
const TYPES = {types_json};
const CONDITIONS = {conditions_json};

const typeSel = document.getElementById('typeSel');
TYPES.forEach(t => {{
  const o = document.createElement('option');
  o.value = t; o.textContent = t;
  typeSel.appendChild(o);
}});

const condSel = document.getElementById('condSel');
CONDITIONS.forEach(c => {{
  const o = document.createElement('option');
  o.value = c; o.textContent = c;
  condSel.appendChild(o);
}});

let sortKey = 'residual';
let sortDir = 1; // 1 = asc, -1 = desc

function fmt(v, dollar=false) {{
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  if (typeof v === 'number') return (dollar ? '$' : '') + v.toLocaleString(undefined, {{maximumFractionDigits: 0}});
  return v;
}}

function residualClass(r) {{
  if (r === null || r === undefined) return 'residual-neutral';
  if (r <= -25) return 'residual-good';
  if (r >= 15) return 'residual-bad';
  return 'residual-neutral';
}}

function getFilters() {{
  return {{
    minPrice: parseFloat(document.getElementById('minPrice').value) || -Infinity,
    maxPrice: parseFloat(document.getElementById('maxPrice').value) || Infinity,
    minResid: parseFloat(document.getElementById('minResid').value),
    maxResid: parseFloat(document.getElementById('maxResid').value),
    minYear: parseFloat(document.getElementById('minYear').value) || 0,
    types: Array.from(typeSel.selectedOptions).map(o => o.value),
    conditions: Array.from(condSel.selectedOptions).map(o => o.value),
    search: document.getElementById('searchBox').value.toLowerCase().trim(),
  }};
}}

function applyFilters(rows, f) {{
  return rows.filter(r => {{
    if (r.price === null || r.price < f.minPrice || r.price > f.maxPrice) return false;
    if (!Number.isNaN(f.minResid) && r.residual !== null && r.residual < f.minResid) return false;
    if (!Number.isNaN(f.maxResid) && r.residual !== null && r.residual > f.maxResid) return false;
    if (f.minYear && (r.year === null || r.year < f.minYear)) return false;
    if (f.types.length && !f.types.includes(r.type)) return false;
    if (f.conditions.length && !f.conditions.includes(r.condition)) return false;
    if (f.search) {{
      const hay = (r.title + ' ' + r.brand + ' ' + r.model + ' ' + r.type).toLowerCase();
      if (!hay.includes(f.search)) return false;
    }}
    return true;
  }});
}}

function sortRows(rows, key, dir) {{
  return [...rows].sort((a, b) => {{
    let av = a[key], bv = b[key];
    if (av === null || av === undefined) av = (typeof bv === 'number' ? Infinity * dir : '');
    if (bv === null || bv === undefined) bv = (typeof av === 'number' ? Infinity * dir : '');
    if (typeof av === 'string') return av.localeCompare(bv) * dir;
    return (av - bv) * dir;
  }});
}}

function render() {{
  const f = getFilters();
  let rows = applyFilters(DATA, f);
  rows = sortRows(rows, sortKey, sortDir);

  document.getElementById('meta').textContent =
    `Showing ${{rows.length}} of ${{DATA.length}} listings · sort: ${{sortKey}} ${{sortDir > 0 ? '↑' : '↓'}}`;

  const tbody = document.getElementById('tbody');
  if (!rows.length) {{
    tbody.innerHTML = '<tr><td colspan="10" class="empty">No listings match these filters.</td></tr>';
    return;
  }}
  tbody.innerHTML = rows.map(r => {{
    const rcls = residualClass(r.residual);
    return `
      <tr>
        <td class="num ${{rcls}}">${{r.residual !== null ? r.residual.toFixed(0) + '%' : '—'}}</td>
        <td class="num">${{fmt(r.price, true)}}</td>
        <td class="num">${{fmt(r.pred, true)}}</td>
        <td class="num">${{fmt(r.msrp, true)}}</td>
        <td>${{r.brand || '—'}}</td>
        <td>${{r.model || '—'}}</td>
        <td class="num">${{r.year || '—'}}</td>
        <td>${{r.type || '—'}}</td>
        <td>${{r.condition || '—'}}</td>
        <td class="title"><a href="${{r.url}}" target="_blank" rel="noopener">${{r.title || '(no title)'}}</a></td>
      </tr>`;
  }}).join('');

  document.querySelectorAll('th').forEach(th => {{
    const arrow = th.querySelector('.arrow');
    if (th.dataset.key === sortKey) {{
      arrow.textContent = sortDir > 0 ? '▲' : '▼';
    }} else {{
      arrow.textContent = '';
    }}
  }});
}}

document.querySelectorAll('th').forEach(th => {{
  th.addEventListener('click', () => {{
    const key = th.dataset.key;
    if (sortKey === key) sortDir *= -1;
    else {{ sortKey = key; sortDir = 1; }}
    render();
  }});
}});

['minPrice','maxPrice','minResid','maxResid','minYear','searchBox'].forEach(id => {{
  document.getElementById(id).addEventListener('input', render);
}});
typeSel.addEventListener('change', render);
condSel.addEventListener('change', render);

document.getElementById('resetBtn').addEventListener('click', () => {{
  ['minPrice','maxPrice','minResid','maxResid','minYear','searchBox'].forEach(id => {{
    document.getElementById(id).value = '';
  }});
  Array.from(typeSel.options).forEach(o => o.selected = false);
  Array.from(condSel.options).forEach(o => o.selected = false);
  sortKey = 'residual'; sortDir = 1;
  render();
}});

render();
</script>
</body>
</html>"""

    OUT.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT} ({len(rows)} listings, {len(bike_types)} bike types)")


if __name__ == "__main__":
    main()
