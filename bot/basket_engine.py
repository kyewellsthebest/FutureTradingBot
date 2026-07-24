"""SNAP-BACK BASKET engine (middle dial, v1) — DEMO ONLY.

Runs the 26 validated sleeves from research/basket_sleeves.json across
MES/M2K/MYM/MGC/MCL/ZB on 5-minute bars pulled through the existing
Tradovate stack (bot.tradovate_bars / bot.tradovate_orders).

Faithful to the validated backtest (bot mirrors mega_multi.evaluate):
  entries on CLOSED 5-min bars only; fade/momo/pullback/breakout/volspike
  triggers with ATR thresholds; limit sleeves rest 0.5*ATR away with a
  3-bar TTL; exits = ATR target / ATR stop / H-bar time-out; EVERYTHING
  flat by session end. 1 contract per sleeve (units=1 in v1).

Hard rails (non-negotiable):
  * refuses to start unless the Tradovate session is DEMO
  * daily circuit-breaker: realized day P&L <= -$1,000 x units -> flatten
    all, halt until next session
  * kill-switch: cumulative P&L <= -$2,000 -> flatten, halt permanently
    (writes data/basket_killed.flag; human must delete it to restart)
  * exogenous gates (VIX/AAII/NAAIM) come from data/gates_daily.json;
    if the file is missing or stale, gated sleeves simply DON'T trade
    (safe state) while ungated sleeves continue.

Run standalone:  python -m bot.basket_engine
or via fib_main hook when data/basket_enabled.flag exists.
"""
from __future__ import annotations
import json, math, os, threading, time, logging
import datetime as dt
from pathlib import Path

logger = logging.getLogger("basket")
ROOT = Path(__file__).resolve().parent.parent
CFG_PATH = ROOT / "research" / "basket_sleeves.json"      # code, ships in git
# Runtime state lives in the bot's REAL data dir: on Railway that is the
# persistent volume (BOT_DATA_DIR), NOT the repo checkout's data/ folder —
# files committed to git under data/ never reach the host (learned from
# the 2026-07-24 bundle: enabled flag + gates were invisible on the host).
DATA = Path(os.environ.get("BOT_DATA_DIR") or (ROOT / "data"))
try:
    DATA.mkdir(parents=True, exist_ok=True)
except Exception:
    pass
GATES_PATH = DATA / "gates_daily.json"
STATE_PATH = DATA / "basket_state.json"
KILL_FLAG = DATA / "basket_killed.flag"
DISABLED_FLAG = DATA / "basket_disabled.flag"
STATUS_PATH = DATA / "basket_status.json"
PRICES_PATH = DATA / "basket_prices.json"

# Frozen research constants for the exogenous gates. vix_med is the
# median the sleeves were validated against; AAII/NAAIM are the latest
# known readings (they move slowly — weekly surveys). VIX itself is
# fetched LIVE daily; sentiment values carry until refreshed.
GATE_DEFAULTS = {"vix_med": 17.93, "aaii_bb": 0.116279,
                 "naaim": 80.61, "naaim_med": 71.2857143}


def basket_enabled() -> bool:
    """Default ON (user order 2026-07-24: 'get the bot working and
    trading properly'). Off only via BASKET_ENABLED=0 or the disabled
    flag file. The kill-switch is separate and handled inside run()."""
    if os.environ.get("BASKET_ENABLED", "1").strip() == "0":
        return False
    return not DISABLED_FLAG.exists()


def _fetch_vix():
    """Live VIX close: Yahoo chart API, then Stooq. Returns (px, src)
    or (None, None) — caller decides the safe fallback."""
    import urllib.request
    try:
        req = urllib.request.Request(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX"
            "?range=5d&interval=1d",
            headers={"User-Agent": "Mozilla/5.0"})
        j = json.loads(urllib.request.urlopen(req, timeout=8).read().decode())
        cl = [x for x in j["chart"]["result"][0]["indicators"]["quote"][0]
              ["close"] if x]
        if cl:
            return float(cl[-1]), "yahoo"
    except Exception:
        pass
    try:
        req = urllib.request.Request(
            "https://stooq.com/q/l/?s=%5Evix&f=sd2t2ohlcv&h&e=csv",
            headers={"User-Agent": "Mozilla/5.0"})
        txt = urllib.request.urlopen(req, timeout=8).read().decode()
        px = float(txt.splitlines()[1].split(",")[6])
        if px > 0:
            return px, "stooq"
    except Exception:
        pass
    return None, None

