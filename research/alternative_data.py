"""
Alternative-data aggregator — combines all free non-price signals into
a single `macro_score` in [-1, +1] that biases the bot's position sizing.

Composite signals (each weighted by source reliability):
  - COT commercials (weight 0.30)    — commercial hedgers rarely wrong at extremes
  - GEX dealer positioning (0.25)    — options dealers forced to hedge
  - EDGAR insider activity  (0.20)   — smart-money corporate insiders
  - Congressional trades    (0.15)   — politicians with informational edge
  - WSB retail sentiment    (0.10)   — contrarian retail indicator

GRACEFUL DEGRADATION:
If any individual source is unavailable, the aggregator re-weights the
remaining signals so the final macro_score still lands in [-1, +1].

POSITION-SIZE IMPACT:
  macro_score > +0.5 aligned with signal : size × 1.0 (full)
  macro_score > +0.5 against signal       : size × 0.5 (halve)
  macro_score in [-0.5, +0.5]             : size × 0.9 (slight reduction)
  macro_score < -0.5 aligned with signal  : size × 1.0
  macro_score < -0.5 against signal       : size × 0.5
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from research.congressional_trades import fetch_congress_snapshot
from research.cot_parser import fetch_cot_snapshot
from research.edgar_insider import fetch_insider_snapshot
from research.gex_calculator import compute_gex, load_cached_snapshot as load_gex_cache
from research.wsb_sentiment import fetch_wsb_snapshot

MacroBias = Literal["STRONG_BULLISH", "BULLISH", "NEUTRAL", "BEARISH", "STRONG_BEARISH"]

COMPONENT_WEIGHTS = {
    "cot":      0.30,
    "gex":      0.25,
    "insider":  0.20,
    "congress": 0.15,
    "wsb":      0.10,
}


@dataclass
class MacroSnapshot:
    macro_score: float           # final [-1, +1]
    bias: MacroBias
    components: dict[str, float]  # per-source score (or None)
    details: dict[str, dict]      # raw snapshot summaries
    effective_weights: dict[str, float]  # after re-normalisation
    components_available: int     # how many of the 5 produced data


def _gex_score(snap) -> float | None:
    """Map GEX regime + intensity into [-1, +1]."""
    if snap is None:
        return None
    # POSITIVE regime in normal range = mild bullish (buy-the-dip dealer support)
    # NEGATIVE regime = mild bearish (volatility expansion / downside risk)
    # Extreme percentiles are contrarian
    base = 0.0
    if snap.regime == "POSITIVE":
        base = 0.4
    elif snap.regime == "NEGATIVE":
        base = -0.4
    pct = snap.intensity_percentile
    if pct >= 90:
        base -= 0.5   # extreme positive = reversal risk down
    elif pct <= 10:
        base += 0.5   # extreme negative = bounce risk up
    return max(-1.0, min(1.0, base))


def compute_macro(*, force_refresh: bool = False) -> MacroSnapshot:
    """Fetch all sources and produce a composite macro_score."""
    details: dict[str, dict] = {}
    component_scores: dict[str, float | None] = {}

    # 1. COT
    try:
        cot = fetch_cot_snapshot(force_refresh=force_refresh)
    except Exception:
        cot = None
    if cot:
        component_scores["cot"] = cot.combined_score
        details["cot"] = {
            "report_date": cot.report_date,
            "commercial_bias": cot.commercial_bias,
            "spec_bias": cot.spec_bias,
            "combined_score": cot.combined_score,
        }
    else:
        component_scores["cot"] = None

    # 2. GEX — use cache if fresh, else recompute
    try:
        gex = load_gex_cache()
        if gex is None:
            gex = compute_gex()
    except Exception:
        gex = None
    gex_score = _gex_score(gex)
    component_scores["gex"] = gex_score
    if gex is not None:
        details["gex"] = {
            "regime": gex.regime,
            "total_gex_billion": gex.total_gex / 1e9,
            "intensity_pct": gex.intensity_percentile,
            "zero_gamma_nq": gex.zero_gamma_nq,
            "magnets_nq": gex.magnets_nq,
        }

    # 3. Insider
    try:
        ins = fetch_insider_snapshot(force_refresh=force_refresh)
    except Exception:
        ins = None
    if ins:
        component_scores["insider"] = ins.score
        details["insider"] = {
            "bias": ins.bias,
            "net_buy_dollars": ins.net_buy_dollars,
            "n_filings_30d": ins.n_filings_30d,
            "score": ins.score,
        }
    else:
        component_scores["insider"] = None

    # 4. Congress
    try:
        cg = fetch_congress_snapshot(force_refresh=force_refresh)
    except Exception:
        cg = None
    if cg:
        component_scores["congress"] = cg.score
        details["congress"] = {
            "bias": cg.bias,
            "total_net": cg.total_net,
            "n_trades_60d": cg.n_trades_60d,
            "score": cg.score,
        }
    else:
        component_scores["congress"] = None

    # 5. WSB
    try:
        wsb = fetch_wsb_snapshot(force_refresh=force_refresh)
    except Exception:
        wsb = None
    if wsb:
        component_scores["wsb"] = wsb.contrarian_score
        details["wsb"] = {
            "bias": wsb.bias,
            "nq_mentions": wsb.nq_mentions,
            "bull_score": wsb.bull_score,
            "bear_score": wsb.bear_score,
            "contrarian_score": wsb.contrarian_score,
        }
    else:
        component_scores["wsb"] = None

    # Re-normalise weights over available sources
    available = {k: s for k, s in component_scores.items() if s is not None}
    total_w = sum(COMPONENT_WEIGHTS[k] for k in available)
    if total_w == 0:
        final = 0.0
        effective: dict[str, float] = {}
    else:
        effective = {k: COMPONENT_WEIGHTS[k] / total_w for k in available}
        final = sum(available[k] * effective[k] for k in available)

    final = max(-1.0, min(1.0, final))

    bias: MacroBias
    if final >= 0.6:
        bias = "STRONG_BULLISH"
    elif final >= 0.25:
        bias = "BULLISH"
    elif final <= -0.6:
        bias = "STRONG_BEARISH"
    elif final <= -0.25:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    return MacroSnapshot(
        macro_score=float(final),
        bias=bias,
        components={k: (v if v is not None else None) for k, v in component_scores.items()},
        details=details,
        effective_weights=effective,
        components_available=len(available),
    )


def macro_filter(snap: MacroSnapshot | None, side: str) -> tuple[bool, str, float]:
    """
    (pass, reason, size_multiplier) applied as an ADDITIONAL multiplier
    on top of regime/VPIN/adverse-selection multipliers.

    Never blocks outright — only adjusts size.
    """
    if snap is None:
        return True, "macro=unavailable", 1.0
    score = snap.macro_score
    aligned = (score > 0 and side == "LONG") or (score < 0 and side == "SHORT")

    if abs(score) >= 0.5:
        mult = 1.0 if aligned else 0.5
        return (True,
                f"macro={snap.bias} {score:+.2f} aligned={aligned} size×{mult}",
                mult)
    if abs(score) >= 0.25:
        mult = 0.95 if aligned else 0.80
        return (True,
                f"macro={snap.bias} {score:+.2f} aligned={aligned} size×{mult}",
                mult)
    # Near-neutral — small penalty for everyone (reduces random-trade size)
    return True, f"macro={snap.bias} {score:+.2f}", 0.9


def _main() -> int:
    print("Computing macro score from all alternative data sources...")
    print("(May take 30-60s: EDGAR + CFTC + Reddit + options chain)")
    snap = compute_macro()
    print(f"\nMacro score: {snap.macro_score:+.3f}   bias={snap.bias}")
    print(f"Components available: {snap.components_available}/5")
    print(f"Effective weights: {snap.effective_weights}")
    print("\nComponent scores:")
    for k, v in snap.components.items():
        if v is None:
            print(f"  {k:10s}  UNAVAILABLE")
        else:
            print(f"  {k:10s}  {v:+.3f}")
    print("\nFilter test:")
    for side in ("LONG", "SHORT"):
        ok, reason, mult = macro_filter(snap, side)
        print(f"  {side}: mult={mult}  {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
