"""
Cross-dataset macro pattern miner.

Goal: find non-obvious combinations of macro features that predict NQ moves.
Approach: stack all macro panels (CFTC, FRED, TGA, AAII, NAAIM), align to
daily, build forward NQ return targets, then use:

  1. Gradient-boosted decision trees (sklearn) to find feature importances
     and interactions automatically.
  2. Per-feature decile analysis: for each feature, which deciles produce
     the highest / lowest forward NQ returns.
  3. Pair-feature analysis: top combinations of two features whose joint
     extreme states predict moves.
  4. Sanity check: train/test split (2022-2024 train, 2024-2026 test)
     so we don't over-fit.

Outputs:
  data/macro_pattern_findings.json   structured results
  data/macro_pattern_findings.html   visual report
"""
from __future__ import annotations

import base64, io, json
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"


def fig_to_b64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def load_panel() -> pd.DataFrame:
    """Stack all macro panels to a daily DataFrame."""
    cftc = pd.read_csv(DATA/"cftc_nq_features.csv.gz", parse_dates=["date"])
    cftc = cftc[cftc["contract"].str.contains("Consolidated", case=False, na=False)]
    cftc = cftc.set_index("date")[[
        "asset_mgr_net_long","lev_money_net_long","retail_net_long",
        "am_minus_lm","asset_mgr_net_long_z52w","retail_net_long_z52w","lev_money_net_long_z52w",
    ]]
    cftc.columns = ["cftc_" + c for c in cftc.columns]

    macro = pd.read_csv(DATA/"macro_features.csv.gz", parse_dates=["date"]).set_index("date")
    macro = macro[[
        "vix","vxv","dgs10","sofr","iorb","effr","dxy","hy_spread","wti","t10y2y","t10y3m",
        "vix_term_struct","sofr_iorb","real_rate_proxy","vix_5d_change","hy_5d_change",
        "dxy_5d_change","dxy_20d_change","yc_change_20d","wti_5d_change",
    ]]

    tga = pd.read_csv(DATA/"tga_features.csv.gz", parse_dates=["date"]).set_index("date")
    tga = tga[["tga","tga_change_5d","tga_change_20d","tga_pct_5d","tga_z_1y"]]

    aaii = pd.read_csv(DATA/"aaii_features.csv.gz").rename(columns={"Unnamed: 0":"date"})
    aaii["date"] = pd.to_datetime(aaii["date"]); aaii = aaii.set_index("date")
    aaii = aaii[["bull","bear","bull_bear","bull_z52w","bear_z52w","bull_bear_z52w"]]
    aaii.columns = ["aaii_" + c for c in aaii.columns]

    naaim = pd.read_csv(DATA/"naaim_features.csv.gz").rename(columns={"Unnamed: 0":"date"})
    naaim["date"] = pd.to_datetime(naaim["date"]); naaim = naaim.set_index("date")
    naaim = naaim[["naaim","naaim_z52w","naaim_4w_ma","naaim_change_4w","naaim_dispersion"]]
    naaim.columns = ["naaim_" + c if not c.startswith("naaim") else c for c in naaim.columns]

    for d in [cftc, macro, tga, aaii, naaim]:
        d.index = d.index.tz_localize(None) if d.index.tz else d.index

    panel = macro.join(tga, how="outer").join(cftc, how="outer").join(aaii, how="outer").join(naaim, how="outer")
    panel = panel.sort_index().ffill()
    return panel


def add_targets(panel: pd.DataFrame) -> pd.DataFrame:
    """Use SPX from naaim file as proxy (we have NQ via QQQ if needed)."""
    naaim_full = pd.read_excel(DATA/"research_data/naaim.xlsx", sheet_name=0)
    naaim_full["date"] = pd.to_datetime(naaim_full["Date"], errors="coerce")
    naaim_full = naaim_full.dropna(subset=["date"])
    spx = naaim_full[["date","S&P 500"]].rename(columns={"S&P 500":"spx"}).set_index("date")
    spx = spx.dropna().sort_index()
    spx = spx[~spx.index.duplicated(keep="first")]
    spx.index = spx.index.tz_localize(None) if spx.index.tz else spx.index
    spx = spx.resample("D").ffill()
    spx["spx_ret_1d"] = spx["spx"].pct_change(1).shift(-1)
    spx["spx_ret_5d"] = spx["spx"].pct_change(5).shift(-5)
    spx["spx_ret_20d"] = spx["spx"].pct_change(20).shift(-20)
    panel = panel.join(spx[["spx_ret_1d","spx_ret_5d","spx_ret_20d"]], how="left")
    return panel