UNITS = 1
POLL_S = 40
BAR_S = 300
SESS = {"us": (13.5, 20.0), "eu": (7.0, 13.5), "asia": (0.0, 7.0), "all": (0.0, 24.0)}
EOD_UTC = 20.9                      # flatten everything by 20:54 UTC
# keyed by RESEARCH ROOT (sleeve.instr), values for the traded micro contract
TICKS = {"ES": 0.25, "RTY": 0.1, "YM": 1.0, "GC": 0.1, "CL": 0.01, "ZB": 1 / 32}
PV = {"ES": 5.0, "RTY": 5.0, "YM": 0.5, "GC": 10.0, "CL": 100.0, "ZB": 1000.0}
MONTH_Q = {3: "H", 6: "M", 9: "U", 12: "Z"}
MONTH_ALL = {1:"F",2:"G",3:"H",4:"J",5:"K",6:"M",7:"N",8:"Q",9:"U",10:"V",11:"X",12:"Z"}


def front_symbol(root: str, today: dt.date | None = None) -> str:
    """Front-month contract with a 3-day pre-expiry roll buffer."""
    today = today or dt.date.today()
    if root in ("MES", "M2K", "MYM", "ZB"):
        months = sorted(MONTH_Q)
    elif root == "MGC":
        months = [2, 4, 6, 8, 10, 12]
    else:                              # MCL: monthly
        months = list(range(1, 13))
    for delta in range(0, 15):
        m = (today.month + delta - 1) % 12 + 1
        y = today.year + (today.month + delta - 1) // 12
        if m not in months:
            continue
        # approx expiry: 3rd Friday (equity/ZB) else 20th; roll 3 days early
        d = dt.date(y, m, 1)
        third_fri = 1 + ((4 - d.weekday()) % 7) + 14
        exp = dt.date(y, m, min(third_fri, 28)) if root in ("MES","M2K","MYM","ZB") \
              else dt.date(y, m, 20)
        if exp - dt.timedelta(days=3) > today:
            code = (MONTH_Q if root in ("MES","M2K","MYM","ZB") else MONTH_ALL)[m]
            return f"{root}{code}{y % 10}"
    return f"{root}{MONTH_Q[12]}{today.year % 10}"


def _load_json(p: Path, default):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


class Gates:
    def __init__(self):
        self.d = {}
        self.load()

    def load(self):
        self.d = _load_json(GATES_PATH, {})

    def fresh(self) -> bool:
        try:
            age = (dt.date.today() - dt.date.fromisoformat(self.d["date"])).days
            return age <= 5
        except Exception:
            return False

    def ok(self, gate: str) -> bool:
        """True if this sleeve's exogenous gate is open. Missing data -> gated
        sleeves stay OFF (safe), 'none' sleeves always on."""
        if gate == "none":
            return True
        if not self.fresh():
            return False
        g = self.d
        try:
            if gate == "vix_lt":   return g["vix"] < g["vix_med"]
            if gate == "vix_gt":   return g["vix"] > g["vix_med"]
            if gate == "aaii_bull": return g["aaii_bb"] > 0
            if gate == "aaii_bear": return g["aaii_bb"] < 0
            if gate == "naaim_lt": return g["naaim"] < g["naaim_med"]
            if gate == "naaim_gt": return g["naaim"] > g["naaim_med"]
        except Exception:
            return False
        return False


