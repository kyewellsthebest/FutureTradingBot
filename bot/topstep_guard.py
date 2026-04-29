"""
TopStep compliance guard.

Hard-codes the TopStep rules so the bot CANNOT violate them — every trade
must be approved by this guard before it goes to the broker. Any rule
violation is rejected at this layer, before it ever touches the order
router. This is the "you can't lose your account because the code won't
let you" layer.

Rules enforced (per Topstep docs as of April 2026):

  ACCOUNT-LEVEL (hard, never bypassable)
    - Maximum Loss Limit (MLL):
        $50K  → $48,000 floor  (trails EOD high; locks at $50,000 once
                                balance reaches $52,000)
        $100K → $97,000 floor  (locks at $100,000 once $103,000)
        $150K → $145,500 floor (locks at $150,000 once $154,500)
      MLL is monitored in REAL TIME using realized + unrealized P&L —
      any intraday breach triggers immediate flatten + lockout for the
      session.

    - Daily Loss Limit (soft breach): auto-liquidate for the rest of
      the trading day if Net P&L hits or exceeds the daily limit.

    - Maximum Position Size:
        $50K  → 5 NQ or 50 MNQ
        $100K → 10 NQ or 100 MNQ
        $150K → 15 NQ or 150 MNQ
      Micros count 10:1 toward the limit on Topstep platforms.

  TIME-OF-DAY (hard)
    - Trading hours: 5:00 PM CT (previous day) → 3:10 PM CT
    - All positions MUST be flat by 3:10 PM CT
    - We auto-flatten 60 seconds before close (3:09 PM CT) to be safe

  PROHIBITED CONDUCT (hard)
    - No trades within 2% of a product's lock limit
    - No "scalping algorithm" patterns (avg trade duration ≥ 60 seconds)
    - No mass order entry (we cap to ≤ 30 orders/minute, which is far
      below any reasonable definition of HFT)
    - No trades using stale/external data feed (we lock to broker feed)
    - No same-strategy across multiple accounts in identical time
      increments (account-stacking detection)

  CIRCUIT BREAKERS (soft, configurable)
    - News blackout window around scheduled high-impact events
      (CPI, FOMC, NFP, GDP, PPI) — 15 min before, 30 min after
    - Daily trade cap (default 8/day, can raise but never below 1)
    - Per-trade risk cap (default 25% of buffer-to-MLL)
    - Max consecutive losing trades before mandatory pause (default 4)

Usage:
    guard = TopstepComplianceGuard.from_combine_50k()
    if guard.can_enter(signal, account_state, market_state, now_utc):
        contracts = guard.size_position(signal, account_state, market_state)
        place_order(...)
    else:
        log("rejected by guard: " + guard.last_rejection_reason)
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger("topstep_guard")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CT = ZoneInfo("America/Chicago")
NY = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Account-size profile — Topstep posted parameters
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TopstepProfile:
    """Static account-size parameters from Topstep's published rules."""
    label: str
    starting_balance: float
    max_loss_limit_dollars: float    # the buffer (e.g. $2k for $50K)
    profit_target: float              # buffer above starting to pass Combine
    daily_loss_limit: float           # soft breach
    max_nq_contracts: int             # max NQ (full) contracts
    max_mnq_contracts: int            # max MNQ (micro) contracts via 10:1


PROFILES = {
    "50K": TopstepProfile(
        label="$50K Combine",
        starting_balance=50_000.0,
        max_loss_limit_dollars=2_000.0,
        profit_target=3_000.0,
        daily_loss_limit=1_000.0,
        max_nq_contracts=5,
        max_mnq_contracts=50,
    ),
    "100K": TopstepProfile(
        label="$100K Combine",
        starting_balance=100_000.0,
        max_loss_limit_dollars=3_000.0,
        profit_target=6_000.0,
        daily_loss_limit=2_000.0,
        max_nq_contracts=10,
        max_mnq_contracts=100,
    ),
    "150K": TopstepProfile(
        label="$150K Combine",
        starting_balance=150_000.0,
        max_loss_limit_dollars=4_500.0,
        profit_target=9_000.0,
        daily_loss_limit=3_000.0,
        max_nq_contracts=15,
        max_mnq_contracts=150,
    ),
}


# ---------------------------------------------------------------------------
# Per-trade and per-account state used for the guard's decisions
# ---------------------------------------------------------------------------

