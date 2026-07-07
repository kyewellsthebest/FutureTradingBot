"""Round 11: VOLUME/TICK microstructure — the untouched data dimension.
Builds per-minute volume features from 280M raw ticks (2.5y), then runs
a family battery on them. Band focus: 100-300 trades/wk, one strategy.
Same honest fills + select/blind protocol."""
import os, time
import numpy as np, pandas as pd
import pyarrow.parquet as pq
from multiprocessing import Pool
from research.midfreq_search import load_bars
from research.midfreq_round4 import metrics_split, run_exit_ts

FEAT = "data/tick/minute_volfeat.parquet"
WEEKS = 156.1

def build_features():
    if os.path.exists(FEAT):
        return pd.read_parquet(FEAT)
    import glob as _g
    files = sorted(_g.glob("data/tick/raw/NQ*.parquet"))
    parts = []
    rgs = [(f, i) for f in files for i in range(pq.ParquetFile(f).num_row_groups)]
    for n, (f, i) in enumerate(rgs):
        t = pq.ParquetFile(f).read_row_group(i, columns=["ts","price","size"]).to_pandas()
        dt = pd.to_datetime(t["ts"], utc=True)
        m = dt.dt.floor("1min")
        px = t["price"].to_numpy(); sz = t["size"].to_numpy()
        d = np.sign(np.diff(px, prepend=px[0]))
        big = sz >= 10
        g = pd.DataFrame({"m": m, "vol": sz, "nt": 1,
                          "imb": d*sz, "bigv": np.where(big, d*sz, 0)})
        parts.append(g.groupby("m").sum())
        if n % 40 == 0: print(f"rg {n}/{len(rgs)}", flush=True)
    f = pd.concat(parts).groupby(level=0).sum()
    f.to_parquet(FEAT)
    return f

def run_family(args):
    fname, rl, rs_, arrs = args
    o,h,l,c,atr,ts,years,idx,rth=(arrs[k] for k in ('o','h','l','c','atr','ts','years','idx','rth'))
    out=[]
    for mode,p1s in (("time",(5,15,40)),("trail",(2.0,))):
        for p1 in p1s:
            for sess,mask in (("all",np.ones(len(c),bool)),("rth",rth)):
                sig=np.where(np.nan_to_num(rl)&mask,1,np.where(np.nan_to_num(rs_)&mask,-1,0))
                ys,ps,tss=run_exit_ts(o,h,l,c,atr,ts,years,sig,mode,p1,0,120)
                m=metrics_split(idx,ys,ps,tss)
                if m:
                    net=round((m['sel_total']+m['blind_total'])/WEEKS,1)
                    fees=round(m['trades_wk']*1.96,1)
                    out.append({"name":f"{fname}_{mode}{p1}_{sess}",
                                "net_wk":net,"fees_wk":fees,"gross_wk":round(net+fees,1),**m})
    return out