class Features:
    """Rolling 5-min OHLCV features for one instrument (mirrors backtest)."""
    def __init__(self):
        self.bars = []          # list of dicts o,h,l,c,v,ts (closed bars only)

    def update(self, bars: list) -> bool:
        """Returns True if a NEW closed bar arrived."""
        if not bars:
            return False
        prev = self.bars[-1]["ts"] if self.bars else None
        clean = [b for b in bars if b.get("c") is not None]
        if not clean:
            return False
        self.bars = clean[-300:]
        return prev is None or self.bars[-1]["ts"] != prev

    def _col(self, k):
        return [b[k] for b in self.bars]

    def ready(self) -> bool:
        return len(self.bars) >= 60

    def atr(self, n=14):
        h, l, c = self._col("h"), self._col("l"), self._col("c")
        trs = [max(h[i]-l[i], abs(c[i]-c[i-1])) for i in range(1, len(c))]
        return sum(trs[-n:]) / n

    def mom(self, lb):
        c = self._col("c"); return c[-1] - c[-1-lb]

    def ma(self, n):
        c = self._col("c"); return sum(c[-n:]) / n

    def rmax(self, n):
        return max(self._col("h")[-n:])

    def rmin(self, n):
        return min(self._col("l")[-n:])

    def volz(self, n=48):
        v = self._col("v")[-n:]
        mu = sum(v)/len(v); sd = (sum((x-mu)**2 for x in v)/len(v)) ** 0.5
        return (v[-1]-mu)/(sd+1e-9)

    def last(self):
        return self.bars[-1]


class Sleeve:
    def __init__(self, idx, spec):
        self.idx = idx
        self.instr = spec["instr"]
        self.cfg = spec["cfg"]
        self.pos = 0                 # -1/0/+1
        self.entry_px = None
        self.entry_bar_ts = None
        self.tgt = None
        self.stop = None
        self.pending = None          # dict(limit px, side, ttl bars) for limit sleeves

    def signal(self, F: Features):
        """Mirror of mega_multi.evaluate entry logic on the last CLOSED bar."""
        cfg = self.cfg; c = F.last()["c"]; o = F.last()["o"]
        a = F.atr(14)
        if not a or a <= 0:
            return 0, a
        fam = cfg["fam"]
        if fam in ("fade", "momo"):
            m = F.mom(cfg["lb"])
            if abs(m) <= cfg["k"] * a:
                return 0, a
            s = (1 if m < 0 else -1) if fam == "fade" else (1 if m > 0 else -1)
            return s, a
        if fam == "breakout":
            if c >= F.rmax(cfg["rn"]) - 1e-9:  return 1, a
            if c <= F.rmin(cfg["rn"]) + 1e-9:  return -1, a
            return 0, a
        if fam == "pullback":
            ma = F.ma(cfg["man"]); m = F.mom(cfg["lb"])
            if c > ma and m < 0:  return 1, a
            if c < ma and m > 0:  return -1, a
            return 0, a
        if fam == "volspike":
            if F.volz() > cfg["k"]:
                return (1 if c > o else -1), a
            return 0, a
        return 0, a

    def describe(self) -> str:
        """One-line human description of what this mini-bot looks for."""
        c = self.cfg; fam = c["fam"]
        sess = {"us": "US hours", "eu": "EU hours", "asia": "Asia hours",
                "all": "24h"}.get(c.get("sess", "us"), c.get("sess"))
        if fam == "fade":
            d = f"fades {c['lb']}-bar moves > {c['k']}x ATR"
        elif fam == "momo":
            d = f"rides {c['lb']}-bar moves > {c['k']}x ATR"
        elif fam == "breakout":
            d = f"buys/sells {c['rn']}-bar range breaks"
        elif fam == "pullback":
            d = f"buys dips above the {c['man']}-bar average"
        else:
            d = f"trades volume spikes > {c['k']} sigma"
        return f"{d}, {sess}"

    def proximity(self, F: Features):
        """0..100 = how close the setup is to firing (rough, for display)."""
        try:
            cfg = self.cfg; fam = cfg["fam"]
            a = F.atr(14)
            if not a or a <= 0:
                return 0
            c = F.last()["c"]
            if fam in ("fade", "momo"):
                return int(min(100, abs(F.mom(cfg["lb"])) / (cfg["k"] * a) * 100))
            if fam == "breakout":
                rmx, rmn = F.rmax(cfg["rn"]), F.rmin(cfg["rn"])
                up = max(0.0, 1 - (rmx - c) / a); dn = max(0.0, 1 - (c - rmn) / a)
                return int(min(100, max(up, dn) * 100))
            if fam == "pullback":
                ma = F.ma(cfg["man"]); m = F.mom(cfg["lb"])
                live = (c > ma and m < 0) or (c < ma and m > 0)
                return 100 if live else 25
            if fam == "volspike":
                return int(min(100, max(0.0, F.volz() / cfg["k"]) * 100))
        except Exception:
            pass
        return 0