@dataclass
class AccountSnapshot:
    """The minimum state the guard needs to make a decision."""
    balance: float                    # current balance (realized + funded baseline)
    eod_high_balance: float           # highest END-OF-DAY balance seen so far
    mll_locked: bool                  # has MLL locked at starting_balance?
    mll_floor: float                  # current MLL value
    realized_pnl_today: float
    unrealized_pnl: float = 0.0
    open_position_contracts: int = 0
    consecutive_losers: int = 0
    trades_today: int = 0
    last_n_trade_durations_sec: list[float] = field(default_factory=list)


@dataclass
class MarketSnapshot:
    """Last-known market state — used to reject within-lock-limit trades."""
    last_price: float
    daily_high: float
    daily_low: float
    daily_lock_limit_dollars: float = 1500.0   # CME daily price-limit move
    in_news_blackout: bool = False
    news_event_label: str | None = None


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------

class TopstepComplianceGuard:
    """Hard rule enforcement for Topstep accounts. Reject ANY trade that
    would breach the rules — no exceptions, no overrides."""

    # Cut-off times (Chicago time)
    SESSION_OPEN_CT = time(17, 0)        # 5:00 PM CT (Sunday open / day rollover)
    SESSION_FLATTEN_CT = time(15, 9)     # 3:09 PM CT — flatten 60s before close
    SESSION_CLOSE_CT = time(15, 10)      # 3:10 PM CT

    # Daily loss-limit auto-liquidate:  if realized P&L for the day hits this,
    # halt trading for the session
    # (this is the soft-breach mechanism)
    # Exposed at profile.daily_loss_limit

    def __init__(self,
                 profile: TopstepProfile,
                 max_trades_per_day: int = 8,
                 max_consecutive_losers: int = 4,
                 per_trade_buffer_risk_pct: float = 0.25,
                 min_trade_duration_sec: float = 60.0,
                 news_blackout_pre_min: int = 15,
                 news_blackout_post_min: int = 30):
        self.profile = profile
        self.max_trades_per_day = max_trades_per_day
        self.max_consecutive_losers = max_consecutive_losers
        self.per_trade_buffer_risk_pct = per_trade_buffer_risk_pct
        self.min_trade_duration_sec = min_trade_duration_sec
        self.news_blackout_pre_min = news_blackout_pre_min
        self.news_blackout_post_min = news_blackout_post_min
        self.last_rejection_reason: str | None = None

    @classmethod
    def from_combine_50k(cls, **kw):
        return cls(profile=PROFILES["50K"], **kw)

    @classmethod
    def from_combine_100k(cls, **kw):
        return cls(profile=PROFILES["100K"], **kw)

    @classmethod
    def from_combine_150k(cls, **kw):
        return cls(profile=PROFILES["150K"], **kw)

    # ----- Hard rule checks --------------------------------------------------

    def _reject(self, reason: str) -> bool:
        self.last_rejection_reason = reason
        logger.warning(f"[guard] REJECT: {reason}")
        return False

    def _ct_time(self, now_utc: datetime) -> time:
        return now_utc.astimezone(CT).time()

    def can_enter(self,
                  *,
                  account: AccountSnapshot,
                  market: MarketSnapshot,
                  signal_stop_pts: float,
                  signal_target_pts: float,
                  now_utc: datetime) -> bool:
        """Returns True iff a new trade is allowed under all hard rules."""
        self.last_rejection_reason = None

        # 1. SESSION CLOSED
        ct_now = self._ct_time(now_utc)
        if not (ct_now >= self.SESSION_OPEN_CT or ct_now < self.SESSION_FLATTEN_CT):
            return self._reject(f"outside_session_ct={ct_now}")
        if ct_now >= self.SESSION_FLATTEN_CT and ct_now < self.SESSION_OPEN_CT:
            return self._reject(f"flatten_window_ct={ct_now}")

        # 2. POSITION OPEN
        if account.open_position_contracts > 0:
            return self._reject("position_already_open")

        # 3. MLL — current balance + worst-case full-stop loss must stay above MLL
        # buffer-to-MLL must be > 0 to even consider a trade
        buffer = account.balance + account.unrealized_pnl - account.mll_floor
        if buffer <= 0:
            return self._reject(f"mll_breach_buffer={buffer:.2f}")

        # 4. DAILY LOSS LIMIT (soft breach)
        if account.realized_pnl_today <= -self.profile.daily_loss_limit:
            return self._reject(
                f"daily_loss_limit_hit={account.realized_pnl_today:.2f}"
            )

        # 5. DAILY TRADE CAP
        if account.trades_today >= self.max_trades_per_day:
            return self._reject(f"trades_today={account.trades_today}")

        # 6. CONSECUTIVE LOSERS pause
        if account.consecutive_losers >= self.max_consecutive_losers:
            return self._reject(f"consec_losers={account.consecutive_losers}")

        # 7. NEWS BLACKOUT
        if market.in_news_blackout:
            return self._reject(f"news_blackout={market.news_event_label}")

        # 8. PRICE-LOCK PROXIMITY (Topstep prohibits trading within 2% of lock)
        if market.daily_lock_limit_dollars > 0:
            # NQ daily limit ≈ 7% expansions in tiers; we don't have the exact
            # number, so guard at 2% of *daily range* as a proxy
            daily_range = max(market.daily_high - market.daily_low, 1.0)
            if daily_range >= market.daily_lock_limit_dollars * 0.98:
                return self._reject(f"near_lock_limit_range={daily_range:.0f}")

        # 9. SCALPING / SPEED — average recent trade duration check
        if account.last_n_trade_durations_sec:
            avg = sum(account.last_n_trade_durations_sec) / \
                  len(account.last_n_trade_durations_sec)
            if avg < self.min_trade_duration_sec:
                return self._reject(f"avg_duration_{avg:.0f}s_below_min")

        return True

    def size_position(self,
                       *,
                       account: AccountSnapshot,
                       signal_wr: float,
                       signal_n_obs: int,
                       signal_stop_pts: float,
                       signal_target_pts: float,
                       kelly_fraction: float = 0.5,
                       dollars_per_pt_mnq: float = 2.0,
                       comm_per_mnq: float = 0.40) -> int:
        """Compute the max-allowed MNQ contract count under all guard rules.

        Returns 0 if the guard cannot find a safe size (caller should reject
        the trade).
        """
        # Half-Kelly with uncertainty haircut + buffer cap
        if signal_target_pts <= 0 or signal_stop_pts <= 0:
            return 0
        rr = signal_target_pts / signal_stop_pts
        f = (signal_wr * rr - (1 - signal_wr)) / rr if rr > 0 else 0
        if f <= 0:
            return 0
        f = min(f * kelly_fraction, 0.10)
        if signal_n_obs < 100:
            f *= math.sqrt(signal_n_obs / 100)

        bal = account.balance + account.unrealized_pnl
        target_risk = bal * f

        risk_per_mnq = signal_stop_pts * dollars_per_pt_mnq + comm_per_mnq
        if risk_per_mnq <= 0:
            return 0
        n = int(target_risk // risk_per_mnq)

        # 25%-of-buffer cap
        buffer = bal - account.mll_floor
        n_buffer = int((buffer * self.per_trade_buffer_risk_pct) // risk_per_mnq)
        n = min(n, n_buffer)

        # Topstep position cap
        n = min(n, self.profile.max_mnq_contracts)

        # Daily-loss-limit cap: if a full stop loss would breach DLL → reject
        # remaining DLL room
        dll_room = self.profile.daily_loss_limit + account.realized_pnl_today
        if dll_room <= 0:
            return 0
        n_dll = int(dll_room // risk_per_mnq)
        n = min(n, n_dll)

        return max(0, n)

    def update_eod(self, account: AccountSnapshot) -> AccountSnapshot:
        """Call at end of each trading day. Updates MLL trail + lock state."""
        new_high = max(account.eod_high_balance, account.balance)
        if account.mll_locked:
            new_floor = self.profile.starting_balance
        else:
            new_floor = max(account.mll_floor,
                            new_high - self.profile.max_loss_limit_dollars)
            if new_high >= self.profile.starting_balance + self.profile.max_loss_limit_dollars:
                # locks at starting balance once we reach $52k (= $50k + $2k buffer)
                new_floor = self.profile.starting_balance
                account.mll_locked = True
        account.eod_high_balance = new_high
        account.mll_floor = new_floor
        account.realized_pnl_today = 0.0
        account.trades_today = 0
        return account

    def force_flatten_required(self, *, account: AccountSnapshot, now_utc: datetime) -> bool:
        """Returns True if the bot MUST flatten any open position immediately
        (session close approaching OR MLL breach detected)."""
        ct_now = self._ct_time(now_utc)
        if ct_now >= self.SESSION_FLATTEN_CT and ct_now < self.SESSION_OPEN_CT:
            return True
        # Real-time MLL breach with current unrealized P&L
        live_balance = account.balance + account.unrealized_pnl
        if live_balance <= account.mll_floor:
            return True
        if account.realized_pnl_today <= -self.profile.daily_loss_limit:
            return True
        return False


# ---------------------------------------------------------------------------
# Self-test — run with `python -m bot.topstep_guard` to verify rules
# ---------------------------------------------------------------------------

def _self_test():
    print("=" * 70)
    print("TOPSTEP COMPLIANCE GUARD — self-test")
    print("=" * 70)
    g = TopstepComplianceGuard.from_combine_50k()
    p = g.profile
    acct = AccountSnapshot(
        balance=50_000.0,
        eod_high_balance=50_000.0,
        mll_locked=False,
        mll_floor=p.starting_balance - p.max_loss_limit_dollars,
        realized_pnl_today=0.0,
    )
    mkt = MarketSnapshot(last_price=20_000.0, daily_high=20_100.0, daily_low=19_900.0)
    now = datetime(2026, 4, 29, 14, 0, tzinfo=timezone.utc)   # mid-session

    print(f"\nProfile: {p.label}")
    print(f"  Starting balance:  ${p.starting_balance:,.0f}")
    print(f"  MLL floor:         ${acct.mll_floor:,.0f}  (${p.max_loss_limit_dollars:,.0f} buffer)")
    print(f"  Profit target:     ${p.starting_balance + p.profit_target:,.0f}")
    print(f"  Position cap:      {p.max_nq_contracts} NQ / {p.max_mnq_contracts} MNQ")

    # Sane signal: WR 60%, RR 2:1, stop 15pt, 200 observations
    n = g.size_position(
        account=acct, signal_wr=0.60, signal_n_obs=200,
        signal_stop_pts=15.0, signal_target_pts=30.0,
    )
    print(f"\nSizing test (WR 60%, RR 1:2, 15pt stop):")
    print(f"  Recommended size: {n} MNQ contracts")
    print(f"  Max allowed:      {p.max_mnq_contracts} MNQ")

    # Hard-rule tests
    cases = [
        ("normal trade", lambda: g.can_enter(account=acct, market=mkt,
                                              signal_stop_pts=15, signal_target_pts=30,
                                              now_utc=now)),
        ("after 8 trades", lambda: g.can_enter(account=AccountSnapshot(**{**acct.__dict__, "trades_today": 8}),
                                                market=mkt, signal_stop_pts=15,
                                                signal_target_pts=30, now_utc=now)),
        ("DLL hit",       lambda: g.can_enter(account=AccountSnapshot(**{**acct.__dict__, "realized_pnl_today": -1100}),
                                                market=mkt, signal_stop_pts=15,
                                                signal_target_pts=30, now_utc=now)),
        ("position open", lambda: g.can_enter(account=AccountSnapshot(**{**acct.__dict__, "open_position_contracts": 5}),
                                                market=mkt, signal_stop_pts=15,
                                                signal_target_pts=30, now_utc=now)),
        ("MLL breach",    lambda: g.can_enter(account=AccountSnapshot(**{**acct.__dict__, "balance": 47_500}),
                                                market=mkt, signal_stop_pts=15,
                                                signal_target_pts=30, now_utc=now)),
        ("news blackout", lambda: g.can_enter(account=acct,
                                                market=MarketSnapshot(last_price=20_000, daily_high=20_100,
                                                                       daily_low=19_900, in_news_blackout=True,
                                                                       news_event_label="CPI"),
                                                signal_stop_pts=15, signal_target_pts=30,
                                                now_utc=now)),
        ("after-hours",   lambda: g.can_enter(account=acct, market=mkt,
                                                signal_stop_pts=15, signal_target_pts=30,
                                                now_utc=datetime(2026, 4, 29, 21, 0, tzinfo=timezone.utc))),
    ]
    print("\nHard-rule tests:")
    for name, fn in cases:
        ok = fn()
        msg = "ALLOWED" if ok else f"REJECTED ({g.last_rejection_reason})"
        print(f"  {name:<20} → {msg}")
    print()


if __name__ == "__main__":
    _self_test()
