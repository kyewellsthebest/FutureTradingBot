#!/usr/bin/env python3
"""Daily gates file for the basket engine: data/gates_daily.json.
VIX: live via yfinance (fallback: last value in macro_features).
AAII/NAAIM: carried forward from repo weekly datasets (they update slowly).
Medians computed over full history so gate thresholds match the research.
Run daily (gex-daily workflow). Engine treats a stale file as SAFE-OFF for
gated sleeves, so a failed run never causes wrong trades - only fewer.
"""
import json, datetime as dt
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "gates_daily.json"

mac = pd.read_csv(ROOT / "data" / "macro_features.csv.gz")
vix_med = float(mac["vix"].median())
vix = float(mac["vix"].dropna().iloc[-1]); vix_src = "macro_csv(carry)"
try:
    import yfinance as yf
    v = yf.Ticker("^VIX").history(period="5d")["Close"].dropna()
    if len(v):
        vix = float(v.iloc[-1]); vix_src = "yfinance"
except Exception:
    pass

aa = pd.read_csv(ROOT / "data" / "aaii_features.csv.gz")
aaii_bb = float(aa["bull_bear"].dropna().iloc[-1])
na = pd.read_csv(ROOT / "data" / "naaim_features.csv.gz")
naaim = float(na["naaim"].dropna().iloc[-1])
naaim_med = float(na["naaim"].median())

rec = dict(date=dt.date.today().isoformat(), vix=vix, vix_med=vix_med,
           vix_src=vix_src, aaii_bb=aaii_bb, naaim=naaim, naaim_med=naaim_med)
OUT.write_text(json.dumps(rec, indent=1))
print(json.dumps(rec))
