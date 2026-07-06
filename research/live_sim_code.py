"""No-lookahead simulation of THE BOT'S ACTUAL CODE over real ticks.

This is not a strategy re-implementation. It imports the live modules --
bot.pullback_strategy (setup detection, arming, tick fires, tick exits),
bot.lucid_account.LucidAccount (paper booking: slips, commission, DB) --
and replicates bot/fib_main.py's wiring verbatim, in the same order the
live process runs it:

  per tick:  broker exchange advances -> tick-exit check (bid/ask
             synthesized last+/-0.125 exactly like _on_tick_instant) ->
             try_fire_on_tick; on minute close -> on_new_1m_bar off the
             tick-built bars (live's primary bar source).

The broker side models Tradovate execution using the decision logic
copied from bot/tradovate_orders.py submit_market_with_bracket (default
marketable_limit: limit bumped 1pt through the market; mirror drift
caps: skip only favorable>=target-1 or adverse>=stop; paper's exact
bracket prices) and fc5455a's close flow (instant liquidate on paper
close, 2.5s bracket patience on target exits, duplicate-entry guard
skipping ONLY the broker leg). Exchange matching is the only modeled
part: marketable limits fill at the current tick bounded by the limit,
resting limits fill on touch-through (half-spread convention 0.125),
stops fill with 0.25pt adverse slip, target limits need one tick
through. Submit latency 65ms (the live-measured signal->placeoso p50).

STRICT no-lookahead: one chronological pass; every decision uses only
ticks at or before the current one; broker orders interact only with
ticks after their arrival time.

Usage:
  python -m research.live_sim_code data/tick/week/MNQU6_*.parquet
"""
from __future__ import annotations

import glob
import json
import os
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

# ---- live env BEFORE bot imports (mirrors the Railway config) ----------
os.environ.setdefault("BOT_DATA_DIR", tempfile.mkdtemp(prefix="simdata_"))
os.environ.setdefault("FIB_N_MNQ", "1")
os.environ.setdefault("STRAT_COOLDOWN_SECS", "10")
os.environ.setdefault("STRAT_ARMING", "0")
os.environ.setdefault("BOT_SHADOW_MODE", "1")   # never touch a real broker

import pandas as pd  # noqa: E402

PARAMS = {"IMPULSE_PTS": float(os.environ.get("SIM_IMPULSE_PTS", "2.0")),
          "IMPULSE_WINDOW_BARS": int(os.environ.get("SIM_IMPULSE_BARS", "3")),
          "PULLBACK_PCT": float(os.environ.get("SIM_PULLBACK_PCT", "0.118")),
          "STOP_PTS": float(os.environ.get("SIM_STOP_PTS", "5.0")),
          "TARGET_PTS": float(os.environ.get("SIM_TARGET_PTS", "44.0")),
          "INVERT": True}
if os.environ.get("SIM_COOLDOWN"):
    os.environ["STRAT_COOLDOWN_SECS"] = os.environ["SIM_COOLDOWN"]
HALF = 0.125          # half-spread convention, same constant as fib_main
STOP_SLIP = 0.25      # broker stop adverse slip (matches live fills)
LATENCY_S = 0.065     # live-measured signal->placeoso p50
BUFFER = 1.0          # BROKER_MARKETABLE_BUFFER_PTS default
FEES_RT = 1.96        # real all-in per round trip
PATIENCE_S = 2.5      # BROKER_TARGET_PATIENCE_S default
DIVERGENCE_PT = 30.0  # broker gate 4/4
PT = 2.0              # $/pt per MNQ


