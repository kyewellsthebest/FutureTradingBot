"""
Plain-English descriptions for every signal the bot watches.

Two categories:

  1. Hand-coded named signals (PDH_TOUCH, EQ50_LONG, etc.) — exact entry
     conditions are in research/signal_generator.py. Descriptions here
     mirror that logic in human terms.

  2. Mined V3 / WR / HF families — names encode their parameters
     (V3_LONG_S15T30_69 = LONG, stop 15pt, target 30pt, ID 69). The
     specific feature combination that triggers entry was discovered by
     the gradient-boosted miner (research/v3_miner.py) and lives inside
     a serialised model. We can't reverse-engineer the exact rule from
     the name alone, so for these we describe the family + parameters
     and explain HOW the miner picked them.

Usage:
    from research.strategy_descriptions import describe
    info = describe("V3_LONG_S15T30_69")  # → dict with description, ...
"""
from __future__ import annotations

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Hand-coded named signals (5-minute family)
# ---------------------------------------------------------------------------
NAMED = {
    "PDH_TOUCH": dict(
        title="Previous Day High touch — fade",
        family="5-min",
        side="SHORT",
        idea="Fade rejections at yesterday's high. Liquidity sits there from "
             "stop-runs and breakout traders; a tag without commitment usually "
             "means sellers are stepping in.",
        triggers=[
            "Bar's high reaches within 1pt of prev-day high (PDH)",
            "Bar closes BACK BELOW the PDH (no break-and-hold)",
            "Bar is bearish (close < open)",
            "Volume ≥ 1.2× the 20-bar volume average (real participation, not a wick)",
        ],
        notes="Works best in choppy / mean-reverting regimes. Fails on strong "
              "trend days that gap higher and don't look back.",
    ),
    "PDL_TOUCH": dict(
        title="Previous Day Low touch — buy the dip",
        family="5-min", side="LONG",
        idea="Mirror of PDH_TOUCH on the downside. Buyers defend yesterday's "
             "low; a tag that gets reclaimed signals exhaustion of the down move.",
        triggers=[
            "Bar's low reaches within 1pt of prev-day low (PDL)",
            "Bar closes BACK ABOVE the PDL (no break-and-hold)",
            "Bar is bullish (close > open)",
            "Volume ≥ 1.2× the 20-bar volume average",
        ],
        notes="Best on bounces from oversold opens. Skip on news-driven sell-offs.",
    ),
    "EQ50_LONG": dict(
        title="EQ50 mean reversion — long",
        family="5-min", side="LONG",
        idea="Price stretched ≥40pt below the 50-bar equilibrium midpoint usually "
             "snaps back to the mean once buying pressure resumes.",
        triggers=[
            "Close is ≥40pt below the 50-bar EQ midpoint (high-low / 2 over 50 bars)",
            "Bar is bullish (the snapback has started)",
        ],
        notes="Mean-reversion play. Avoid in strong-trend regimes — it fades into "
              "a trend and gets crushed.",
    ),
    "EQ50_SHORT": dict(
        title="EQ50 mean reversion — short",
        family="5-min", side="SHORT",
        idea="Mirror of EQ50_LONG. Price ≥40pt ABOVE the 50-bar midpoint usually "
             "reverts.",
        triggers=[
            "Close is ≥40pt above the 50-bar EQ midpoint",
            "Bar is bearish",
        ],
        notes="Same caveat — avoid in strong trends.",
    ),
    "GAP_FILL_LONG": dict(
        title="Cash-open gap-down fill — long",
        family="5-min", side="LONG",
        idea="A big gap down at the cash open (-20pt or more) often gets filled "
             "back to the prior close as panic sellers exhaust.",
        triggers=[
            "It's the 9:30 ET cash-open bar",
            "Open is ≥20pt below prior cash close",
            "First 5-min bar is bullish (gap is being faded)",
        ],
        notes="Target hint: the prior cash close (the gap-fill level).",
    ),
    "GAP_FILL_SHORT": dict(
        title="Cash-open gap-up fill — short",
        family="5-min", side="SHORT",
        idea="A big gap up at the cash open (+50pt or more) often gives back "
             "into the prior close as breakout buyers fail.",
        triggers=[
            "It's the 9:30 ET cash-open bar",
            "Open is ≥50pt above prior cash close",
            "First 5-min bar is bearish",
        ],
        notes="Target hint: the prior cash close.",
    ),
    "ZSCORE_LONG": dict(
        title="Z-score reversal — long",
        family="5-min", side="LONG",
        idea="Price was ≥1.5σ below its 20-bar mean and just crossed back up. "
             "Statistically extreme moves tend to revert.",
        triggers=[
            "20-bar z-score of close was below -1.5 on the prior bar",
            "Z-score crossed back above -1.5 on the current bar",
        ],
    ),
    "ZSCORE_SHORT": dict(
        title="Z-score reversal — short",
        family="5-min", side="SHORT",
        idea="Mirror — price was ≥1.5σ above the 20-bar mean and is rolling over.",
        triggers=[
            "20-bar z-score was above +1.5 on the prior bar",
            "Z-score crossed back below +1.5 on the current bar",
        ],
    ),
    "VOL_COMP_LONG": dict(
        title="Volatility compression breakout — long",
        family="5-min", side="LONG",
        idea="Two quiet bars (volume < 70% of average) followed by an explosive "
             "bullish bar (≥2× average volume) signals a breakout from accumulation.",
        triggers=[
            "Prior 2 bars had volume_ratio < 0.7 (the squeeze)",
            "Current bar has volume_ratio ≥ 2.0 (the release)",
            "Current bar is bullish",
        ],
    ),
    "VOL_COMP_SHORT": dict(
        title="Volatility compression breakout — short",
        family="5-min", side="SHORT",
        idea="Mirror — quiet bars followed by an explosive bearish bar.",
        triggers=[
            "Prior 2 bars had volume_ratio < 0.7",
            "Current bar has volume_ratio ≥ 2.0",
            "Current bar is bearish",
        ],
    ),
    "VWAP_RECLAIM_LONG": dict(
        title="VWAP reclaim — long",
        family="5-min", side="LONG",
        idea="Price drops below VWAP, then reclaims it on a bullish bar — "
             "trend-followers re-enter as the session bias resumes.",
    ),
    "VWAP_RECLAIM_SHORT": dict(
        title="VWAP rejection — short",
        family="5-min", side="SHORT",
        idea="Price rallies into VWAP and rejects on a bearish bar.",
    ),
}