def main():
    t0=time.time()
    feats = build_features()
    print(f"features: {len(feats):,} minutes ({time.time()-t0:.0f}s)", flush=True)
    bars = load_bars()
    df = bars.join(feats, how="left").fillna({"vol":0,"nt":0,"imb":0,"bigv":0})
    o=df["open"].to_numpy(); h=df["high"].to_numpy(); l=df["low"].to_numpy(); c=df["close"].to_numpy()
    idx=df.index; hrs=np.asarray(idx.hour)+np.asarray(idx.minute)/60.0
    cs=pd.Series(c,index=idx)
    tr=np.maximum(h-l,np.abs(c-np.roll(c,1))); atr=pd.Series(tr).rolling(20).mean().to_numpy()
    rth=(hrs>=13.5)&(hrs<20.9)
    vol=df["vol"].to_numpy(float); nt=df["nt"].to_numpy(float)
    imb=df["imb"].to_numpy(float); bigv=df["bigv"].to_numpy(float)
    vma=pd.Series(vol).rolling(30).mean().to_numpy()
    ima=pd.Series(imb).rolling(10).sum().to_numpy()
    bma=pd.Series(bigv).rolling(10).sum().to_numpy()
    ntma=pd.Series(nt).rolling(30).mean().to_numpy()
    obv=pd.Series(np.where(c>np.roll(c,1),vol,np.where(c<np.roll(c,1),-vol,0))).cumsum()
    obvsl=(obv-obv.shift(15)).to_numpy()
    up=(c-np.roll(c,1))>0; dn=(c-np.roll(c,1))<0
    hi30=pd.Series(h).rolling(30).max().shift(1).to_numpy(); lo30=pd.Series(l).rolling(30).min().shift(1).to_numpy()
    vspk=vol>3*np.where(vma>0,vma,np.inf)
    dry=vol<0.4*np.where(vma>0,vma,0)
    F={}
    F['VSPKF']=(vspk&up, vspk&dn)                      # volume spike follow
    F['VSPKR']=(vspk&dn, vspk&up)                      # spike reversal
    F['IMBF']=(ima>3*np.nan_to_num(vma,nan=1e18), ima<-3*np.nan_to_num(vma,nan=1e18))
    F['IMBR']=(ima<-3*np.nan_to_num(vma,nan=1e18), ima>3*np.nan_to_num(vma,nan=1e18))
    F['BIGF']=(bma>1.5*np.nan_to_num(vma,nan=1e18), bma<-1.5*np.nan_to_num(vma,nan=1e18))
    F['BIGR']=(bma<-1.5*np.nan_to_num(vma,nan=1e18), bma>1.5*np.nan_to_num(vma,nan=1e18))
    F['OBVT']=((obvsl>0)&(c>hi30), (obvsl<0)&(c<lo30))
    F['OBVD']=((obvsl>0)&(c<lo30), (obvsl<0)&(c>hi30))  # divergence
    F['DRYBO']=(np.roll(dry,1)&(c>np.roll(h,1)), np.roll(dry,1)&(c<np.roll(l,1)))
    F['BURST']=((nt>3*np.nan_to_num(ntma,nan=1e18))&up, (nt>3*np.nan_to_num(ntma,nan=1e18))&dn)
    F['VATEX']=(vspk&(l<=lo30)&up, vspk&(h>=hi30)&dn)   # volume at extreme reversal
    F['VCONF']=((c>hi30)&(vol>1.5*np.nan_to_num(vma,nan=1e18)), (c<lo30)&(vol>1.5*np.nan_to_num(vma,nan=1e18)))
    F['VREJ']=((c>hi30)&dry, (c<lo30)&dry)              # breakout w/o volume -> fade next
    arrs=dict(o=o,h=h,l=l,c=c,atr=atr,ts=idx.asi8,years=idx.year.to_numpy(),idx=idx,rth=rth)
    jobs=[(fn,rl,rs_,arrs) for fn,(rl,rs_) in F.items()]
    with Pool(5) as pool: res=pool.map(run_family, jobs)
    rows=[r for s in res for r in s]
    out=pd.DataFrame(rows); out.to_csv("research/round11_results.csv", index=False)
    print(f"\nALL {len(out)} configs ({time.time()-t0:.0f}s)")
    band=out[(out.trades_wk>=100)&(out.trades_wk<=300)]
    ok=band[(band.sel_total>0)&(band.blind_usd_wk>0)].sort_values("net_wk",ascending=False)
    cols=["name","gross_wk","fees_wk","net_wk","trades_wk","win_pct"]
    print(f"\nIN-BAND 100-300tr/wk: {len(band)} | QUALIFIERS: {len(ok)}")
    print(ok[cols].head(15).to_string(index=False) if len(ok) else "(none)")
    print("\nBand frontier:")
    print(band.sort_values("net_wk",ascending=False)[cols].head(12).to_string(index=False))
    lowf=out[(out.sel_total>0)&(out.blind_usd_wk>0)&(out.trades_wk<100)].sort_values("net_wk",ascending=False)
    print(f"\nlow-freq both-positive: {len(lowf)}")
    print(lowf[cols+['blind_usd_wk']].head(8).to_string(index=False))

if __name__ == "__main__":
    main()
