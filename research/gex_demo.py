"""
Dealer Gamma Exposure (GEX) calculator — demo on Cboe sample data.

GEX measures the aggregate gamma position of options dealers (the people who
sell most retail options). When dealers are SHORT gamma, hedging amplifies
moves (vol expands, breakouts trend). When LONG gamma, hedging suppresses
moves (vol compresses, market pins).

The math:
    GEX_per_contract = gamma * open_interest * 100 * spot^2 * dealer_sign
        - For CALL options:  dealers usually SHORT (sold to retail) → -1
        - For PUT options:   dealers usually LONG (retail sells puts to monetize)
                             but in modern markets retail buys puts too → -1
        - SqueezeMetrics convention: -calls, +puts (call-put gamma)
        - We use the conservative version: -gamma * OI for both

Total GEX in $ per 1% S&P move:  Σ(gamma_per_strike * OI * 100 * spot^2 * 0.01)

Then per-strike "gamma walls" — strikes where gamma exposure is concentrated.
Above gamma flip = long gamma regime (low vol, mean-revert).
Below gamma flip = short gamma regime (high vol, trends).
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np


def load_options_eod(path: Path) -> pd.DataFrame:
    """Load Cboe Underlying Options EOD Calcs CSV."""
    df = pd.read_csv(path)
    # Restrict to SPX only (most liquid index, best for dealer-position inference)
    df = df[df["underlying_symbol"] == "^SPX"].copy()
    df["expiration"] = pd.to_datetime(df["expiration"])
    df["quote_date"] = pd.to_datetime(df["quote_date"])
    df["dte"] = (df["expiration"] - df["quote_date"]).dt.days
    return df


def compute_gex(df: pd.DataFrame, spot: float, dte_max: int = 60) -> dict:
    """Compute aggregate dealer gamma exposure.

    Returns a dict with:
      - total_gex_usd_per_1pct: aggregate dealer gamma in $ per 1% S&P move
      - call_gex / put_gex: split by option type
      - gex_per_strike: dict of strike → cumulative gamma exposure
      - gamma_flip: estimated strike where regime changes from long→short
      - call_wall: strike with most call gamma (resistance)
      - put_wall: strike with most put gamma (support)
    """
    # Use a reasonable DTE cap — focus on near-term where dealer hedging matters most
    near = df[df["dte"] <= dte_max].copy()

    # Use a single bid/ask snapshot for OI + gamma (the 1545 EOD reading)
    near["oi"] = near["open_interest"].fillna(0)
    near["gamma"] = near["gamma_1545"].fillna(0)

    # Notional gamma per contract: gamma * OI * 100 * spot^2
    # For dealers (assumed short calls, long puts in classic SqueezeMetrics convention):
    near["dollar_gamma"] = near["gamma"] * near["oi"] * 100 * spot * spot
    near["signed_gamma"] = np.where(
        near["option_type"] == "C",
        -near["dollar_gamma"],   # dealers short calls
        +near["dollar_gamma"],   # dealers long puts
    )

    total_call_gex = near[near["option_type"] == "C"]["signed_gamma"].sum() * 0.01
    total_put_gex = near[near["option_type"] == "P"]["signed_gamma"].sum() * 0.01
    total_gex = total_call_gex + total_put_gex

    # Per-strike aggregation
    per_strike = near.groupby("strike")["signed_gamma"].sum() * 0.01
    per_strike = per_strike.sort_index()

    # Cumulative gamma from low strike upward — gamma flip is where it crosses 0
    cum = per_strike.cumsum()
    flip_idx = (cum.abs()).idxmin()

    # Walls = single largest concentration of negative call gamma vs positive put gamma
    call_strikes = near[near["option_type"] == "C"].groupby("strike")["dollar_gamma"].sum()
    put_strikes = near[near["option_type"] == "P"].groupby("strike")["dollar_gamma"].sum()
    call_wall = call_strikes.idxmax() if len(call_strikes) > 0 else None
    put_wall = put_strikes.idxmax() if len(put_strikes) > 0 else None

    return {
        "spot": spot,
        "dte_max": dte_max,
        "n_options": len(near),
        "total_gex_usd_per_1pct": float(total_gex),
        "total_call_gex": float(total_call_gex),
        "total_put_gex": float(total_put_gex),
        "gamma_flip_strike": float(flip_idx),
        "call_wall_strike": float(call_wall) if call_wall else None,
        "put_wall_strike": float(put_wall) if put_wall else None,
        "regime": "LONG GAMMA (vol-suppressed)" if total_gex > 0 else "SHORT GAMMA (vol-expanding)",
    }


def main():
    sample = Path("/tmp/cboe_inspect/UnderlyingOptionsEODCalcs_2023-08-25_cgi_or_historical.csv")
    print("=" * 72)
    print("DEALER GAMMA EXPOSURE — demo on Cboe sample (Aug 25, 2023)")
    print("=" * 72)

    df = load_options_eod(sample)
    print(f"\n  SPX options on file: {len(df):,}")
    print(f"  Expiration range:    {df['expiration'].min().date()}  →  {df['expiration'].max().date()}")

    # Spot price from the data itself
    spot = df["active_underlying_price_1545"].dropna().iloc[0]
    print(f"  SPX spot:            {spot:.2f}")

    # Run GEX for several DTE windows
    for dte_max in [7, 30, 60, 365]:
        gex = compute_gex(df, spot, dte_max=dte_max)
        print(f"\n  --- DTE ≤ {dte_max} ({gex['n_options']:,} contracts) ---")
        print(f"    Total dealer GEX:  ${gex['total_gex_usd_per_1pct']/1e9:>+8.2f} B per 1% move")
        print(f"    Call-side GEX:     ${gex['total_call_gex']/1e9:>+8.2f} B")
        print(f"    Put-side GEX:      ${gex['total_put_gex']/1e9:>+8.2f} B")
        print(f"    Regime:            {gex['regime']}")
        print(f"    Gamma flip strike: {gex['gamma_flip_strike']:.0f}  (price = {spot:.0f}, "
              f"distance = {gex['gamma_flip_strike']-spot:+.0f} pts)")
        if gex["call_wall_strike"]:
            print(f"    Call wall:         {gex['call_wall_strike']:.0f}  "
                  f"({gex['call_wall_strike']-spot:+.0f} from spot — resistance)")
        if gex["put_wall_strike"]:
            print(f"    Put wall:          {gex['put_wall_strike']:.0f}  "
                  f"({gex['put_wall_strike']-spot:+.0f} from spot — support)")

    # Historical context: what actually happened around Aug 25, 2023?
    print(f"\n  --- Aug 25, 2023 historical context ---")
    print(f"    SPX closed:           ~4,405 (your sample shows {spot:.0f})")
    print(f"    Aug 14-18, 2023:      SPX dropped from 4,500 to 4,330 (-3.8%)")
    print(f"    Aug 25, 2023:         SPX bounced to ~4,405")
    print(f"    By Sep 1:             SPX hit 4,510 (rallied 2.4% from sample date)")
    print(f"    If GEX was POSITIVE on Aug 25 → vol-suppressing → SPX should pin/grind")
    print(f"    If GEX was NEGATIVE on Aug 25 → vol-expanding → expect breakout (it did rally)")


if __name__ == "__main__":
    main()