# ---------------------------------------------------------------------------
# Family-level explanations for mined signals
# ---------------------------------------------------------------------------
V3_FAMILY = dict(
    title="V3 mined gold-standard pattern",
    description=(
        "Discovered by the gradient-boosted V3 miner over 8 years of NQ data "
        "with rigorous walk-forward validation (train 2018-2023, test 2024-2026). "
        "Each pattern is a non-obvious combination of order-flow, "
        "volatility-regime, and time-of-day features that historically led "
        "to the specific stop/target outcome encoded in its name. "
        "Survives a Combinatorial Purged Cross-Validation (CPCV) audit — "
        "out-of-sample performance is statistically distinguishable from luck "
        "(deflated Sharpe > 0)."
    ),
    notes=(
        "The exact feature recipe lives inside a serialised gradient-boost "
        "model and is not human-readable. The miner found ≈8,000 candidate "
        "patterns and only 200 survived CPCV. The 40 currently live (Tier A) "
        "additionally pass a 60% out-of-sample win-rate floor."
    ),
)
WR_FAMILY = dict(
    title="WR (Whitley Resource) live-validated pattern",
    description=(
        "Patterns the bot mined and then live-paper-traded for ≥30 days "
        "with positive expectancy maintained. WR signals are validated under "
        "real-market friction (slippage, exit-bar latency) before getting "
        "Tier-A status."
    ),
)
HF_FAMILY = dict(
    title="HF high-frequency pattern",
    description=(
        "Sub-bar / micro-pattern strategies. Reserved for future deployment — "
        "not part of the Lucid live stack (Lucid prohibits HFT-style strategies)."
    ),
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def describe(name: str) -> dict:
    """Return a dict describing one strategy. Always returns something useful."""
    if name in NAMED:
        d = dict(NAMED[name])
        d["name"] = name
        return d

    # Mined-family fallback: parse the name
    family = "?"
    if name.startswith("V3_"):    family_info = V3_FAMILY
    elif name.startswith("WR_"):  family_info = WR_FAMILY
    elif name.startswith("HF_"):  family_info = HF_FAMILY
    else:
        family_info = dict(title=f"{name} — unclassified", description="No description available.")

    side = None
    stop_pts: Optional[int] = None
    target_pts: Optional[int] = None
    pid: Optional[int] = None
    # e.g. V3_LONG_S15T30_69
    m = re.match(r"^(V3|WR|HF)_(LONG|SHORT)_S(\d+)T(\d+)_(\d+)$", name)
    if m:
        _, side, stop, target, pid_s = m.groups()
        stop_pts = int(stop); target_pts = int(target); pid = int(pid_s)

    rr = (target_pts / stop_pts) if (stop_pts and target_pts) else None
    fam_short = "v3" if name.startswith("V3_") else ("WR" if name.startswith("WR_") else "HF")

    out = dict(
        name=name,
        title=family_info["title"],
        family=fam_short,
        side=side or "—",
        description=family_info["description"],
        notes=family_info.get("notes", ""),
    )
    if stop_pts is not None:
        out["triggers"] = [
            f"Mined feature combination evaluated each new bar by the GBM model",
            f"Direction: {side}",
            f"Stop loss: {stop_pts} points  ({stop_pts*2:.0f}$ per MNQ)",
            f"Take profit: {target_pts} points  ({target_pts*2:.0f}$ per MNQ)",
            f"Reward:risk ≈ {rr:.2f}",
            f"Pattern ID #{pid} (the {pid}-th surviving CPCV-validated pattern in this family)",
        ]
    return out
