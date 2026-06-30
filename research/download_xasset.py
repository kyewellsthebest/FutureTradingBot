"""Download cross-asset history that leads NQ via the POLYGON FUTURES API
(/futures/v1/aggs) — the same family as the NQ trades download. ES (S&P) and
GC (gold) front-month-stitched at 1-SECOND resolution; ZB (bonds) attempted
(may be unentitled); VIX index via /v2 (indices; may be unentitled).

1-second is the finest retail-EXECUTABLE resolution and a superset of slower
bars; it completes within a temp key's life, unlike a full tick pull.

GitHub Actions matrix mode: set env PRODUCT=ES (or ZB/GC/VIX).
  -> writes data/xasset/<PRODUCT>_1s.parquet  (VIX -> _1m)
Needs POLYGON_API.
"""
import json,os,sys,time,urllib.request,urllib.error
from datetime import date,timedelta
from pathlib import Path
import pandas as pd
KEY=os.environ.get("POLYGON_API")
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/"data"/"xasset"; OUT.mkdir(parents=True,exist_ok=True)
HISTORY_DAYS=1010
MONTH_CODE={3:"H",6:"M",9:"U",12:"Z"}      # quarterly for ES/ZB
GC_MONTHS={2:"G",4:"J",6:"M",8:"Q",10:"V",12:"Z"}  # gold actives
NS=1_000_000_000
def third_fri(y,m):
    d=date(y,m,1); return date(y,m,1+((4-d.weekday())%7)+14)
def get(u,tries=8):
    for a in range(tries):
        try:
            r=urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"x/1"}),timeout=120)
            return json.loads(r.read().decode()),None
        except urllib.error.HTTPError as e:
            if e.code==429: time.sleep(min(90,2**a*3)); continue
            try:b=json.loads(e.read().decode())
            except:b={}
            return None,f"HTTP {e.code}: {b.get('message') or b.get('error')}"
        except Exception as e:
            if a<tries-1: time.sleep(4); continue
            return None,f"{type(e).__name__}:{e}"
    return None,"exhausted"
def _norm_ts(t):
    t=int(t)   # normalize s/ms/us -> ns
    if t<2*10**9:  return t*1_000_000_000
    if t<2*10**12: return t*1_000_000
    if t<2*10**15: return t*1_000
    return t
def _row(r):
    ts=r.get("window_start") or r.get("timestamp") or r.get("t") or r.get("start_timestamp")
    o=r.get("open",r.get("o")); h=r.get("high",r.get("h")); l=r.get("low",r.get("l"))
    c=r.get("close",r.get("c")); v=r.get("volume",r.get("v",0))
    if ts is None or c is None: return None
    return (_norm_ts(ts),float(o),float(h),float(l),float(c),float(v or 0))
def futures_aggs(ticker,s_ns,e_ns,resolution="1_second"):
    """Paginated 1-second aggs from the FUTURES endpoint for one contract window."""
    rows=[]; dbg=True
    url=(f"https://api.polygon.io/futures/v1/aggs/{ticker}"
         f"?resolution={resolution}&timestamp.gte={s_ns}&timestamp.lt={e_ns}"
         f"&order=asc&limit=50000&apiKey={KEY}")
    while url:
        d,err=get(url)
        if err: print(f"  {ticker}: {err}",flush=True); break
        res=d.get("results") or []
        if dbg and res:
            print(f"  {ticker}: sample fields {list(res[0].keys())}",flush=True); dbg=False
        for r in res:
            row=_row(r)
            if row: rows.append(row)
        nx=d.get("next_url"); url=(nx+f"&apiKey={KEY}") if nx else None
    return rows
def v2_aggs(ticker,s,e,span="minute"):
    rows=[]; url=(f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/{span}/"
                 f"{s}/{e}?adjusted=true&sort=asc&limit=50000&apiKey={KEY}")
    while url:
        d,err=get(url)
        if err: print(f"  {ticker}: {err}",flush=True); break
        for r in (d.get("results") or []):
            rows.append((_norm_ts(r["t"]),float(r["o"]),float(r["h"]),float(r["l"]),float(r["c"]),float(r.get("v",0))))
        nx=d.get("next_url"); url=(nx+f"&apiKey={KEY}") if nx else None
    return rows
def futures_tickers(product,months):
    today=date.today(); start=today-timedelta(days=HISTORY_DAYS+120); end=today+timedelta(days=10)
    out=[]
    for y in range(start.year,end.year+1):
        for m,code in months.items():
            exp=third_fri(y,m)
            if start<=exp<=end: out.append((f"{product}{code}{y%10}",exp))
    out.sort(key=lambda t:t[1]); return out
def download_futures(product,months):
    tks=futures_tickers(product,months); parts=[]; prev=None
    for tk,exp in tks:
        s0=(prev or (exp-timedelta(days=130))); e=exp; prev=exp
        s_ns=int(time.mktime(s0.timetuple()))*NS; e_ns=int(time.mktime(e.timetuple()))*NS
        rows=futures_aggs(tk,s_ns,e_ns)
        print(f"{tk}: {s0}->{e}  {len(rows):,} bars",flush=True)
        if rows:
            df=pd.DataFrame(rows,columns=["ts","open","high","low","close","vol"])
            df=df[(df.ts>=s_ns)&(df.ts<e_ns)]; parts.append(df)
    if not parts: print("no data"); return
    full=pd.concat(parts).sort_values("ts"); full=full[~full.ts.duplicated(keep="last")]
    f=OUT/f"{product}_1s.parquet"; full.to_parquet(f,compression="zstd",index=False)
    print(f"{product}: {len(full):,} bars -> {f}",flush=True)
def download_index(name,ticker):
    today=date.today(); start=today-timedelta(days=HISTORY_DAYS); rows=[]; cur=start
    while cur<today:
        nxt=min(cur+timedelta(days=120),today)
        rows+=v2_aggs(ticker,cur.isoformat(),nxt.isoformat(),"minute"); cur=nxt
    if not rows: print("no data"); return
    df=pd.DataFrame(rows,columns=["ts","open","high","low","close","vol"]).sort_values("ts")
    df=df[~df.ts.duplicated(keep="last")]
    f=OUT/f"{name}_1m.parquet"; df.to_parquet(f,compression="zstd",index=False)
    print(f"{name}: {len(df):,} bars -> {f}",flush=True)
def main():
    if not KEY: print("NO POLYGON KEY"); sys.exit(1)
    p=os.environ.get("PRODUCT","ES").strip()
    if p=="ES": download_futures("ES",MONTH_CODE)
    elif p=="ZB": download_futures("ZB",MONTH_CODE)
    elif p=="GC": download_futures("GC",GC_MONTHS)
    elif p=="VIX": download_index("VIX","I:VIX")
    else: print(f"unknown PRODUCT {p}")
if __name__=="__main__": main()