class BasketEngine:
    def __init__(self):
        self.cfg = _load_json(CFG_PATH, None)
        if not self.cfg:
            raise RuntimeError("basket_sleeves.json missing")
        self.sleeves = [Sleeve(i, s) for i, s in enumerate(self.cfg["sleeves"])]
        self.roots = sorted({s.instr for s in self.sleeves})
        # Resolve tradable contracts IMMEDIATELY — not only on day roll.
        # (Bug found via 2026-07-24 bundle: a same-day restart loaded
        # state with day==today, the roll never fired, symbols stayed {}
        # and the engine sat idle with no bars, no prices, no trades.)
        cmap = self.cfg.get("contracts", {})
        self.symbols = {r: front_symbol(cmap.get(r, r)) for r in self.roots}
        self.feats = {r: Features() for r in self.roots}
        self.gates = Gates()
        self.state = _load_json(STATE_PATH, {"cum_pnl": 0.0, "day": None, "day_pnl": 0.0})
        self.halted_today = False
        self._orders = None

    # ---------------- broker glue ----------------
    def _ensure_demo(self):
        from bot.tradovate_client import _is_demo
        if not _is_demo():
            raise RuntimeError("REFUSING TO START: session is not DEMO. "
                               "Basket engine is demo-only until explicitly authorized.")

    def orders(self):
        if self._orders is None:
            from bot.tradovate_client import get_session
            from bot.tradovate_orders import TradovateOrders
            self._orders = TradovateOrders(get_session())
        return self._orders

    def bars_for(self, root):
        from bot.tradovate_bars import get_bars
        sym = self.symbols[root]
        df = get_bars(sym, "5m", 240)
        if df is None or len(df) < 2:
            return []
        out = []
        for ts, row in df.iterrows():
            try:
                out.append(dict(ts=str(ts), o=float(row["open"]), h=float(row["high"]),
                                l=float(row["low"]), c=float(row["close"]),
                                v=float(row.get("volume", 0) or 0)))
            except Exception:
                continue
        return out[:-1]                          # drop the forming bar: CLOSED only

    def market(self, root, side, qty=1, why=""):
        """side: +1/-1 or 'Buy'/'Sell' -> TradovateOrders LONG/SHORT."""
        sym = self.symbols[root]
        s = side if isinstance(side, str) else ("Buy" if side > 0 else "Sell")
        api_side = "LONG" if s == "Buy" else "SHORT"
        logger.info(f"[basket] ORDER {api_side} {qty} {sym} ({why})")
        return self.orders().submit_market(side=api_side, qty=int(qty),
                                           symbol=sym, setup_ref=f"basket:{why}")

    # ---------------- live prices (Polygon REST, Tradovate fallback) ----
    def _poll_price_polygon(self, sym: str):
        """Latest price from Polygon's futures REST (the user's live feed).
        Endpoint format mirrors research/fetch_polygon_history.py, the
        one PROVEN shape against this account: /futures/v1/aggs/{ticker}
        with resolution "1_minute" (underscore — "1min" 400s). We window
        to the last 2h and take the newest bar client-side; the forming
        minute updates in near-real-time. A trades endpoint is tried
        first for true last-trade, tolerated to fail."""
        key = os.environ.get("POLYGON_API") or os.environ.get("POLYGON_API_KEY")
        if not key:
            return None
        import urllib.request
        now_ns = int(time.time() * 1e9)

        def newest(j, tkeys, vkey):
            rs = (j or {}).get("results") or []
            best = None
            for r in rs:
                try:
                    t = max(int(r.get(k) or 0) for k in tkeys)
                    v = float(r[vkey])
                    if best is None or t > best[0]:
                        best = (t, v)
                except Exception:
                    continue
            return best[1] if best else None

        for url, pick in (
            (f"https://api.polygon.io/futures/v1/trades/{sym}"
             f"?limit=10&apiKey={key}",
             lambda j: newest(j, ("sip_timestamp", "timestamp",
                                  "participant_timestamp"), "price")),
            (f"https://api.polygon.io/futures/v1/aggs/{sym}"
             f"?resolution=1_minute&window_start.gte={now_ns - 7_200_000_000_000}"
             f"&limit=200&apiKey={key}",
             lambda j: newest(j, ("window_start",), "close")),
        ):
            try:
                with urllib.request.urlopen(url, timeout=4) as r:
                    px = pick(json.loads(r.read().decode()))
                if px:
                    return float(px)
            except Exception:
                continue
        return None

    def _price_loop(self):
        """Every ~5s: refresh live prices for all traded contracts and write
        basket_prices.json for the dashboard. Polygon = live (user pays for
        it); last closed 5-min bar = fallback, tagged so the UI is honest."""
        last_warn = 0.0
        while True:
            out = {}
            n_live = 0
            for root in self.roots:
                sym = self.symbols.get(root)
                if not sym:
                    continue
                px = self._poll_price_polygon(sym)
                src = "polygon-live"
                if px is None:
                    src = "bar-close"
                    try:
                        px = self.feats[root].last()["c"]
                    except Exception:
                        px = None
                else:
                    n_live += 1
                if px is not None:
                    out[root] = {"symbol": sym, "px": px, "src": src,
                                 "ts": dt.datetime.utcnow().isoformat() + "Z"}
            try:
                PRICES_PATH.write_text(json.dumps(out))
            except Exception:
                pass
            if n_live == 0 and time.time() - last_warn > 600:
                last_warn = time.time()
                logger.warning(f"[basket] polygon REST returned no prices "
                               f"(symbols={list(self.symbols.values())}); "
                               f"display falls back to bar closes")
            time.sleep(5)

    # ---------------- dashboard status ----------------
    def _write_status(self):
        try:
            gates_fresh = self.gates.fresh()
            sleeves = []
            for sl in self.sleeves:
                F = self.feats[sl.instr]
                exo = sl.cfg.get("exo", "none")
                gate_open = self.gates.ok(exo)
                if sl.pos != 0:
                    state = "long" if sl.pos > 0 else "short"
                elif sl.pending:
                    state = "armed"
                elif not gate_open:
                    state = "gated"
                else:
                    state = "watching"
                d = {"i": sl.idx, "instr": sl.instr, "fam": sl.cfg["fam"],
                     "desc": sl.describe(), "exo": exo, "gate_open": gate_open,
                     "state": state,
                     "prox": sl.proximity(F) if F.ready() else 0}
                if sl.pos != 0:
                    d.update(entry_px=sl.entry_px, stop=sl.stop, tgt=sl.tgt,
                             bars_held=getattr(sl, "bars_held", 0),
                             max_bars=sl.cfg["H"])
                if sl.pending:
                    d.update(limit_px=sl.pending["px"],
                             limit_side="long" if sl.pending["side"] > 0 else "short",
                             ttl=sl.pending["ttl"])
                sleeves.append(d)
            status = {
                "ts": dt.datetime.utcnow().isoformat() + "Z",
                "units": UNITS,
                "day": self.state.get("day"),
                "day_pnl": round(self.state.get("day_pnl", 0.0), 2),
                "cum_pnl": round(self.state.get("cum_pnl", 0.0), 2),
                "halted_today": self.halted_today,
                "killed": KILL_FLAG.exists(),
                "gates": {"fresh": gates_fresh, **{k: self.d_gate(k) for k in
                          ("vix", "vix_med", "aaii_bb", "naaim", "naaim_med")}},
                "symbols": self.symbols,
                "pv": PV,
                "sleeves": sleeves,
            }
            STATUS_PATH.write_text(json.dumps(status))
        except Exception as e:
            logger.debug(f"[basket] status write: {e!r}")

    def d_gate(self, k):
        try:
            return self.gates.d.get(k)
        except Exception:
            return None

    # ---------------- gates (self-updating, no committed files) --------
    def _update_gates_daily(self):
        """Write today's gates_daily.json from a LIVE VIX fetch plus
        carried sentiment values. Runs on the host, so no git-shipped
        data file is needed. If the VIX fetch fails and the carried
        value is >3 days old, the vix keys are omitted — Gates.ok()
        then returns False for vix-gated sleeves (per-signal safe-OFF)
        while sentiment-gated sleeves keep working."""
        today = dt.date.today().isoformat()
        prev = _load_json(GATES_PATH, {})
        if prev.get("date") == today:
            return
        rec = {"date": today,
               "vix_med": prev.get("vix_med", GATE_DEFAULTS["vix_med"]),
               "aaii_bb": prev.get("aaii_bb", GATE_DEFAULTS["aaii_bb"]),
               "naaim": prev.get("naaim", GATE_DEFAULTS["naaim"]),
               "naaim_med": prev.get("naaim_med", GATE_DEFAULTS["naaim_med"])}
        vix, src = _fetch_vix()
        if vix is not None:
            rec["vix"] = vix
            rec["vix_src"] = src
        else:
            try:
                age = (dt.date.today()
                       - dt.date.fromisoformat(prev["date"])).days
                if "vix" in prev and age <= 3:
                    rec["vix"] = prev["vix"]
                    rec["vix_src"] = f"carry({prev.get('vix_src')})"
            except Exception:
                pass
            if "vix" not in rec:
                logger.warning("[basket] VIX fetch failed, no recent carry "
                               "— vix-gated sleeves OFF today (safe)")
        try:
            GATES_PATH.write_text(json.dumps(rec, indent=1))
            logger.info(f"[basket] gates for {today}: "
                        f"vix={rec.get('vix')}({rec.get('vix_src')}) "
                        f"aaii={rec['aaii_bb']} naaim={rec['naaim']}")
        except Exception as e:
            logger.error(f"[basket] gates write failed: {e!r}")

    # ---------------- risk rails ----------------
    def _roll_day(self):
        today = dt.date.today().isoformat()
        if self.state.get("day") != today:
            self.state["day"] = today
            self.state["day_pnl"] = 0.0
            self.halted_today = False
            self._update_gates_daily()
            self.gates.load()
            cmap = self.cfg.get("contracts", {})
            self.symbols = {r: front_symbol(cmap.get(r, r)) for r in self.roots}
            logger.info(f"[basket] new day {today} symbols={self.symbols}")
        self._save()

    def _save(self):
        try:
            STATE_PATH.write_text(json.dumps(self.state))
        except Exception:
            pass

    def record_fill_pnl(self, pnl):
        self.state["day_pnl"] += pnl
        self.state["cum_pnl"] += pnl
        self._save()
        if self.state["cum_pnl"] <= -2000 * UNITS:
            KILL_FLAG.write_text(dt.datetime.utcnow().isoformat())
            self.flatten_all("KILL-SWITCH")
            logger.error("[basket] KILL-SWITCH tripped: cumulative <= -$2000. HALTED.")
        elif self.state["day_pnl"] <= -1000 * UNITS:
            self.flatten_all("DAILY-BREAKER")
            self.halted_today = True
            logger.warning("[basket] daily breaker tripped: day <= -$1000. Halted for today.")

    def flatten_all(self, why):
        for sl in self.sleeves:
            if sl.pos != 0:
                self._exit(sl, px=None, why=why)

    # ---------------- trade mechanics ----------------
    def _enter(self, sl: Sleeve, side: int, a: float):
        c = self.feats[sl.instr].last()["c"]
        tick = TICKS[sl.instr]
        if sl.cfg.get("limit"):
            sl.pending = dict(px=c - 0.5 * a * side, side=side, ttl=3, atr=a)
            return
        self.market(sl.instr, "Buy" if side > 0 else "Sell", UNITS, f"s{sl.idx}-entry")
        sl.pos = side
        sl.entry_px = c + tick * side           # conservative book-keeping (1 tick slip)
        sl.entry_bar_ts = self.feats[sl.instr].last()["ts"]
        sl.tgt = sl.entry_px + sl.cfg["tgtA"] * a * side if sl.cfg.get("tgtA") else None
        sl.stop = sl.entry_px - sl.cfg["stopA"] * a * side if sl.cfg.get("stopA") else None
        sl.bars_held = 0

    def _exit(self, sl: Sleeve, px, why):
        side = "Sell" if sl.pos > 0 else "Buy"
        self.market(sl.instr, side, UNITS, f"s{sl.idx}-{why}")
        tick = TICKS[sl.instr]
        c = px if px is not None else self.feats[sl.instr].last()["c"]
        fill = c - tick * sl.pos
        pnl = (fill - sl.entry_px) * sl.pos * PV[sl.instr] * UNITS - 1.54
        logger.info(f"[basket] EXIT s{sl.idx} {sl.instr} {why} pnl≈{pnl:+.0f}")
        sl.pos = 0; sl.pending = None
        self.record_fill_pnl(pnl)

    def on_new_bar(self, root):
        F = self.feats[root]
        if not F.ready():
            return
        now_h = dt.datetime.utcnow().hour + dt.datetime.utcnow().minute / 60
        bar = F.last()
        for sl in self.sleeves:
            if sl.instr != root:
                continue
            # ---- manage open position ----
            if sl.pos != 0:
                sl.bars_held += 1
                hit_stop = sl.stop is not None and (
                    bar["l"] <= sl.stop if sl.pos > 0 else bar["h"] >= sl.stop)
                hit_tgt = sl.tgt is not None and (
                    bar["h"] >= sl.tgt if sl.pos > 0 else bar["l"] <= sl.tgt)
                if hit_stop:                      # stop priority, like the backtest
                    self._exit(sl, sl.stop, "stop")
                elif hit_tgt:
                    self._exit(sl, sl.tgt, "target")
                elif sl.bars_held >= sl.cfg["H"] or now_h >= EOD_UTC:
                    self._exit(sl, None, "time" if sl.bars_held >= sl.cfg["H"] else "eod")
                continue
            # ---- pending limit entries ----
            if sl.pending:
                p = sl.pending
                touched_through = (bar["l"] < p["px"] if p["side"] > 0
                                   else bar["h"] > p["px"])
                if touched_through:
                    self.market(root, "Buy" if p["side"] > 0 else "Sell", UNITS,
                                f"s{sl.idx}-limfill")
                    sl.pos = p["side"]; sl.entry_px = p["px"]
                    sl.entry_bar_ts = bar["ts"]; sl.bars_held = 0
                    a = p["atr"]
                    sl.tgt = sl.entry_px + sl.cfg["tgtA"]*a*sl.pos if sl.cfg.get("tgtA") else None
                    sl.stop = sl.entry_px - sl.cfg["stopA"]*a*sl.pos if sl.cfg.get("stopA") else None
                    sl.pending = None
                else:
                    p["ttl"] -= 1
                    if p["ttl"] <= 0:
                        sl.pending = None
                continue
            # ---- new entries ----
            if self.halted_today or KILL_FLAG.exists() or now_h >= EOD_UTC - 0.5:
                continue
            lo, hi = SESS[sl.cfg.get("sess", "us")]
            if not (lo <= now_h < hi):
                continue
            if not self.gates.ok(sl.cfg.get("exo", "none")):
                continue
            side, a = sl.signal(F)
            if side != 0:
                self._enter(sl, side, a)

    # ---------------- main loop ----------------
    def run(self):
        self._ensure_demo()
        logger.info(f"[basket] starting: {len(self.sleeves)} sleeves on {self.roots} "
                    f"UNITS={UNITS} (DEMO) data_dir={DATA}")
        self._update_gates_daily()
        self._roll_day()
        self.gates.load()
        threading.Thread(target=self._price_loop, name="basket-prices",
                         daemon=True).start()
        while True:
            try:
                self._roll_day()
                if KILL_FLAG.exists():
                    self._write_status()
                    time.sleep(300); continue
                for root in self.roots:
                    try:
                        if self.feats[root].update(self.bars_for(root)):
                            self.on_new_bar(root)
                    except Exception as e:
                        logger.warning(f"[basket] {root} poll error: {e}")
                self._write_status()
            except Exception as e:
                logger.error(f"[basket] loop error: {e}")
            time.sleep(POLL_S)


def start_in_thread():
    eng = BasketEngine()
    t = threading.Thread(target=eng.run, name="basket-engine", daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    BasketEngine().run()
