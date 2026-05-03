# Bike Valuer

A model-priced view of Facebook Marketplace bicycle listings near Sherwood Park, AB.

The pipeline scrapes Marketplace, asks an LLM (with web search and an image-fallback pass) to identify each bike's brand/model/year and original MSRP in CAD, then fits a depreciation model on the result and flags listings priced well below the model's prediction.

**Live page:** see GitHub Pages for this repo.

## Pipeline

```
scrape.py        → listings/<item_id>.html  (Playwright + saved FB session)
parse.py         → bikes.csv                (title, price, condition, image_url, …)
msrp_lookup.py   → enriched_bikes.csv       (LLM brand/model/MSRP, text pass)
msrp_lookup.py --image-fallback             (vision pass for missing-MSRP rows)
value.py         → deals.csv                (depreciation model + residuals)
build_html.py    → index.html               (sortable/filterable single-page UI)
```

`storage_state.json` (Facebook session cookie), `listings/` (raw scraped HTML), and the CSV outputs are intentionally excluded from this repo.
