"""
PRICE-FLOW STUDY — what the bot's own 97 strategies are actually surfing.

This is not a strategy search and not a filter. It dissects the live
deployment against the four things 8 years of NQ data proved govern price
flow, so the bot has a TRUE model of where its edge lives:

  1. EDGE LIFESPAN   — reconstruct every trade's unconstrained forward
                       path (close-to-entry, in R-units) bar by bar.
                       Mean-reversion has a ~3.5-bar half-life; if the
                       edge is front-loaded, a 75-90 min hold spends most
                       of its life holding a coin flip.
  2. ASYMMETRY       — oversold snaps back (+0.26% / 30min), overbought
                       does not (~0). So LONG (buy-dip) and SHORT
                       (fade-rip) reversion are NOT the same trade.
  3. VOL REGIME      — dislocations need volatility to exist AND to
                       revert. Split each trade by ATR percentile at
                       entry.
  4. MECHANISM       — sa_* triggers ride NQ-ES convergence (index
                       arbitrage — mechanical, steady). vix_* triggers
                       ride a sentiment divergence (behavioral, noisier).

Output: data/price_flow_study.json — aggregate curves + a per-strategy
profile ("this strategy is a high-vol morning oversold-snapback that
peaks at bar 4"), so the dashboard Brain tab and the bot can reason about
each strategy instead of treating it as an opaque "go" signal.
"""
from __future__ import annotations
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from research.pattern_miner_v6 import build_v6_features, label_strategy, StrategyDef
from research.pattern_miner_v7 import build_v7_extras
from research.pattern_miner_v8 import build_v8_extras
from research.pattern_miner_v9 import build_v9_extras
from research.pattern_miner_v11 import build_v11_extras, make_v11_detector_dicts
from research.pattern_miner_v12 import make_v12_detector_dicts
from research.pattern_miner_v13 import build_v13_extras, make_v13_detector_dicts
from research.local_data_loader import (
    load_daily, load_intraday_1min, load_intraday_5min, load_vix_5min,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
OUT_PATH = DATA / "price_flow_study.json"
logger = logging.getLogger("price_flow")

HORIZON = 18          # 5-min bars to walk forward (90 min — full max-hold)
HALF_LIFE_BAR = 3     # ~15 min — the measured reversion half-life


def load_deployed_specs() -> list[dict]:
    """Deployed strategies + their full specs, tagged with source + family."""
    deployed = set(json.loads((DATA / "deployed_strategies.json").read_text())
                   .get("names", []))
    out = []
    for fname, src in [("mined_v11_patterns.json", "v11"),
                       ("mined_v12_patterns.json", "v12"),
                       ("mined_v13_patterns.json", "v13")]:
        p = DATA / fname
        if not p.exists():
            continue
        for s in json.loads(p.read_text()).get("user_passers", []):
            if s["name"] not in deployed:
                continue
            trig = s.get("trigger", "")
            # sa_* = NQ-ES stat-arb (index-arb convergence — mechanical).
            # vix_* = VIX-divergence (sentiment — behavioral).
            family = "vix" if trig.startswith("vix") else (
                "rty" if trig.startswith("rty") else "stat_arb")
            s = dict(s)
            s["_source"] = src
            s["_family"] = family
            out.append(s)
    return out


def forward_paths(trades: pd.DataFrame, close: np.ndarray,
                  idx_of: dict) -> np.ndarray:
    """For each trade return signed excursion in R-units at bars 1..HORIZON.

    R-unit = (close[entry+k] - entry) * dir / stop_pts. R-units make the
    path comparable across 8 years (NQ 7k -> 25k) and across strategies
    with different ATR-scaled stops. NaN where the window runs off data.
    """
    n = len(trades)
    out = np.full((n, HORIZON), np.nan)
    entries = trades["entry"].to_numpy(dtype=float)
    dirs = np.where(trades["side"].to_numpy() == "LONG", 1.0, -1.0)
    stops = trades["stop_pts"].to_numpy(dtype=float)
    locs = np.array([idx_of.get(ts, -1) for ts in trades["entry_ts"]])
    for r in range(n):
        loc = locs[r]
        if loc < 0 or stops[r] <= 0:
            continue
        for k in range(1, HORIZON + 1):
            j = loc + k
            if j >= len(close):
                break
            out[r, k - 1] = (close[j] - entries[r]) * dirs[r] / stops[r]
    return out


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])

    logger.info("Loading data + features...")
    nq_5m = load_intraday_5min("nq")
    nq_1m = load_intraday_1min("nq")
    daily = load_daily("nq")
    es_5m = load_intraday_5min("es")
    rty_5m = load_intraday_5min("rty")
    vix_5m = load_vix_5min()
    for df in (nq_5m, nq_1m, daily, es_5m, rty_5m, vix_5m):
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
    F = build_v6_features(nq_5m, daily, es_5m, rty_5m, vix_5m)
    F = build_v7_extras(F, nq_5m, es_5m, vix_5m)
    F = build_v8_extras(F, nq_5m, daily)
    F = build_v9_extras(F, nq_5m, daily, rty_5m)
    F = build_v11_extras(F, nq_5m, es_5m)
    F = build_v13_extras(F, nq_5m, rty_5m, vix_5m)
    cd11, td11 = make_v11_detector_dicts(F)
    cd12, _ = make_v12_detector_dicts(F)
    cd13, td13 = make_v13_detector_dicts(F)
    contexts_d = {**cd11, **cd12, **cd13}
    triggers_d = {**td11, **td13}

    # Volatility regime + clock context per 5-min bar.
    close = nq_5m["close"].to_numpy(dtype=float)
    atr14 = F["atr14"].reindex(nq_5m.index)
    atr_pctile = atr14.rolling(2000, min_periods=200).rank(pct=True).to_numpy()
    ny_hour = nq_5m.index.tz_convert("America/New_York").hour.to_numpy()
    idx_of = {ts: i for i, ts in enumerate(nq_5m.index)}

    specs = load_deployed_specs()
    logger.info(f"Loaded {len(specs)} deployed strategies")

    # ---- per-trade record across the whole deployment --------------------
    all_paths = []          # list of (HORIZON,) R-unit arrays
    rec = defaultdict(list)  # parallel arrays of per-trade attributes
    profiles = []

    for i, s in enumerate(specs):
        if i % 15 == 0:
            logger.info(f"  labeling {i+1}/{len(specs)}...")
        strat = StrategyDef(
            name=s["name"], side=s["side"], contexts=s["contexts"],
            trigger=s["trigger"], context_window_bars=5,
            stop_atr=s["stop_atr"], target_atr=s["target_atr"],
            max_hold_min=s["max_hold_min"],
        )
        try:
            tr = label_strategy(F, nq_5m, nq_1m, daily, strat,
                                contexts_d, triggers_d)
        except Exception as e:
            logger.warning(f"  {s['name']} skipped: {e}")
            continue
        if tr.empty:
            continue
        paths = forward_paths(tr, close, idx_of)
        locs = np.array([idx_of.get(ts, -1) for ts in tr["entry_ts"]])
        valid = locs >= 0
        ent_pct = np.where(valid, atr_pctile[np.where(valid, locs, 0)], np.nan)
        ent_hr = np.where(valid, ny_hour[np.where(valid, locs, 0)], -1)
        final_R = (tr["pts"].to_numpy(dtype=float)
                   / np.where(tr["stop_pts"] > 0, tr["stop_pts"], np.nan))

        for r in range(len(tr)):
            all_paths.append(paths[r])
            rec["side"].append(tr["side"].iloc[r])
            rec["family"].append(s["_family"])
            rec["source"].append(s["_source"])
            rec["name"].append(s["name"])
            rec["atr_pctile"].append(ent_pct[r])
            rec["hour"].append(int(ent_hr[r]))
            rec["final_R"].append(final_R[r])
            rec["outcome"].append(tr["outcome"].iloc[r])

        # ---- per-strategy profile ---------------------------------------
        P = np.array([p for p in paths])
        mean_curve = np.nanmean(P, axis=0)
        peak_bar = int(np.nanargmax(mean_curve)) + 1
        peak_R = float(np.nanmax(mean_curve))
        end_R = float(mean_curve[-1])
        pcts = ent_pct[~np.isnan(ent_pct)]
        hrs = ent_hr[ent_hr >= 0]
        profiles.append({
            "name": s["name"], "source": s["_source"],
            "family": s["_family"], "side": s["side"],
            "n_trades": int(len(tr)),
            "peak_bar": peak_bar,
            "peak_R": round(peak_R, 3),
            "R_at_bar18": round(end_R, 3),
            "give_back_R": round(peak_R - end_R, 3),
            "median_entry_vol_pctile": (round(float(np.median(pcts)), 2)
                                        if len(pcts) else None),
            "modal_entry_hour_ny": (int(np.bincount(hrs).argmax())
                                    if len(hrs) else None),
        })

    P = np.array(all_paths)                       # (N_trades, HORIZON)
    side = np.array(rec["side"])
    family = np.array(rec["family"])
    apct = np.array(rec["atr_pctile"], dtype=float)
    hour = np.array(rec["hour"])
    finalR = np.array(rec["final_R"], dtype=float)
    N = len(P)
    logger.info(f"Reconstructed forward paths for {N:,} trades")

    def curve(mask):
        sub = P[mask]
        return np.nanmean(sub, axis=0) if len(sub) else np.full(HORIZON, np.nan)

    report = {"n_trades": int(N), "horizon_bars": HORIZON}

    # 1. EDGE LIFESPAN -----------------------------------------------------
    overall = curve(np.ones(N, bool))
    mfe = np.nanmax(np.where(np.isnan(P), -np.inf, P), axis=1)
    mfe[~np.isfinite(mfe)] = np.nan
    report["edge_lifespan"] = {
        "mean_R_by_bar": [round(float(x), 4) for x in overall],
        "peak_bar": int(np.nanargmax(overall)) + 1,
        "peak_R": round(float(np.nanmax(overall)), 4),
        "R_at_bar18": round(float(overall[-1]), 4),
        "frac_of_peak_kept_at_18": round(float(overall[-1] /
                                         max(np.nanmax(overall), 1e-9)), 3),
        "mean_MFE_R": round(float(np.nanmean(mfe)), 4),
    }

    # 2. ASYMMETRY (long vs short) ----------------------------------------
    report["asymmetry"] = {}
    for sd in ("LONG", "SHORT"):
        m = side == sd
        c = curve(m)
        report["asymmetry"][sd] = {
            "n": int(m.sum()),
            "peak_bar": int(np.nanargmax(c)) + 1,
            "peak_R": round(float(np.nanmax(c)), 4),
            "mean_final_R": round(float(np.nanmean(finalR[m])), 4),
            "win_rate": round(float(np.nanmean(finalR[m] > 0)), 4),
        }

    # 3. VOL REGIME --------------------------------------------------------
    report["vol_regime"] = {}
    for lbl, lo, hi in [("low", 0.0, 0.33), ("mid", 0.33, 0.66),
                        ("high", 0.66, 1.01)]:
        m = (apct >= lo) & (apct < hi)
        if m.sum() == 0:
            continue
        c = curve(m)
        report["vol_regime"][lbl] = {
            "n": int(m.sum()),
            "peak_R": round(float(np.nanmax(c)), 4),
            "mean_final_R": round(float(np.nanmean(finalR[m])), 4),
            "win_rate": round(float(np.nanmean(finalR[m] > 0)), 4),
        }

    # 4. MECHANISM (stat-arb vs vix) --------------------------------------
    report["mechanism"] = {}
    for fam in sorted(set(family)):
        m = family == fam
        c = curve(m)
        fr = finalR[m]
        report["mechanism"][fam] = {
            "n": int(m.sum()),
            "peak_bar": int(np.nanargmax(c)) + 1,
            "peak_R": round(float(np.nanmax(c)), 4),
            "mean_final_R": round(float(np.nanmean(fr)), 4),
            "final_R_std": round(float(np.nanstd(fr)), 4),
            "win_rate": round(float(np.nanmean(fr > 0)), 4),
        }

    # 5. REVERSION CLOCK — does "didn't work fast" mean "won't work"? ------
    rk = P[:, HALF_LIFE_BAR - 1]            # R-excursion at the half-life bar
    green = rk > 0
    have = np.isfinite(rk) & np.isfinite(finalR)
    g, rdm = green & have, (~green) & have
    report["reversion_clock"] = {
        "half_life_bar": HALF_LIFE_BAR,
        "frac_green_at_half_life": round(float(green[have].mean()), 4),
        "P_final_win_given_green_at_HL": round(float((finalR[g] > 0).mean()), 4),
        "P_final_win_given_red_at_HL": round(float((finalR[rdm] > 0).mean()), 4),
        "mean_final_R_given_green_at_HL": round(float(np.nanmean(finalR[g])), 4),
        "mean_final_R_given_red_at_HL": round(float(np.nanmean(finalR[rdm])), 4),
    }

    # 6. EXIT-AT-BAR-K — the data-optimal hold ----------------------------
    exit_k = [round(float(np.nanmean(P[:, k])), 4) for k in range(HORIZON)]
    report["exit_at_bar_k"] = {
        "mean_R_if_exit_at_bar": exit_k,
        "best_bar": int(np.nanargmax(exit_k)) + 1,
        "best_R": round(float(np.nanmax(exit_k)), 4),
    }

    # 7. TIME OF DAY -------------------------------------------------------
    tod = {}
    for h in sorted(set(int(x) for x in hour if x >= 0)):
        m = hour == h
        tod[str(h)] = {"n": int(m.sum()),
                       "mean_final_R": round(float(np.nanmean(finalR[m])), 4),
                       "win_rate": round(float(np.nanmean(finalR[m] > 0)), 4)}
    report["time_of_day_ny"] = tod

    report["per_strategy"] = profiles
    OUT_PATH.write_text(json.dumps(report, indent=2))

    # ---- console summary -------------------------------------------------
    el = report["edge_lifespan"]
    print("\n" + "=" * 74)
    print("PRICE-FLOW STUDY — the 97-strategy deployment, dissected")
    print("=" * 74)
    print(f"\n{N:,} trades across {len(specs)} strategies.\n")
    print("1. EDGE LIFESPAN (mean R-excursion by 5-min bar held):")
    bars = el["mean_R_by_bar"]
    for k in range(0, HORIZON, 2):
        bar_v = bars[k]
        s = "#" * max(0, int(bar_v * 120))
        print(f"   bar {k+1:>2} ({(k+1)*5:>3}min)  {bar_v:+.4f} R  {s}")
    print(f"   -> edge PEAKS at bar {el['peak_bar']} ({el['peak_bar']*5}min) "
          f"= {el['peak_R']:+.4f} R")
    print(f"   -> by bar 18 only {el['frac_of_peak_kept_at_18']*100:.0f}% "
          f"of the peak edge remains")
    print(f"\n2. ASYMMETRY  long vs short:")
    for sd, d in report["asymmetry"].items():
        print(f"   {sd:<6} n={d['n']:>5}  peak {d['peak_R']:+.3f}R @bar{d['peak_bar']}"
              f"  final {d['mean_final_R']:+.3f}R  WR {d['win_rate']*100:.1f}%")
    print(f"\n3. VOL REGIME at entry:")
    for lbl, d in report["vol_regime"].items():
        print(f"   {lbl:<5} n={d['n']:>5}  peak {d['peak_R']:+.3f}R  "
              f"final {d['mean_final_R']:+.3f}R  WR {d['win_rate']*100:.1f}%")
    print(f"\n4. MECHANISM:")
    for fam, d in report["mechanism"].items():
        print(f"   {fam:<9} n={d['n']:>5}  final {d['mean_final_R']:+.3f}R  "
              f"std {d['final_R_std']:.3f}  WR {d['win_rate']*100:.1f}%")
    rc = report["reversion_clock"]
    print(f"\n5. REVERSION CLOCK (bar {rc['half_life_bar']} = "
          f"{rc['half_life_bar']*5}min, the measured half-life):")
    print(f"   green at half-life -> P(final win) = "
          f"{rc['P_final_win_given_green_at_HL']*100:.1f}%  "
          f"(mean {rc['mean_final_R_given_green_at_HL']:+.3f}R)")
    print(f"   red   at half-life -> P(final win) = "
          f"{rc['P_final_win_given_red_at_HL']*100:.1f}%  "
          f"(mean {rc['mean_final_R_given_red_at_HL']:+.3f}R)")
    ek = report["exit_at_bar_k"]
    print(f"\n6. DATA-OPTIMAL HOLD: exit at bar {ek['best_bar']} "
          f"({ek['best_bar']*5}min) -> {ek['best_R']:+.4f} R/trade")
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