class BrokerSim:
    """Tradovate exchange model driven by the same tick stream."""

    def __init__(self):
        self.entry = None       # dict while an entry order lives
        self.pos = None         # dict while a position is open
        self.trades = []        # completed broker round trips
        self.skips = Counter()
        self.liq_at = None      # (t_exec, tag) pending liquidation
        self.anticip = None     # resting pre-touch limit (anticipatory mode)
        self.stats = Counter()  # anticipatory bookkeeping

    # -- anticipatory pre-touch resting limit ----------------------------
    # The ONLY mechanism that can buy paper's fill price: the LIMIT is
    # already on the book when the touch happens. Managed with strict
    # discipline: rest only while paper CAN fire (flat + cooldown ok +
    # live setup); cancel the moment eligibility disappears; any fill
    # not adopted by a paper fire within ADOPT_S is flattened at market.
    ADOPT_S = 1.5

    def anticipatory_manage(self, t, px, eligible):
        """eligible: list of (side, level) paper setups that could fire
        right now. Called once per tick, after fills processed."""
        if self.pos is not None:
            # holding (possibly awaiting adoption) -- no new rests
            if self.anticip is not None:
                self.anticip = None
                self.stats["anticip_cancelled"] += 1
            return
        if not eligible:
            if self.anticip is not None:
                self.anticip = None
                self.stats["anticip_cancelled"] += 1
            return
        side, level = min(eligible, key=lambda e: abs(e[1] - px))
        a = self.anticip
        if a is not None and a["side"] == side and abs(a["level"] - level) < 0.25:
            return  # already resting at the right price
        self.anticip = {"side": side, "level": float(level),
                        "arrive": t + LATENCY_S}
        self.stats["anticip_rested"] += 1

    def _anticip_fill_check(self, t, px):
        a = self.anticip
        if a is None or t < a["arrive"] or self.pos is not None:
            return
        L = a["level"]
        filled = (px <= L - HALF) if a["side"] == "LONG" else (px >= L + HALF)
        if filled:
            # fills AT the level -- the price paper books
            self.pos = {"ref": None, "side": a["side"], "entry": L,
                        "stop": None, "target": None, "t_in": t,
                        "level": L, "await_adopt_until": t + self.ADOPT_S}
            self.anticip = None
            self.stats["anticip_filled"] += 1

    def adopt(self, ref, side, stop_px, target_px, t):
        """Paper fired: claim the anticipatory fill (or the resting
        order) as this trade's entry. Returns True if adopted."""
        p = self.pos
        if p is not None and p.get("await_adopt_until") and p["side"] == side:
            p["ref"] = ref
            p["stop"] = float(stop_px)
            p["target"] = float(target_px)
            p.pop("await_adopt_until", None)
            self.stats["anticip_adopted"] += 1
            return True
        a = self.anticip
        if a is not None and a["side"] == side:
            # not filled yet -- convert the resting order into the
            # trade's entry order at the same price
            self.entry = {"ref": ref, "side": side, "limit": a["level"],
                          "stop": float(stop_px), "target": float(target_px),
                          "arrive": a["arrive"], "level": a["level"]}
            self.anticip = None
            self.stats["anticip_converted"] += 1
            return True
        return False

    # -- order placement (logic from tradovate_orders) -------------------
    def submit(self, ref, side, level, stop_px, target_px, live_px, t):
        mode = os.environ.get("BROKER_SIM_MODE", "marketable")
        # SIM_CHASE_MAX_DRIFT: only mirror trades whose head start is
        # small (fired at/near the touch). Everything else is skipped.
        cap = os.environ.get("SIM_CHASE_MAX_DRIFT")
        if cap and abs(live_px - level) > float(cap):
            self.skips["over_drift_cap"] += 1
            return False
        if mode == "rest_at_level":
            # Candidate policy: LIMIT at paper's exact level. Fills at
            # paper's price or better, or not at all (cancelled when
            # paper closes). No drift caps needed -- the limit price
            # bounds the fill by construction.
            limit = level
            self.entry = {"ref": ref, "side": side, "limit": limit,
                          "stop": stop_px, "target": target_px,
                          "arrive": t + LATENCY_S, "level": level}
            return True
        drift = abs(live_px - level)
        favorable = (live_px >= level) if side == "LONG" else (live_px <= level)
        if favorable and drift >= PARAMS["TARGET_PTS"] - 1.0:
            self.skips["drift_beyond_target"] += 1
            return False
        if (not favorable) and drift >= PARAMS["STOP_PTS"]:
            self.skips["drift_beyond_stop"] += 1
            return False
        if side == "LONG":
            limit = max(level, live_px + BUFFER)
        else:
            limit = min(level, live_px - BUFFER)
        self.entry = {"ref": ref, "side": side, "limit": limit,
                      "stop": stop_px, "target": target_px,
                      "arrive": t + LATENCY_S, "level": level}
        return True

    def cancel_entry(self):
        self.entry = None

    def request_close(self, t, reason):
        """Paper closed. Target exits get bracket patience; everything
        else liquidates as soon as the order can reach the exchange.

        SIM_INDEPENDENT_EXITS=1: the broker does NOT follow paper's
        exits at all -- it rides its own bracket, with only a max-hold
        liquidation mirroring the strategy's 600s timeout."""
        if self.pos is None:
            self.cancel_entry()
            return
        if os.environ.get("SIM_INDEPENDENT_EXITS") == "1":
            self.liq_at = (self.pos["t_in"] + 600.0, "timeout")
            return
        delay = PATIENCE_S if reason == "target" else LATENCY_S
        self.liq_at = (t + delay, reason)

    def flat(self):
        return self.pos is None and self.entry is None

    # -- exchange matching -----------------------------------------------
    def on_tick(self, t, px):
        self._anticip_fill_check(t, px)
        # unadopted anticipatory fill past its deadline -> flatten NOW
        p0 = self.pos
        if (p0 is not None and p0.get("await_adopt_until")
                and t >= p0["await_adopt_until"]):
            exit_px = px - HALF if p0["side"] == "LONG" else px + HALF
            pts = ((exit_px - p0["entry"]) if p0["side"] == "LONG"
                   else (p0["entry"] - exit_px))
            self.trades.append({
                "ref": "orphan", "side": p0["side"], "entry": p0["entry"],
                "exit": exit_px, "path": "orphan_flatten",
                "level": p0["level"], "t_in": p0["t_in"], "t_out": t,
                "pnl_net": round(pts * PT - FEES_RT, 2)})
            self.stats["anticip_orphaned"] += 1
            self.pos = None
        e = self.entry
        if e and t >= e["arrive"]:
            side = e["side"]
            fill = None
            if side == "LONG":
                if px <= e["limit"] - HALF:
                    fill = min(e["limit"], px + HALF)     # resting, touched
                elif e["limit"] >= px:                     # marketable
                    fill = px
            else:
                if px >= e["limit"] + HALF:
                    fill = max(e["limit"], px - HALF)
                elif e["limit"] <= px:
                    fill = px
            if fill is not None:
                stop_px, target_px = e["stop"], e["target"]
                if os.environ.get("SIM_BRACKET_ANCHOR") == "fill":
                    # Anchor brackets to the ACTUAL fill instead of
                    # paper's level: the broker keeps the strategy's
                    # intended 5/44 geometry no matter the head start.
                    sp = PARAMS["STOP_PTS"]
                    tp = PARAMS["TARGET_PTS"]
                    if side == "LONG":
                        stop_px, target_px = fill - sp, fill + tp
                    else:
                        stop_px, target_px = fill + sp, fill - tp
                self.pos = {"ref": e["ref"], "side": side, "entry": fill,
                            "stop": stop_px, "target": target_px,
                            "t_in": t, "level": e["level"]}
                self.entry = None
        p = self.pos
        if p is not None and p.get("stop") is not None:
            exit_px = None
            path = None
            # pending liquidation reached the exchange?
            if self.liq_at is not None and t >= self.liq_at[0]:
                exit_px = px - HALF if p["side"] == "LONG" else px + HALF
                path = ("liquidate_after_patience"
                        if self.liq_at[1] == "target" else "instant_liquidate")
            elif p["side"] == "LONG":
                if px <= p["stop"]:
                    exit_px, path = p["stop"] - STOP_SLIP, "bracket_stop"
                elif px >= p["target"] + HALF:
                    exit_px, path = p["target"], "bracket_target"
            else:
                if px >= p["stop"]:
                    exit_px, path = p["stop"] + STOP_SLIP, "bracket_stop"
                elif px <= p["target"] - HALF:
                    exit_px, path = p["target"], "bracket_target"
            if exit_px is not None:
                pts = ((exit_px - p["entry"]) if p["side"] == "LONG"
                       else (p["entry"] - exit_px))
                self.trades.append({
                    "ref": p["ref"], "side": p["side"],
                    "entry": p["entry"], "exit": exit_px, "path": path,
                    "level": p["level"], "t_in": p["t_in"], "t_out": t,
                    "pnl_net": round(pts * PT - FEES_RT, 2)})
                self.pos = None
                self.liq_at = None


