"""
Strategy profiles — what each deployed strategy IS, in price-flow terms.

Reads the per-strategy profiles produced by research/price_flow_study.py
(data/price_flow_study.json) and turns them into a plain-English "thesis"
the bot logs the moment it enters, and the dashboard shows.

This is understanding, NOT a filter. It changes nothing about which trades
are taken or how they are held. It just means that when the bot enters a
strategy it (and you) know what the trade is and what to expect from it:
how long the edge takes to develop, that an early drawdown is normal, and
when the move typically completes.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STUDY_PATH = PROJECT_ROOT / "data" / "price_flow_study.json"

_FAMILY_WORD = {
    "stat_arb": "an NQ-vs-ES divergence",
    "vix": "an NQ-vs-VIX divergence",
    "rty": "an NQ-vs-RTY divergence",
}


@lru_cache(maxsize=1)
def _study() -> dict:
    try:
        return json.loads(STUDY_PATH.read_text())
    except Exception:
        return {}


@lru_cache(maxsize=1)
def _by_name() -> dict:
    return {p["name"]: p for p in _study().get("per_strategy", [])}


def _vol_word(pct) -> str:
    if pct is None:
        return "any"
    if pct < 0.40:
        return "quiet"
    if pct < 0.66:
        return "normal"
    return "elevated"


def _session_word(hour) -> str:
    if hour is None or hour < 0:
        return "any session"
    if 9 <= hour < 11:
        return "the morning"
    if 11 <= hour < 14:
        return "midday"
    if 14 <= hour < 16:
        return "the afternoon"
    if 16 <= hour < 20:
        return "the evening"
    if hour >= 20 or hour < 4:
        return "the overnight session"
    return "the pre-market"


def profile_for(name: str) -> dict | None:
    """Raw per-strategy profile from the price-flow study (or None)."""
    return _by_name().get(name)


def thesis_for(name: str, side: str | None = None) -> dict:
    """Plain-English 'what this trade is and what to expect'.

    Falls back to a side-only generic thesis if the strategy was not in the
    price-flow study (e.g. a freshly-mined strategy with no profile yet).
    """
    p = _by_name().get(name)
    if p is None:
        return _generic(side)

    side = p["side"]
    peak_min = int(p["peak_bar"]) * 5
    vol = _vol_word(p.get("median_entry_vol_pctile"))
    sess = _session_word(p.get("modal_entry_hour_ny"))
    fam = _FAMILY_WORD.get(p.get("family"), "a cross-asset divergence")
    move = "buys the dip" if side == "LONG" else "fades the rip"

    if side == "SHORT":
        side_time = ("This is a SHORT — its move tends to complete near "
                     "55 minutes, faster than the bot's longs.")
    else:
        side_time = ("This is a LONG — its move builds slowly and can take "
                     "the full 90-minute hold to fully pay off.")

    thesis = (
        f"This strategy {move} on {fam} during {sess}, in {vol} volatility. "
        f"Across {p['n_trades']} historical trades its edge develops over "
        f"about {peak_min} minutes. An early drawdown is normal — being "
        f"underwater in the first ~15 minutes is the usual path of a "
        f"mean-reversion winner; the trade's direction is typically settled "
        f"by then. {side_time}"
    )
    return {
        "known": True,
        "kind": f"{side} · {vol}-vol · "
                f"{sess.replace('the ', '')} reversion",
        "thesis": thesis,
        "goal": ("Hold the reversion to target; exit on target, stop, or the "
                 "time cap. Do not be alarmed by an early drawdown."),
        "expectations": [
            f"Edge develops over ~{peak_min} min (peaks at bar {p['peak_bar']}).",
            "Underwater early is normal — direction settles by ~15 min.",
            side_time,
        ],
        "edge_peak_min": peak_min,
        "n_trades_studied": p["n_trades"],
        "modal_hour_et": p.get("modal_entry_hour_ny"),
        "vol_regime": vol,
        "side": side,
    }


def _generic(side: str | None) -> dict:
    side = side or "—"
    move = ("buys a dislocation" if side == "LONG"
            else "fades a dislocation" if side == "SHORT"
            else "trades a dislocation")
    return {
        "known": False,
        "kind": f"{side} mean-reversion (not yet profiled)",
        "thesis": (f"This strategy {move} and expects mean-reversion. It was "
                   f"not in the price-flow study, so no per-strategy timing "
                   f"profile is available — but the deployment-wide pattern "
                   f"holds: an early drawdown is normal and the edge builds "
                   f"over the full hold."),
        "goal": ("Hold the reversion to target; exit on target, stop, or the "
                 "time cap."),
        "expectations": [
            "Underwater early is normal — direction settles by ~15 min.",
            "Edge magnitude builds over the full 75-90 min hold.",
        ],
        "edge_peak_min": None,
        "n_trades_studied": 0,
        "side": side,
    }
