"""Download 1-MINUTE aggregates for cross-asset instruments that lead NQ:
ES (S&P), ZB (30y bonds), GC (gold) as front-month-stitched futures, and the
VIX index. Minute scale = retail-tradeable (avoids the HFT fill wall).

GitHub Actions matrix mode: set env PRODUCT=ES (or ZB/GC/VIX).
  -> writes data/xasset/<PRODUCT>_1m.parquet
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
            r=urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"x/1"}),timeout=90)
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
def agg_range(ticker,s,e,span="minute"):
    """aggs for [s,e] dates via the v2 range endpoint, paginated. span=second|minute."""
    rows=[]; url=(f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/{span}/"
                 f"{s}/{e}?adjusted=true&sort=asc&limit=50000&apiKey={KEY}")
    while url:
        d,err=get(url)
        if err: print(f"  {ticker}: {err}",flush=True); break
        for r in (d.get("results") or []):
            rows.append((int(r["t"])*1_000_000, float(r["o"]),float(r["h"]),float(r["l"]),float(r["c"]),float(r.get("v",0))))
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
def download_futures(product,months,span="second"):
    tks=futures_tickers(product,months); parts=[]; prev=None
    for i,(tk,exp) in enumerate(tks):
        s0=(prev or (exp-timedelta(days=130))); e=exp; prev=exp
        # page in <=10-day chunks so 1-second pulls stay reliable
        cur=s0; rows=[]
        while cur<e:
            nxt=min(cur+timedelta(days=10),e)
            rows+=agg_range(tk,cur.isoformat(),nxt.isoformat(),span); cur=nxt
        print(f"{tk}: {s0}->{e}  {len(rows):,} bars",flush=True)
        if rows:
            df=pd.DataFrame(rows,columns=["ts","open","high","low","close","vol"])
            df=df[(pd.to_datetime(df.ts)>=pd.Timestamp(s0))&(pd.to_datetime(df.ts)<pd.Timestamp(e))]
            parts.append(df)
    if not parts: print("no data"); return
    full=pd.concat(parts).sort_values("ts"); full=full[~full.ts.duplicated(keep="last")]
    tag="1s" if span=="second" else "1m"
    f=OUT/f"{product}_{tag}.parquet"; full.to_parquet(f,compression="zstd",index=False)
    print(f"{product}: {len(full):,} bars -> {f}",flush=True)
def download_index(name,ticker):
    today=date.today(); start=today-timedelta(days=HISTORY_DAYS)
    rows=[]; cur=start
    while cur<today:
        nxt=min(cur+timedelta(days=120),today)
        rows+=agg_range(ticker,cur.isoformat(),nxt.isoformat()); cur=nxt
        print(f"  {ticker} {cur}: {len(rows):,}",flush=True)
    if not rows: print("no data"); return
    df=pd.DataFrame(rows,columns=["ts","open","high","low","close","vol"]).sort_values("ts")
    df=df[~df.ts.duplicated(keep="last")]
    f=OUT/f"{name}_1m.parquet"; df.to_parquet(f,compression="zstd",index=False)
    print(f"{name}: {len(df):,} bars -> {f}",flush=True)
def main():
    if not KEY: print("NO POLYGON KEY"); sys.exit(1)
    p=os.environ.get("PRODUCT","ES").strip()
    if p=="ES": download_futures("ES",MONTH_CODE,"second")
    elif p=="ZB": download_futures("ZB",MONTH_CODE,"second")
    elif p=="GC": download_futures("GC",GC_MONTHS,"second")
    elif p=="VIX": download_index("VIX","I:VIX")   # index: 1-minute finest
    else: print(f"unknown PRODUCT {p}")
if __name__=="__main__": main()
