"""
Fit a depreciation model on enriched bike listings:

  log(price) ~ log(MSRP) + log(age + 1) + condition + brand + bike_type + groupset

Then rank by residual. Most-negative residual = priced furthest below the
depreciation curve = best value.

Inputs: enriched_bikes.csv (bikes.csv + LLM-extracted fields incl. msrp_cad).
"""

import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline

ROOT = Path(__file__).parent
CSV = ROOT / "enriched_bikes.csv"
OUT = ROOT / "deals.csv"

CURRENT_YEAR = date.today().year


def main():
    df = pd.read_csv(CSV)
    print(f"Total listings: {len(df)}")

    df = df[df["llm_is_bike"] == True].copy()
    print(f"LLM-confirmed bikes: {len(df)}")

    df = df[df["price_cad"].notna() & (df["price_cad"] >= 200) & (df["price_cad"] <= 15000)].copy()
    print(f"With reasonable price: {len(df)}")

    df = df[df["llm_msrp_cad"].notna() & (df["llm_msrp_cad"] > 0)].copy()
    print(f"With MSRP: {len(df)}")

    before = len(df)
    df["dup_key"] = (
        df["description"].fillna("").str.lower().str.strip().str[:200]
        + "|" + df["price_cad"].astype(str)
    )
    df = df.sort_values("creation_date", ascending=False).drop_duplicates("dup_key", keep="first")
    df = df.drop(columns="dup_key")
    print(f"After dedupe: {len(df)} (removed {before - len(df)})")

    df["log_price"] = np.log(df["price_cad"])
    df["log_msrp"] = np.log(df["llm_msrp_cad"])

    df["effective_year"] = df["llm_year"].fillna(df["year"])
    median_year = df["effective_year"].median()
    df["effective_year"] = df["effective_year"].fillna(median_year)
    df["age"] = (CURRENT_YEAR - df["effective_year"]).clip(lower=0)
    df["log_age"] = np.log(df["age"] + 1)

    df["brand_f"] = df["llm_brand"].fillna(df["brand"]).fillna("Unknown")
    df["type_f"] = df["llm_bike_type"].fillna("unknown")
    df["cond_f"] = df["condition"].fillna("Unknown")
    df["grp_f"] = df["groupset"].fillna("Unknown")

    cat_cols = ["brand_f", "type_f", "cond_f", "grp_f"]
    num_cols = ["log_msrp", "log_age"]

    pre = ColumnTransformer(
        [("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=2), cat_cols),
         ("num", "passthrough", num_cols)]
    )
    model = Pipeline([("pre", pre), ("ridge", Ridge(alpha=1.0))])
    model.fit(df[cat_cols + num_cols], df["log_price"].values)

    df["pred_log_price"] = model.predict(df[cat_cols + num_cols])
    df["pred_price"] = np.exp(df["pred_log_price"])
    df["residual_log"] = df["log_price"] - df["pred_log_price"]
    df["residual_pct"] = (df["price_cad"] - df["pred_price"]) / df["pred_price"] * 100

    y = df["log_price"].values
    ss_res = float(np.sum((y - df["pred_log_price"]) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    print(f"\nIn-sample R^2 on log(price): {r2:.3f}  (n={len(df)})")

    coefs = model.named_steps["ridge"].coef_
    feat_names = (
        list(model.named_steps["pre"].named_transformers_["cat"].get_feature_names_out(cat_cols))
        + num_cols
    )
    msrp_idx = feat_names.index("log_msrp")
    age_idx = feat_names.index("log_age")
    print(f"  log_msrp coefficient: {coefs[msrp_idx]:.3f}  (expect ~0.7-1.0)")
    print(f"  log_age  coefficient: {coefs[age_idx]:.3f}   (expect negative)")

    deals = df.sort_values("residual_log").copy()
    cols = [
        "item_id", "title", "price_cad", "llm_msrp_cad", "pred_price", "residual_pct",
        "llm_brand", "llm_model", "effective_year", "llm_bike_type",
        "frame_size", "frame_material", "groupset", "condition",
        "llm_confidence", "llm_notes", "city", "url",
    ]
    deals[cols].to_csv(OUT, index=False)
    print(f"\nWrote ranked deals to {OUT}")

    def show(label, frame, n=15):
        print(f"\n=== {label} ===\n")
        for _, r in frame.head(n).iterrows():
            brand = r.get("llm_brand") or "?"
            mdl = r.get("llm_model") or "?"
            yr = int(r["effective_year"]) if not pd.isna(r["effective_year"]) else "?"
            btype = r.get("llm_bike_type") or "?"
            print(
                f"${r['price_cad']:>5.0f}  vs pred ${r['pred_price']:>5.0f} "
                f"({r['residual_pct']:+5.0f}%)  msrp ${r['llm_msrp_cad']:>5.0f}  | "
                f"{brand:<14} {mdl:<24} {yr!s:<5} {btype:<10}"
            )
            print(f"           {str(r['title'])[:90]}")
            print(f"           {r['url']}")
            print()

    show("Top 15 best-value bikes (all types, by residual)", deals, n=15)

    gravel_like = deals[deals["llm_bike_type"].isin(["gravel", "cyclocross", "endurance_road", "touring"])].copy()
    show(f"Top 10 best-value gravel/cx/all-road (n={len(gravel_like)})", gravel_like, n=10)


if __name__ == "__main__":
    main()