def main():
    print("="*72)
    print("MACRO PATTERN MINER — find emergent cross-dataset signals")
    print("="*72)

    panel = load_panel()
    print(f"\nPanel: {panel.shape}, cols: {list(panel.columns)[:5]}...")

    panel = add_targets(panel)
    panel = panel.dropna(subset=["spx_ret_1d","spx_ret_5d"])
    feature_cols = [c for c in panel.columns if not c.startswith("spx_ret")]
    panel = panel.dropna(subset=feature_cols, how="all")
    panel[feature_cols] = panel[feature_cols].ffill()
    panel = panel.dropna(subset=feature_cols)
    print(f"Aligned panel: {len(panel):,} days  ({panel.index.min().date()} → {panel.index.max().date()})")
    print(f"Features: {len(feature_cols)}")

    # Train/test split: 2022-2023 train, 2024-2026 test
    split = pd.Timestamp("2024-01-01")
    train = panel[panel.index < split]
    test  = panel[panel.index >= split]
    print(f"Train: {len(train)}    Test: {len(test)}")

    X_train = train[feature_cols].values
    y_train_5d = (train["spx_ret_5d"] > 0).astype(int).values
    X_test = test[feature_cols].values
    y_test_5d = (test["spx_ret_5d"] > 0).astype(int).values

    # ---- Gradient Boosting feature importance ----
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.metrics import accuracy_score, roc_auc_score
    print("\nTraining GradientBoosting on next-5d-positive target ...")
    gbm = GradientBoostingClassifier(n_estimators=120, max_depth=3, learning_rate=0.05,
                                      random_state=42)
    gbm.fit(X_train, y_train_5d)
    train_acc = gbm.score(X_train, y_train_5d)
    test_acc  = gbm.score(X_test, y_test_5d)
    test_auc  = roc_auc_score(y_test_5d, gbm.predict_proba(X_test)[:,1])
    print(f"  Train acc:  {train_acc*100:.1f}%")
    print(f"  Test  acc:  {test_acc*100:.1f}%   (random=51-52%)")
    print(f"  Test  AUC:  {test_auc:.3f}    (random=0.500)")

    importance = pd.DataFrame({
        "feature": feature_cols,
        "importance": gbm.feature_importances_,
    }).sort_values("importance", ascending=False)

    print("\nTop 15 features by importance:")
    for _, r in importance.head(15).iterrows():
        print(f"  {r['feature']:<35} {r['importance']*100:>6.2f}%")

    # ---- Per-feature decile analysis on TEST set ----
    print("\nPer-feature decile analysis (5-day forward SPX return, on TEST 2024-2026):")
    decile_results = []
    for feat in importance.head(15)["feature"]:
        try:
            test_clean = test.dropna(subset=[feat, "spx_ret_5d"])
            if len(test_clean) < 50:
                continue
            test_clean["dec"] = pd.qcut(test_clean[feat], 10, duplicates="drop", labels=False)
            grouped = test_clean.groupby("dec", observed=True)["spx_ret_5d"].agg(["mean","count"])
            grouped.columns = ["mean_5d_ret","n"]
            top = grouped.iloc[-1]; bot = grouped.iloc[0]
            spread = top["mean_5d_ret"] - bot["mean_5d_ret"]
            decile_results.append({
                "feature": feat,
                "low_decile_ret": float(bot["mean_5d_ret"]),
                "high_decile_ret": float(top["mean_5d_ret"]),
                "spread": float(spread),
                "n_low": int(bot["n"]),
                "n_high": int(top["n"]),
            })
        except Exception as e:
            continue

    decile_df = pd.DataFrame(decile_results).sort_values("spread", key=abs, ascending=False)
    print(f"\nTop 10 features by decile-spread (low decile vs high decile fwd ret):")
    for _, r in decile_df.head(10).iterrows():
        print(f"  {r['feature']:<32}  low={r['low_decile_ret']*100:>+5.2f}%  "
              f"high={r['high_decile_ret']*100:>+5.2f}%  spread={r['spread']*100:>+5.2f}pp")

    # ---- Pair-feature analysis: combinations of top-5 features ----
    print("\nPair-feature regime test (joint extreme states):")
    top5 = importance.head(5)["feature"].tolist()
    pair_results = []
    test_c = test.dropna(subset=top5 + ["spx_ret_5d"])
    for f1 in top5:
        for f2 in top5:
            if f1 >= f2: continue
            q1_low = test_c[f1].quantile(0.20)
            q1_high = test_c[f1].quantile(0.80)
            q2_low = test_c[f2].quantile(0.20)
            q2_high = test_c[f2].quantile(0.80)

            for label, mask in [
                ("low/low",   (test_c[f1]<=q1_low)  & (test_c[f2]<=q2_low)),
                ("low/high",  (test_c[f1]<=q1_low)  & (test_c[f2]>=q2_high)),
                ("high/low",  (test_c[f1]>=q1_high) & (test_c[f2]<=q2_low)),
                ("high/high", (test_c[f1]>=q1_high) & (test_c[f2]>=q2_high)),
            ]:
                sub = test_c[mask]
                if len(sub) < 10: continue
                fwd = sub["spx_ret_5d"].mean()
                pair_results.append({
                    "f1": f1, "f2": f2, "regime": label,
                    "n": len(sub), "mean_fwd_5d_ret": float(fwd),
                })

    pair_df = pd.DataFrame(pair_results).sort_values("mean_fwd_5d_ret", key=abs, ascending=False)
    print(f"\nTop 10 pair-regime combos (rare states, biggest fwd return signal):")
    for _, r in pair_df.head(10).iterrows():
        print(f"  {r['f1'][:18]:<19} × {r['f2'][:18]:<19} ({r['regime']:>8})  "
              f"n={r['n']:>3}  fwd 5d ret={r['mean_fwd_5d_ret']*100:>+6.2f}%")

    # ---- Save findings JSON ----
    findings = {
        "panel_shape": list(panel.shape),
        "n_features": len(feature_cols),
        "train_acc": float(train_acc),
        "test_acc": float(test_acc),
        "test_auc": float(test_auc),
        "top_features": importance.head(20).to_dict("records"),
        "decile_analysis": decile_df.to_dict("records"),
        "pair_regimes": pair_df.head(30).to_dict("records"),
    }
    (DATA/"macro_pattern_findings.json").write_text(json.dumps(findings, indent=2, default=str))
    print(f"\nWrote -> data/macro_pattern_findings.json")

    # ---- Build HTML report ----
    fig, ax = plt.subplots(figsize=(11, 8))
    top20 = importance.head(20).iloc[::-1]
    ax.barh(top20["feature"], top20["importance"]*100, color="steelblue", alpha=0.85)
    ax.set_xlabel("Feature Importance (%)")
    ax.set_title("Top 20 Macro Features — Predicting NQ/SPX 5-Day Forward Direction", fontsize=13)
    ax.grid(axis="x", alpha=0.3)
    chart1 = fig_to_b64(fig)

    fig, ax = plt.subplots(figsize=(11, 6))
    top10_dec = decile_df.head(10).iloc[::-1]
    y = np.arange(len(top10_dec))
    ax.barh(y, top10_dec["low_decile_ret"]*100, height=0.4, label="Low decile", color="#dc3545", alpha=0.85)
    ax.barh(y+0.4, top10_dec["high_decile_ret"]*100, height=0.4, label="High decile", color="#28a745", alpha=0.85)
    ax.set_yticks(y+0.2); ax.set_yticklabels(top10_dec["feature"])
    ax.set_xlabel("5-day forward SPX return (%)")
    ax.set_title("Per-Feature Decile Spread (TEST 2024-2026)", fontsize=13)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.legend(); ax.grid(axis="x", alpha=0.3)
    chart2 = fig_to_b64(fig)

    # Pair regimes table HTML
    pair_rows = ""
    for _, r in pair_df.head(15).iterrows():
        c = "#28a745" if r["mean_fwd_5d_ret"] > 0 else "#dc3545"
        pair_rows += f"""<tr>
        <td>{r['f1']}</td><td>{r['f2']}</td>
        <td>{r['regime']}</td><td>{r['n']}</td>
        <td style="color:{c};font-weight:bold">{r['mean_fwd_5d_ret']*100:+.2f}%</td>
        </tr>"""

    feat_rows = ""
    for _, r in importance.head(20).iterrows():
        feat_rows += f"<tr><td>{r['feature']}</td><td>{r['importance']*100:.2f}%</td></tr>"

    decile_rows = ""
    for _, r in decile_df.head(15).iterrows():
        cl = "#dc3545" if r["low_decile_ret"]<0 else "#28a745"
        ch = "#dc3545" if r["high_decile_ret"]<0 else "#28a745"
        spread_pct = r["spread"]*100
        sc = "#28a745" if spread_pct > 0 else "#dc3545"
        decile_rows += f"""<tr>
        <td>{r['feature']}</td>
        <td style="color:{cl}">{r['low_decile_ret']*100:+.2f}%</td>
        <td style="color:{ch}">{r['high_decile_ret']*100:+.2f}%</td>
        <td style="color:{sc};font-weight:bold">{spread_pct:+.2f}pp</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>HFTBot — Macro Pattern Mining</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       max-width: 1200px; margin: 24px auto; padding: 0 20px; color:#222; background:#f8f9fa; }}
h1 {{ font-size:28px; border-bottom:3px solid #007bff; padding-bottom:10px; }}
h2 {{ font-size:22px; margin-top:36px; color:#007bff; }}
table {{ width:100%; border-collapse:collapse; background:white; box-shadow:0 2px 4px rgba(0,0,0,0.06); margin:12px 0; }}
th,td {{ padding:8px 10px; text-align:left; border-bottom:1px solid #e9ecef; font-size:13px; }}
th {{ background:#f1f3f5; font-weight:600; }}
.summary {{ display:grid; grid-template-columns:repeat(3,1fr); gap:16px; margin:20px 0; }}
.card {{ background:white; padding:16px; border-radius:8px; box-shadow:0 2px 4px rgba(0,0,0,0.06); }}
.card .num {{ font-size:28px; font-weight:bold; color:#007bff; }}
.card .lbl {{ color:#666; font-size:12px; text-transform:uppercase; }}
img {{ max-width:100%; border-radius:8px; box-shadow:0 2px 4px rgba(0,0,0,0.06); margin:12px 0; }}
</style></head><body>

<h1>HFTBot — Cross-Dataset Macro Pattern Mining</h1>
<p style="color:#666;">All macro panels stacked (CFTC + FRED + TGA + AAII + NAAIM = {len(feature_cols)} features). Target: SPX 5-day forward direction. Train 2022-2023, test 2024-2026.</p>

<h2>Headline</h2>
<div class="summary">
  <div class="card"><div class="lbl">Out-of-sample Accuracy</div><div class="num">{test_acc*100:.1f}%</div><div style="color:#666;font-size:12px;">vs ~52% random</div></div>
  <div class="card"><div class="lbl">Out-of-sample AUC</div><div class="num">{test_auc:.3f}</div><div style="color:#666;font-size:12px;">vs 0.500 random</div></div>
  <div class="card"><div class="lbl">Daily panel size</div><div class="num">{len(panel):,}</div><div style="color:#666;font-size:12px;">days, {len(feature_cols)} features</div></div>
</div>

<h2>Top 20 Most Important Features</h2>
<img src="data:image/png;base64,{chart1}" />
<table><tr><th>Feature</th><th>Importance</th></tr>{feat_rows}</table>

<h2>Decile Spread Analysis (TEST set)</h2>
<p>For each top feature, what is forward SPX return when the feature is in its lowest 10% vs highest 10%?</p>
<img src="data:image/png;base64,{chart2}" />
<table>
<tr><th>Feature</th><th>Low decile fwd 5d</th><th>High decile fwd 5d</th><th>Spread</th></tr>
{decile_rows}
</table>

<h2>Pair-Feature Regime Analysis</h2>
<p>Combinations of two features in extreme states — finds non-obvious "regime" signals.</p>
<table>
<tr><th>Feature 1</th><th>Feature 2</th><th>Regime</th><th>N obs</th><th>Avg fwd 5d ret</th></tr>
{pair_rows}
</table>

<p style="color:#999; margin-top:40px; font-size:12px;">Generated via gradient-boosted trees + decile + pair-regime analysis. research/macro_pattern_miner.py</p>
</body></html>"""

    (DATA/"macro_pattern_findings.html").write_text(html)
    print(f"Wrote -> data/macro_pattern_findings.html  ({len(html)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
