"""PRODUCTION daily dealer-GEX regime pipeline (separate, validation-gated project).

Reads ONE daily QQQ option-chain snapshot (OPT_QQQ_YYYYMMDD.parquet from
tools/fetch_options_chain.py, which carries REAL open-interest + Polygon greeks),
computes net dealer GEX, classifies the regime, and appends an auditable record
to data/gex_daily_log.jsonl.

Design rules (per the agreed validation criteria):
  * SAFE STATE FIRST: any missing/partial/bad input -> regime "UNKNOWN" is logged
    and load_today_regime() returns UNKNOWN, which the engine MUST treat as
    "no new trades". We never guess a regime.
  * FULLY LOGGED: every run writes exactly what the engine will believe, with the
    raw GEX value, contract counts, and validity flags, before the session opens.
  * REPEATABLE: pure function of the snapshot file -> re-running reproduces the
    same classification (criterion #2).

GEX convention (matches research/gex_calculator.py):
  contrib = gamma * open_interest * 100 * spot^2 * (+1 call / -1 put)
Regime is SIGN-based (the sleeves gated on sign of net gamma) with a small
neutral deadband; the band is configurable and logged so it can be tuned during
paper validation without changing history.
"""
from __future__ import annotations
import json, os, sys, glob, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LOG = DATA / "gex_daily_log.jsonl"
MIN_VALID_STRIKES = 20          # too few contracts -> bad fetch -> UNKNOWN
MIN_ABS_GEX = 1e6               # implausibly small -> bad fetch -> UNKNOWN
NEUTRAL_BAND = float(os.environ.get("GEX_NEUTRAL_BAND", "0"))  # 0 => pure sign
STALE_HOURS = 30                # regime older than this -> UNKNOWN (safe)


def compute_from_snapshot(path: str) -> dict:
    """Pure, repeatable classification from one snapshot file. Never raises."""
    rec = {"date": None, "as_of": _now(), "regime": "UNKNOWN",
           "total_gex": None, "n_contracts": 0, "n_valid": 0, "spot": None,
           "source": os.path.basename(path) if path else None, "ok": False,
           "reason": ""}
    try:
        import pandas as pd
        df = pd.read_parquet(path)
    except Exception as e:
        rec["reason"] = f"read-failed:{e}"; return rec
    rec["n_contracts"] = int(len(df))
    try:
        g = df["gamma"].astype(float)
        oi = df["open_interest"].astype(float)
        strike = df["strike"].astype(float)
        typ = df["type"].astype(str).str.lower()
        spot = df["underlying"].astype(float)
        spot_val = float(spot.dropna().median()) if spot.notna().any() else None
        rec["spot"] = spot_val
        valid = g.notna() & oi.notna() & (oi > 0) & strike.notna()
        rec["n_valid"] = int(valid.sum())
        if spot_val is None or rec["n_valid"] < MIN_VALID_STRIKES:
            rec["reason"] = f"insufficient-valid-contracts:{rec['n_valid']}"; return rec
        sign = typ.map(lambda t: 1.0 if t.startswith("c") else -1.0)
        contrib = (g * oi * 100.0 * spot_val * spot_val * sign)[valid]
        total = float(contrib.sum())
        rec["total_gex"] = total
        if abs(total) < MIN_ABS_GEX:
            rec["reason"] = f"gex-too-small:{total:.0f}"; return rec
        if total > NEUTRAL_BAND:
            rec["regime"] = "POSITIVE"
        elif total < -NEUTRAL_BAND:
            rec["regime"] = "NEGATIVE"
        else:
            rec["regime"] = "NEUTRAL"
        # date from filename OPT_QQQ_YYYYMMDD.parquet if present
        base = rec["source"] or ""
        digits = "".join(ch for ch in base if ch.isdigit())[:8]
        rec["date"] = f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}" if len(digits) == 8 else _today()
        rec["ok"] = True
        rec["reason"] = "ok"
    except Exception as e:
        rec["reason"] = f"compute-failed:{e}"
    return rec


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()

def _today() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def append_log(rec: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")


def load_today_regime() -> str:
    """What the ENGINE calls. Returns POSITIVE/NEGATIVE/NEUTRAL, or UNKNOWN if the
    latest record is missing, not ok, or stale. UNKNOWN => engine takes no new trades."""
    if not LOG.exists():
        return "UNKNOWN"
    try:
        last = None
        for line in open(LOG):
            line = line.strip()
            if line:
                last = json.loads(line)
        if not last or not last.get("ok"):
            return "UNKNOWN"
        age_h = (dt.datetime.now(dt.timezone.utc)
                 - dt.datetime.fromisoformat(last["as_of"])).total_seconds() / 3600.0
        if age_h > STALE_HOURS:
            return "UNKNOWN"
        return last.get("regime", "UNKNOWN")
    except Exception:
        return "UNKNOWN"


def main():
    # find today's snapshot (arg, or newest OPT_QQQ_*.parquet in cwd/data)
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        cands = sorted(glob.glob("OPT_QQQ_*.parquet")
                       + glob.glob(str(DATA / "OPT_QQQ_*.parquet")))
        path = cands[-1] if cands else ""
    rec = compute_from_snapshot(path) if path else {
        "date": _today(), "as_of": _now(), "regime": "UNKNOWN", "total_gex": None,
        "n_contracts": 0, "n_valid": 0, "spot": None, "source": None,
        "ok": False, "reason": "no-snapshot-file"}
    append_log(rec)
    print(json.dumps(rec))
    # exit 0 even on UNKNOWN: safe state is a valid, logged outcome (not a crash)


if __name__ == "__main__":
    main()
