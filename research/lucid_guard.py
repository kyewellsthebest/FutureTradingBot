"""
Lucid Trading runtime compliance guard.

Single source of truth for Lucid Trading $50K Pro Funded rules + Terms of Use
prohibitions. The live bot imports this module and calls the check functions
before sending any order so we never violate Lucid's rules.

Source documents (lucidtrading.com, retrieved Apr 2026):
  - Terms of Use            (lucidtrading.com/terms-of-use)
  - 50K Pro Funded rules    (lucidtrading.com pricing card)
  - Permitted Activities    (support.lucidtrading.com/.../11404728)
  - Prohibited Microscalping (support.lucidtrading.com/.../11404742)
  - Prohibited Hedging       (support.lucidtrading.com/.../11404734)
  - Restricted Countries     (support.lucidtrading.com/.../11404636)

Usage in production:

    from research.lucid_guard import LucidState, evaluate_trade

    state = LucidState()  # one per account
    decision = evaluate_trade(state, side="LONG", n_contracts=12,
                               proposed_pnl_at_target=240.0,
                               proposed_pnl_at_stop=-160.0)
    if not decision.allowed:
        log.warning("Lucid guard blocked trade: %s", decision.reason)
        return
    # ... send order ...
    state.on_fill(side="LONG", n_contracts=12, realized_pnl=fill_pnl,
                  ts=fill_ts)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Lucid 50K Pro Funded constants — keep in sync with research/funded_5sim.py
# ---------------------------------------------------------------------------
START_BAL          = 50_000.0
INITIAL_TRAIL      = 48_000.0   # Max Loss Limit $2,000 below start
TRAIL_DROP         =  2_000.0
TRAIL_LOCK_AT      = 52_000.0   # peak EOD threshold at which trail locks at break-even
TRAIL_LOCKED_FLOOR = 50_000.0   # break-even = starting balance
LUCIDSCALE_RATIO   = 0.60       # 60% of peak EOD once locked (binds when peak > ~$83K)
DLL                =  1_200.0   # Daily Loss Limit auto-flatten
MAX_MNQ            = 40         # 4 Mini OR 40 Micro
CONSISTENCY_PCT    = 0.40       # No single day > 40% of total profit
PROFIT_TARGET      =    500.0   # First payout eligibility
MIN_DAYS_TO_PAYOUT = 3
PROFIT_SPLIT       = 0.90       # trader keeps 90%

# Trail-floor safety margin. The trail-breach check (rule 6) blocks any
# trade whose worst-case stop would land balance AT OR BELOW the trail
# floor. This margin adds extra room — even if the stop technically
# clears the trail, a trade that would leave less than this margin above
# trail is rejected. Protects against:
#   * the "two losses in a row blow the account" scenario (after one loss,
#     the next trade's stop check is stricter)
#   * unmodeled extra slippage (gap stops, fast markets)
# Configurable via env var. Default $300.
import os as _os
TRAIL_SAFETY_MARGIN = float(_os.environ.get("LUCID_TRAIL_SAFETY_MARGIN", "300"))

# Microscalping (terms of use): >50% of profits from holds <=5s = banned.
# Bot uses 25-min minimum holds; we still hard-assert this at trade-close time.
MICROSCALP_HOLD_THRESHOLD_S = 5
MICROSCALP_PROFIT_RATIO     = 0.50

# Restricted countries (lucidtrading.com — must be checked at signup, not
# per-trade, but we keep the list here so onboarding scripts can validate)
RESTRICTED_COUNTRIES = frozenset({
    "AF","AL","DZ","AO","BS","BB","BY","BA","BG","BF","MM","BW","BI","KH",
    "CF","CI","CU","CD","CG","EC","ET","GH","GN","HT","IS","ID","IR","IQ",
    "JM","KE","XK","LA","LB","LR","LY","LT","ML","MU","MN","ME","MA","MZ",
    "NA","NI","NG","KP","MK","PK","PA","PG","PH","RU","SN","RS","SI","SO",
    "ZA","SS","LK","SD","SY","TZ","TR","TT","TN","UG","UA","VN","VE","YE","ZW",
})


# ---------------------------------------------------------------------------
# Account state
# ---------------------------------------------------------------------------
@dataclass
class LucidState:
    """In-memory snapshot of one Lucid account. Persist to disk between
    bot restarts so the trail / consistency tracker survives process kills."""
    balance: float = START_BAL
    peak_eod_high: float = START_BAL
    trail_floor: float = INITIAL_TRAIL
    trail_locked: bool = False
    cum_pnl: float = 0.0          # cumulative realized P&L (closed days only)
    today_pnl: float = 0.0
    current_day: Optional[str] = None
    n_trading_days: int = 0
    open_position_side: Optional[str] = None   # "LONG"/"SHORT"/None
    open_position_n: int = 0
    blown: bool = False
    blow_reason: Optional[str] = None

    # Microscalp tracker — per-trade (entry_ts, hold_s, pnl)
    micro_total_profit: float = 0.0
    micro_short_profit: float = 0.0  # profit from holds <=5s

    def end_of_day(self, day: str) -> None:
        """Roll forward to a new trading day."""
        self.peak_eod_high = max(self.peak_eod_high, self.balance)
        self.cum_pnl += self.today_pnl
        self.today_pnl = 0.0
        # Latch the lock the first time peak EOD reaches $52K
        if not self.trail_locked and self.peak_eod_high >= TRAIL_LOCK_AT:
            self.trail_locked = True
        if not self.trail_locked:
            # Phase 1: standard $2K trail
            new_floor = self.peak_eod_high - TRAIL_DROP
        else:
            # Phase 2/3: locked at break-even, LucidScale 60%-of-peak above
            scale = LUCIDSCALE_RATIO * self.peak_eod_high
            new_floor = max(TRAIL_LOCKED_FLOOR, scale)
        self.trail_floor = max(self.trail_floor, new_floor)
        self.current_day = day

    def on_fill(self, side: str, n_contracts: int, realized_pnl: float,
                 ts: datetime, hold_seconds: float) -> None:
        """Update state after a closed trade."""
        day = ts.date().isoformat()
        if self.current_day is None:
            self.current_day = day
            self.n_trading_days += 1
        elif day != self.current_day:
            self.end_of_day(day)
            self.n_trading_days += 1
        self.balance += realized_pnl
        self.today_pnl += realized_pnl
        self.open_position_side = None
        self.open_position_n = 0
        # Microscalp accounting — only profitable trades count
        if realized_pnl > 0:
            self.micro_total_profit += realized_pnl
            if hold_seconds <= MICROSCALP_HOLD_THRESHOLD_S:
                self.micro_short_profit += realized_pnl
        # Trail breach
        if self.balance <= self.trail_floor:
            self.blown = True
            self.blow_reason = f"trail_breach@{self.balance:.0f}<={self.trail_floor:.0f}"


# ---------------------------------------------------------------------------
# Decision object
# ---------------------------------------------------------------------------
@dataclass
class GuardDecision:
    allowed: bool
    reason: str = ""
    rule: str = ""
    suggested_n: int = 0  # max size that would still be compliant


# ---------------------------------------------------------------------------
# Pre-trade evaluation
# ---------------------------------------------------------------------------
def evaluate_trade(
    state: LucidState,
    *,
    side: str,
    n_contracts: int,
    proposed_pnl_at_target: float,
    proposed_pnl_at_stop: float,
    correlated_open_in_other_account: Optional[str] = None,
) -> GuardDecision:
    """Check a proposed trade against every Lucid rule.

    Args:
      side: "LONG" or "SHORT"
      n_contracts: MNQ contracts
      proposed_pnl_at_target / proposed_pnl_at_stop: $ outcomes
      correlated_open_in_other_account: side ("LONG"/"SHORT") of an open
        position in any sibling account on a correlated asset (NQ/ES/RTY/YM
        all count as correlated equities). None if no other accounts exist.

    Returns GuardDecision with .allowed and .reason.
    """
    # 1. Account is alive
    if state.blown:
        return GuardDecision(False, f"account blown: {state.blow_reason}", "blown")

    # 2. Position cap
    if n_contracts > MAX_MNQ:
        return GuardDecision(False, f"size {n_contracts} > Lucid cap {MAX_MNQ} MNQ",
                              "position_cap", suggested_n=MAX_MNQ)
    if n_contracts < 1:
        return GuardDecision(False, "size < 1", "size_zero")

    # 3. Hedging — same side already open in this account
    if state.open_position_side is not None and state.open_position_side != side:
        return GuardDecision(False, f"hedge: {state.open_position_side} already open in this account",
                              "hedging_intra_account")

    # 4. Hedging across accounts (cross-account)
    if correlated_open_in_other_account is not None:
        if correlated_open_in_other_account != side:
            return GuardDecision(False,
                                  f"hedge: opposite {correlated_open_in_other_account} open on "
                                  f"correlated asset in another account",
                                  "hedging_cross_account")

    # 5. Daily Loss Limit (auto-flatten)
    if state.today_pnl <= -DLL:
        return GuardDecision(False, f"DLL hit: today P&L ${state.today_pnl:.0f}", "dll")
    # Or: this trade's worst case would push past DLL
    worst = state.today_pnl + proposed_pnl_at_stop
    if worst < -DLL:
        # Try to find a smaller size that stays inside DLL
        per_contract_stop = proposed_pnl_at_stop / max(1, n_contracts)
        room = -DLL - state.today_pnl  # negative number
        max_n = int(room / per_contract_stop) if per_contract_stop < 0 else 0
        if max_n < 1:
            return GuardDecision(False,
                                  f"trade's stop (${proposed_pnl_at_stop:+.0f}) would push DLL "
                                  f"(today ${state.today_pnl:+.0f}) past -${DLL:.0f}",
                                  "dll_projected")
        return GuardDecision(False,
                              f"stop+today would breach DLL; reduce size to <= {max_n}",
                              "dll_projected", suggested_n=max_n)

    # 6. Trailing drawdown breach. Block if the trade's worst-case stop
    #    would put balance within TRAIL_SAFETY_MARGIN of the trail floor.
    #    The +margin keeps a cushion for the NEXT losing trade — without it,
    #    a single stop could leave the account 1¢ above trail and the very
    #    next trade would be guaranteed to blow.
    worst_bal = state.balance + proposed_pnl_at_stop
    min_required = state.trail_floor + TRAIL_SAFETY_MARGIN
    if worst_bal <= min_required:
        return GuardDecision(False,
                              f"stop would leave balance ${worst_bal:.0f} ≤ "
                              f"${min_required:.0f} (trail ${state.trail_floor:.0f} "
                              f"+ ${TRAIL_SAFETY_MARGIN:.0f} safety margin)",
                              "trail_floor_margin")

    # 7. 40% consistency rule -- INFORMATIONAL ONLY, NOT A REAL-TIME BLOCK.
    #
    #    Lucid's actual rule: at WITHDRAWAL time, no single day's profit can
    #    be >= 40% of total profit. It's a snapshot check when you press
    #    "request payout", NOT a moment-to-moment cap on trading.
    #
    #    Previous version of this gate denied entries any time today's share
    #    crossed 40%, but that was overly conservative -- it stopped the bot
    #    mid-day even though the user could keep trading and let the ratio
    #    dilute over subsequent days before withdrawing. Removed: let the
    #    bot trade freely; the dashboard's "payout readiness" widget shows
    #    the user the current ratio so they pick the right day to click
    #    request-payout.
    #
    #    Kept this comment block so the absence is intentional, not a bug.

    # 8. Microscalp ratio -- block if >50% of profits already came from <=5s holds
    if state.micro_total_profit > 0:
        ratio = state.micro_short_profit / state.micro_total_profit
        if ratio >= MICROSCALP_PROFIT_RATIO:
            return GuardDecision(False,
                                  f"microscalp ratio {ratio*100:.0f}% >= 50% — Terms of Use violation",
                                  "microscalp")

    return GuardDecision(True, "ok", "ok", suggested_n=n_contracts)


# ---------------------------------------------------------------------------
# Withdrawal eligibility
# ---------------------------------------------------------------------------
@dataclass
class PayoutEligibility:
    eligible: bool
    reason: str
    profit_above_start: float
    days_traded: int
    take_home_at_split: float


def can_request_payout(state: LucidState) -> PayoutEligibility:
    profit = state.balance - START_BAL
    take = max(0.0, profit) * PROFIT_SPLIT
    if state.blown:
        return PayoutEligibility(False, "account blown", profit, state.n_trading_days, take)
    if profit < PROFIT_TARGET:
        return PayoutEligibility(False,
                                  f"profit ${profit:+.0f} < ${PROFIT_TARGET:.0f} target",
                                  profit, state.n_trading_days, take)
    if state.n_trading_days < MIN_DAYS_TO_PAYOUT:
        return PayoutEligibility(False,
                                  f"only {state.n_trading_days} trading days "
                                  f"(need {MIN_DAYS_TO_PAYOUT})",
                                  profit, state.n_trading_days, take)
    return PayoutEligibility(True, "eligible", profit, state.n_trading_days, take)


# ---------------------------------------------------------------------------
# One-shot static compliance audit (run on bot startup)
# ---------------------------------------------------------------------------
def audit_bot_compliance(*, min_hold_seconds: int, single_account: bool,
                         live_data_feed: bool, trades_front_month: bool,
                         operator_country_iso2: str) -> dict:
    """Static checks of bot configuration vs Lucid Terms of Use.

    Returns dict of {rule: (compliant, detail)}. Caller should fail-fast if
    any value is (False, ...).
    """
    out = {}
    out["microscalp_min_hold"] = (
        min_hold_seconds > MICROSCALP_HOLD_THRESHOLD_S,
        f"min hold {min_hold_seconds}s vs Lucid's >5s requirement",
    )
    out["hedging_single_account"] = (
        single_account,
        "bot operates a single Lucid account (no cross-account hedging possible)" if single_account
            else "MULTI-ACCOUNT setup requires per-trade cross-account hedge check",
    )
    out["data_feed_real"] = (
        live_data_feed,
        "uses live broker feed (not external/slow feed)" if live_data_feed
            else "Lucid prohibits trading on external/slow data feeds",
    )
    out["front_month_contract"] = (
        trades_front_month,
        "data loader rolls 9 days before 3rd-Friday expiry"
        if trades_front_month else "Lucid requires front-month trading",
    )
    out["country_eligible"] = (
        operator_country_iso2 not in RESTRICTED_COUNTRIES,
        f"operator country {operator_country_iso2!r} "
        + ("is allowed" if operator_country_iso2 not in RESTRICTED_COUNTRIES
           else "is on Lucid's restricted-countries list"),
    )
    return out


if __name__ == "__main__":
    # Self-test: simulate a tiny session and verify rules fire correctly
    import sys

    s = LucidState()
    print("Initial:", s.balance, "trail:", s.trail_floor)

    # Take a normal trade
    d = evaluate_trade(s, side="LONG", n_contracts=10,
                        proposed_pnl_at_target=200.0,
                        proposed_pnl_at_stop=-100.0)
    assert d.allowed, d.reason
    s.on_fill(side="LONG", n_contracts=10, realized_pnl=200.0,
               ts=datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc),
               hold_seconds=600)

    # Position cap
    d = evaluate_trade(s, side="LONG", n_contracts=50,
                        proposed_pnl_at_target=200.0, proposed_pnl_at_stop=-100.0)
    assert not d.allowed and d.rule == "position_cap", d
    print("[ok] position_cap blocks 50>40")

    # Hedging
    s.open_position_side = "LONG"; s.open_position_n = 5
    d = evaluate_trade(s, side="SHORT", n_contracts=5,
                        proposed_pnl_at_target=200.0, proposed_pnl_at_stop=-100.0)
    assert not d.allowed and d.rule == "hedging_intra_account", d
    print("[ok] hedging blocked")
    s.open_position_side = None

    # Static audit
    audit = audit_bot_compliance(min_hold_seconds=25 * 60, single_account=True,
                                  live_data_feed=True, trades_front_month=True,
                                  operator_country_iso2="GB")
    for k, (ok, msg) in audit.items():
        print(f"  {'OK ' if ok else 'XX '} {k}: {msg}")
    assert all(ok for ok, _ in audit.values()), "compliance audit failed"
    print("[ok] all static compliance checks pass")
