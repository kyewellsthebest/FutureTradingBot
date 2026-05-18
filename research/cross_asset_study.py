"""
Cross-asset lead-lag study — what predicts NQ that the bot doesn't use.

The deployed bot trades NQ vs ES (and VIX, RTY) divergence. The GitHub
Actions fetch landed 2 years of 5-min data for EIGHT CME futures:

  NQ ES RTY YM  (equity index)    ZN ZB  (treasuries)    GC CL (gold, oil)

The bot uses 4 of the 8. This study measures, for every other asset:

  * contemporaneous correlation with NQ
  * LEAD-LAG: does asset X's 5-min move at time t predict NQ's move at
    t+k?  (k>0 means X leads NQ — a genuinely predictive, tradeable edge)
  * vs NQ's own autocorrelation at the same lag — a cross-asset signal is
    only worth mining if it beats what NQ already says about itself
  * spread mean-reversion: OLS hedge ratio + AR(1) half-life of the
    NQ-vs-X residual spread — how fast a price divergence closes
  * regime conditioning: does the relationship strengthen in high vol?

Output ranks the strongest UNTAPPED cross-asset signals so the next
mining run knows which new divergence families are worth building.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
POLY = PROJECT_ROOT / "data" / "polygon"
OUT = PROJECT_ROOT / "data" / "cross_asset_study.json"
logger = logging.getLogger("cross_asset")

ASSETS = ["NQ", "ES", "RTY", "YM", "ZN", "ZB", "GC", "CL"]
MAX_LAG = 6   # 6 bars = 30 minutes


def load(sym: str) -> pd.DataFrame:
    df = pd.read_csv(POLY / f"{sym}_5min.csv", parse_dates=["ts"])
    df = df.set_index("ts").sort_index()
    return df[~df.index.duplicated(keep="last")]


def half_life(spread: pd.Series) -> float:
    """AR(1) half-life of a mean-reverting series, in bars."""
    s = spread.dropna()
    if len(s) < 200:
        return np.nan
    lag = s.shift(1).dropna()
    cur = s.loc[lag.index]
    A = np.vstack([lag.values, np.ones(len(lag))]).T
    phi, _ = np.linalg.lstsq(A, cur.values, rcond=None)[0]
    if not (0 < phi < 1):
        return np.nan
    return float(-np.log(2) / np.log(phi))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])
    logger.info("Loading 8 products...")
    data = {s: load(s) for s in ASSETS}
    for s in ASSETS:
        logger.info(f"  {s}: {len(data[s]):,} bars "
                    f"{data[s].index[0].date()} -> {data[s].index[-1].date()}")

    nq = data["NQ"]
    nq_ret_full = np.log(nq["close"]).diff()
    vol_pct = nq_ret_full.abs().rolling(500, min_periods=100).rank(pct=True)

    results = []
    for s in ASSETS:
        if s == "NQ":
            continue
        x = data[s]
        idx = nq.index.intersection(x.index)
        if len(idx) < 5000:
            logger.warning(f"{s}: only {len(idx)} common bars — skipped")
            continue
        nr = np.log(nq.loc[idx, "close"]).diff()
        xr = np.log(x.loc[idx, "close"]).diff()
        vp = vol_pct.reindex(idx)
        df = pd.DataFrame({"nr": nr, "xr": xr, "vp": vp}).dropna()

        contemp = df["nr"].corr(df["xr"])
        # lead-lag: corr( X_ret[t] , NQ_ret[t+k] )  — k>0 => X leads NQ
        leads = {k: df["xr"].corr(df["nr"].shift(-k))
                 for k in range(1, MAX_LAG + 1)}
        nq_ac = {k: df["nr"].corr(df["nr"].shift(-k))
                 for k in range(1, MAX_LAG + 1)}
        best_k = max(leads, key=lambda k: abs(leads[k]))
        best_lead = leads[best_k]

        hi = df[df["vp"] >= 0.66]
        lo = df[df["vp"] < 0.33]
        lead_hi = (hi["xr"].corr(hi["nr"].shift(-best_k))
                   if len(hi) > 500 else np.nan)
        lead_lo = (lo["xr"].corr(lo["nr"].shift(-best_k))
                   if len(lo) > 500 else np.nan)

        # spread mean-reversion: log-price OLS hedge, AR(1) half-life
        npx = np.log(nq.loc[idx, "close"])
        xpx = np.log(x.loc[idx, "close"])
        sp = pd.DataFrame({"n": npx, "x": xpx}).dropna()
        A = np.vstack([sp["x"].values, np.ones(len(sp))]).T
        beta, c = np.linalg.lstsq(A, sp["n"].values, rcond=None)[0]
        spread = sp["n"] - (beta * sp["x"] + c)
        hl = half_life(spread)
        # an "edge ratio": how much the cross-asset lead beats NQ's own
        edge = abs(best_lead) - abs(nq_ac[best_k])
        results.append({
            "asset": s,
            "contemp_corr": round(float(contemp), 4),
            "best_lead_lag_bars": best_k,
            "best_lead_lag_min": best_k * 5,
            "best_lead_corr": round(float(best_lead), 4),
            "nq_autocorr_same_lag": round(float(nq_ac[best_k]), 4),
            "edge_over_nq_autocorr": round(float(edge), 4),
            "lead_corr_highvol": (round(float(lead_hi), 4)
                                  if np.isfinite(lead_hi) else None),
            "lead_corr_lowvol": (round(float(lead_lo), 4)
                                 if np.isfinite(lead_lo) else None),
            "all_lead_corrs": {k: round(float(v), 4) for k, v in leads.items()},
            "spread_half_life_bars": (round(hl, 1)
                                      if np.isfinite(hl) else None),
            "hedge_beta": round(float(beta), 3),
            "n_obs": int(len(df)),
        })

    results.sort(key=lambda r: -abs(r["best_lead_corr"]))

    # ---- conditional shock-response -------------------------------------
    # Unconditional lead-lag washes out event signals. This asks: after a
    # BIG 15-min move in asset X (top/bottom 5%), where does NQ go over the
    # next 15 and 30 min — and how often does it follow X's direction?
    logger.info("Conditional shock-response analysis...")
    shocks = []
    nq_close = nq["close"]
    for s in ASSETS:
        if s == "NQ":
            continue
        x = data[s]
        idx = nq.index.intersection(x.index)
        if len(idx) < 5000:
            continue
        npx = nq_close.loc[idx]
        xpx = x["close"].loc[idx]
        x3 = np.log(xpx / xpx.shift(3))                       # X 15-min move
        fwd3 = np.log(npx.shift(-3) / npx)                    # NQ next 15 min
        fwd6 = np.log(npx.shift(-6) / npx)                    # NQ next 30 min
        d = pd.DataFrame({"x3": x3, "f3": fwd3, "f6": fwd6}).dropna()
        if len(d) < 2000:
            continue
        hi = d["x3"].quantile(0.95)
        lo = d["x3"].quantile(0.05)
        up = d[d["x3"] >= hi]
        dn = d[d["x3"] <= lo]
        base3 = d["f3"].mean()
        # follow-rate: NQ moves the SAME direction as the X shock
        row = {
            "asset": s,
            "after_X_up_NQ_fwd30m_bps": round(float(up["f6"].mean()) * 1e4, 2),
            "after_X_up_follow_rate": round(float((up["f6"] > 0).mean()), 3),
            "after_X_down_NQ_fwd30m_bps": round(float(dn["f6"].mean()) * 1e4, 2),
            "after_X_down_follow_rate": round(float((dn["f6"] < 0).mean()), 3),
            "baseline_fwd30m_bps": round(float(d["f6"].mean()) * 1e4, 2),
            "n_shocks": int(len(up) + len(dn)),
        }
        # net directional edge = up-response minus down-response, in bps
        row["directional_edge_bps"] = round(
            row["after_X_up_NQ_fwd30m_bps"] - row["after_X_down_NQ_fwd30m_bps"], 2)
        shocks.append(row)
    shocks.sort(key=lambda r: -abs(r["directional_edge_bps"]))

    OUT.write_text(json.dumps({"max_lag_bars": MAX_LAG, "results": results,
                               "shock_response": shocks}, indent=2))

    print("\n" + "=" * 78)
    print("CROSS-ASSET LEAD-LAG — what predicts NQ (2yr, 5-min)")
    print("=" * 78)
    print(f"{'asset':<6}{'contemp':>9}{'lead@':>7}{'leadCorr':>10}"
          f"{'NQ-autoC':>10}{'edge':>8}{'hiVol':>8}{'loVol':>8}{'spr-HL':>9}")
    print("-" * 78)
    for r in results:
        hv = f"{r['lead_corr_highvol']:+.3f}" if r['lead_corr_highvol'] is not None else "  —"
        lv = f"{r['lead_corr_lowvol']:+.3f}" if r['lead_corr_lowvol'] is not None else "  —"
        hl = f"{r['spread_half_life_bars']}" if r['spread_half_life_bars'] is not None else "—"
        flag = "  <<<" if r["edge_over_nq_autocorr"] > 0.01 else ""
        print(f"{r['asset']:<6}{r['contemp_corr']:>+9.3f}"
              f"{r['best_lead_lag_min']:>5}m{r['best_lead_corr']:>+10.3f}"
              f"{r['nq_autocorr_same_lag']:>+10.3f}"
              f"{r['edge_over_nq_autocorr']:>+8.3f}{hv:>8}{lv:>8}{hl:>9}{flag}")
    print("-" * 78)
    print("contemp = same-bar corr w/ NQ | lead@ = lag where X best predicts")
    print("NQ's FUTURE move | edge = how much that beats NQ's own autocorr")
    print("(>0.01 flagged <<<) | spr-HL = bars for a price divergence to half-revert")

    print("\n" + "=" * 78)
    print("CONDITIONAL SHOCK-RESPONSE — NQ's next 30 min after a big move in X")
    print("=" * 78)
    print(f"{'asset':<6}{'X-up->NQ':>11}{'follow%':>9}{'X-dn->NQ':>11}"
          f"{'follow%':>9}{'dir-edge':>10}{'baseline':>10}")
    print("-" * 78)
    for r in shocks:
        print(f"{r['asset']:<6}{r['after_X_up_NQ_fwd30m_bps']:>+10.1f}b"
              f"{r['after_X_up_follow_rate']*100:>8.0f}%"
              f"{r['after_X_down_NQ_fwd30m_bps']:>+10.1f}b"
              f"{r['after_X_down_follow_rate']*100:>8.0f}%"
              f"{r['directional_edge_bps']:>+9.1f}b"
              f"{r['baseline_fwd30m_bps']:>+9.1f}b")
    print("-" * 78)
    print("X-up->NQ = NQ's avg 30-min move after a top-5% 15-min move in X")
    print("(bps) | follow% = how often NQ moved X's direction | dir-edge =")
    print("up-response minus down-response | baseline ~0 = NQ's unconditional drift")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