def run(tick_files):
    from bot.pullback_strategy import (FibStrategyState, on_new_1m_bar,
                                       try_fire_on_tick, should_exit_on_tick,
                                       close_trade)
    from bot.lucid_account import LucidAccount
    from bot.tick_history import record_tick

    frames = [pd.read_parquet(f) for f in sorted(tick_files)]
    ticks = pd.concat(frames).sort_values("ts").reset_index(drop=True)
    ts_arr = ticks["ts"].to_numpy("int64") / 1e9
    px_arr = ticks["price"].to_numpy("float64")
    print(f"{len(ticks):,} ticks "
          f"{datetime.fromtimestamp(ts_arr[0], timezone.utc)} -> "
          f"{datetime.fromtimestamp(ts_arr[-1], timezone.utc)}", flush=True)

    state = FibStrategyState()
    account = LucidAccount()
    broker = BrokerSim()
    open_ref = None           # duplicate-entry guard state
    ref_n = 0
    paper_trades = []
    guard_skips = 0
    divergence_skips = 0
    # 1-minute bars built from the full tape -- equivalent to the
    # Polygon AM minute events that feed the live bot's bar frame
    # (the live _TickBarAggregator's own tick path is dead code; live
    # bars arrive via on_bar from AM events).
    MAXB = 2000
    bar_rows = []             # (ts, o, h, l, c, v) closed bars
    cur_min = None
    cur = None                # [o, h, l, c, v]
    bars_df = None

    ANTICIP = os.environ.get("BROKER_SIM_MODE") == "anticipatory"
    COOLDOWN_S = float(os.environ.get("STRAT_COOLDOWN_SECS", "10"))

    def paper_open(trade, px, now):
        nonlocal open_ref, ref_n, guard_skips, divergence_skips
        account.enter(
            signal_name=f"FIB_{trade.side}", side=trade.side,
            entry_px_raw=trade.entry_px, stop_px=trade.stop_px,
            target_px=trade.target_px, qty=trade.n_mnq, vol_regime="FIB",
            rr=abs(trade.target_px - trade.entry_px)
               / max(abs(trade.stop_px - trade.entry_px), 1e-9),
            now=now, entry_slip_pts=0.0, adverse_slip_pts=0.25,
            commission_per_mnq_rt=0.74)
        ref_n += 1
        ref = f"sim_{ref_n}"
        # ANTICIPATORY: the fill (or resting order) at paper's level is
        # already there -- claim it. Falls back to the live chase policy
        # only when there was nothing resting (late setup detection).
        if ANTICIP and broker.adopt(ref, trade.side, trade.stop_px,
                                    trade.target_px, now.timestamp()):
            open_ref = ref
            return
        # broker forwarding (fc5455a): guard skips ONLY the broker leg
        if not broker.flat():
            guard_skips += 1
            return
        if abs(trade.entry_px - px) > DIVERGENCE_PT:
            divergence_skips += 1
            return
        if broker.submit(ref, trade.side, float(trade.entry_px),
                         float(trade.stop_px), float(trade.target_px),
                         px, now.timestamp()):
            open_ref = ref

    def paper_close(record, now):
        nonlocal open_ref
        adverse = (record["exit_reason"] == "stop")
        try:
            account._close(exit_px_raw=record["exit_px"],
                           reason=record["exit_reason"],
                           adverse=adverse, now=now)
        except Exception as e:
            print("account close:", e)
        paper_trades.append(record)
        broker.request_close(now.timestamp(), record["exit_reason"])
        open_ref = None

    n = len(ticks)
    import time as _time
    _t0 = _time.time()
    for i in range(n):
        if i and i % 500_000 == 0:
            print(f"...{i:,}/{n:,} ticks "
                  f"({_time.time()-_t0:.0f}s, paper={len(paper_trades)}, "
                  f"broker={len(broker.trades)})", flush=True)
        t = ts_arr[i]
        px = float(px_arr[i])
        now = datetime.fromtimestamp(t, timezone.utc)
        # live parity: every Polygon tick lands in the tick_history ring
        try:
            record_tick(px, src="polygon")
        except Exception:
            pass
        # 1. exchange advances on this tick (fills, brackets, liqs)
        broker.on_tick(t, px)
        # 2. bar aggregation; a newly CLOSED bar drives on_new_1m_bar
        minute = now.replace(second=0, microsecond=0)
        if cur_min is None:
            cur_min, cur = minute, [px, px, px, px, 1]
        elif minute == cur_min:
            cur[1] = max(cur[1], px)
            cur[2] = min(cur[2], px)
            cur[3] = px
            cur[4] += 1
        else:
            bar_rows.append((cur_min, *cur))
            if len(bar_rows) > MAXB:
                bar_rows = bar_rows[-MAXB:]
            cur_min, cur = minute, [px, px, px, px, 1]
            if len(bar_rows) >= 5:
                bars_df = pd.DataFrame(
                    bar_rows, columns=["ts", "open", "high", "low",
                                       "close", "volume"]).set_index("ts")
                had = state.active_trade
                try:
                    rec = on_new_1m_bar(
                        state, account._build_runtime_lucid_state(),
                        bars_df, bars_df.iloc[-1], now,
                        n_mnq=1, bars_trend=bars_df,
                        params=PARAMS, calendar=None)
                except Exception as e:
                    rec = None
                    print("on_new_1m_bar:", e)
                if rec is not None:
                    paper_close(rec, now)
                if had is None and state.active_trade is not None:
                    paper_open(state.active_trade, px, now)
        # 3. tick exit (same synthesized bid/ask as _on_tick_instant)
        if state.active_trade is not None:
            res = should_exit_on_tick(state.active_trade,
                                      px - HALF, px + HALF, now)
            if res is not None:
                exit_px, reason = res
                rec = close_trade(state.active_trade, exit_px, reason, now)
                state.completed_trades.append(rec)
                state.active_trade = None
                state.last_trade_close_ts = now
                paper_close(rec, now)
                continue
        # 3.5 anticipatory resting-limit management: rest at the nearest
        # live setup's level ONLY while paper could fire right now.
        if ANTICIP:
            eligible = []
            if state.active_trade is None and state.pending_setups:
                cd_ok = True
                lc = state.last_trade_close_ts
                if lc is not None:
                    try:
                        cd_ok = (now - lc).total_seconds() >= COOLDOWN_S
                    except Exception:
                        cd_ok = True
                if cd_ok:
                    for s in state.pending_setups:
                        try:
                            if not s.used and now < s.expires_at:
                                eligible.append((s.side,
                                                 float(s.pullback_entry)))
                        except Exception:
                            continue
            broker.anticipatory_manage(t, px, eligible)
        # 4. tick fire (SIM_NO_TICK_FIRE=1 mimics the pre-Jul-2 live
        # build where the WS tick callback was not wired: fires then
        # happened only on the bar/cycle path, booking the level price
        # up to a minute after the touch)
        if os.environ.get("SIM_NO_TICK_FIRE") == "1":
            continue
        if state.pending_setups and state.active_trade is None:
            fired = try_fire_on_tick(
                state=state, lucid=account._build_runtime_lucid_state(),
                live_price=px, now=now, n_mnq=1,
                params=PARAMS, calendar=None)
            if fired and state.active_trade is not None:
                paper_open(state.active_trade, px, now)

    # ---- report ---------------------------------------------------------
    def day_of(ts_val):
        return (datetime.fromtimestamp(ts_val, timezone.utc)
                + timedelta(hours=2)).strftime("%Y-%m-%d")

    pdays = defaultdict(lambda: {"n": 0, "net": 0.0, "exits": Counter()})
    for r in paper_trades:
        d = day_of(r["exit_ts"].timestamp()
                   if hasattr(r.get("exit_ts"), "timestamp")
                   else pd.Timestamp(r["exit_ts"]).timestamp())
        pnl_net = (r.get("pnl_usd") or 0) - 0.74
        pdays[d]["n"] += 1
        pdays[d]["net"] = round(pdays[d]["net"] + pnl_net, 2)
        pdays[d]["exits"][r.get("exit_reason") or r.get("reason") or "?"] += 1
    bdays = defaultdict(lambda: {"n": 0, "net": 0.0, "paths": Counter()})
    for r in broker.trades:
        d = day_of(r["t_out"])
        bdays[d]["n"] += 1
        bdays[d]["net"] = round(bdays[d]["net"] + r["pnl_net"], 2)
        bdays[d]["paths"][r["path"]] += 1

    # hour-of-day economics (UTC) for the hour-filter avenue
    bhours = defaultdict(lambda: [0, 0.0])
    for r in broker.trades:
        h = datetime.fromtimestamp(r["t_out"], timezone.utc).hour
        bhours[h][0] += 1
        bhours[h][1] = round(bhours[h][1] + r["pnl_net"], 2)
    out = {
        "variant": {
            "mode": os.environ.get("BROKER_SIM_MODE", "marketable"),
            "chase_max_drift": os.environ.get("SIM_CHASE_MAX_DRIFT"),
            "bracket_anchor": os.environ.get("SIM_BRACKET_ANCHOR", "paper"),
            "independent_exits": os.environ.get("SIM_INDEPENDENT_EXITS"),
            "no_tick_fire": os.environ.get("SIM_NO_TICK_FIRE"),
            "cooldown": os.environ.get("STRAT_COOLDOWN_SECS"),
        },
        "broker_hours_utc": {str(k): {"n": v[0], "net": v[1]}
                             for k, v in sorted(bhours.items())},
        "params": PARAMS,
        "paper_days": {k: {"n": v["n"], "net_usd": v["net"],
                           "exits": dict(v["exits"])}
                       for k, v in sorted(pdays.items())},
        "broker_days": {k: {"n": v["n"], "net_usd": v["net"],
                            "paths": dict(v["paths"])}
                        for k, v in sorted(bdays.items())},
        "paper_total_net": round(sum(v["net"] for v in pdays.values()), 2),
        "broker_total_net": round(sum(v["net"] for v in bdays.values()), 2),
        "paper_n": len(paper_trades),
        "broker_n": len(broker.trades),
        "broker_skips": dict(broker.skips),
        "guard_skips": guard_skips,
        "divergence_skips": divergence_skips,
        "anticipatory": dict(broker.stats),
    }
    print(json.dumps(out, indent=1))
    with open(os.environ.get("SIM_OUT", "live_sim_result.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    return out


if __name__ == "__main__":
    pats = sys.argv[1:] or ["data/tick/week/*.parquet"]
    files = sorted(set(sum((glob.glob(p) for p in pats), [])))
    if not files:
        print("no tick files matched", pats)
        sys.exit(1)
    run(files)
