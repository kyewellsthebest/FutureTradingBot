"""Round 8: retests, extremes, seasonality, multi-day ranges."""
import numpy as np, pandas as pd
from research.midfreq_search import load_bars, resample
from research.midfreq_round4 import metrics_split, run_exit_ts

def main():
    base = load_bars()
    rows = []
    d_high = base["high"].resample("1D").max().dropna()
    d_low = base["low"].resample("1D").min().dropna()
    r3h = d_high.rolling(3).max().shift(1); r3l = d_low.rolling(3).min().shift(1)

    for tf in ("3min", "5min", "15min"):
        df = resample(base, tf)
        o=df["open"].to_numpy(); h=df["high"].to_numpy(); l=df["low"].to_numpy(); c=df["close"].to_numpy()
        idx=df.index; ts=idx.asi8; hrs=np.asarray(idx.hour)+np.asarray(idx.minute)/60.0
        years=idx.year.to_numpy(); dk=idx.normalize(); dow=np.asarray(idx.dayofweek)
        cs=pd.Series(c,index=idx)
        tr=np.maximum(h-l,np.abs(c-np.roll(c,1))); atr=pd.Series(tr).rolling(20).mean().to_numpy()
        rth=(hrs>=13.5)&(hrs<20.9)
        ph=dk.map(d_high.shift(1)).to_numpy(float)
        h3=dk.map(r3h).to_numpy(float); l3=dk.map(r3l).to_numpy(float)

        fams={}
        # RETEST: broke prior-day high earlier today, now back at it holding
        broke = pd.Series((c>ph),index=idx).groupby(dk).cummax().to_numpy()
        fams["RETEST"]=(broke&(l<=ph)&(c>ph), np.zeros(len(c),bool))
        # SPIKEF: vertical spike fade (3-bar move > 4*ATR)
        mom3=cs.diff(3).to_numpy()
        fams["SPIKEF"]=((mom3<=-4*np.nan_to_num(atr,nan=1e9)), (mom3>=4*np.nan_to_num(atr,nan=1e9)))
        # R3BO: 3-day range breakout
        fams["R3BO"]=(c>h3, c<l3)
        # ENGULF at 20-bar extreme
        lo20=pd.Series(l).rolling(20).min().shift(1).to_numpy()
        hi20=pd.Series(h).rolling(20).max().shift(1).to_numpy()
        bull=(c>o)&(np.roll(c,1)<np.roll(o,1))&(c>np.roll(o,1))&(o<np.roll(c,1))
        bear=(c<o)&(np.roll(c,1)>np.roll(o,1))&(c<np.roll(o,1))&(o>np.roll(c,1))
        fams["ENGX"]=(bull&(np.roll(l,1)<=lo20), bear&(np.roll(h,1)>=hi20))
        # DOWSEAS: Mon/Fri afternoon momentum
        pm=(hrs>=17.0)&(hrs<17.25)
        opn=pd.Series(np.where((hrs>=13.5)&(hrs<13.6),o,np.nan),index=idx).groupby(dk).transform("max").to_numpy()
        dm=c-opn
        fams["SEASMF"]=(pm&(dm>15)&((dow==0)|(dow==4)), pm&(dm<-15)&((dow==0)|(dow==4)))

        for fname,(rl,rs_) in fams.items():
            for mode,p1s in (("time",(20,60,120)),("trail",(2.0,3.5))):
                for p1 in p1s:
                    for p2 in (0,12):
                        for sess,mask in (("all",np.ones(len(c),bool)),("rth",rth)):
                            sig=np.where(np.nan_to_num(rl)&mask,1,np.where(np.nan_to_num(rs_)&mask,-1,0))
                            ys,ps,tss=run_exit_ts(o,h,l,c,atr,ts,years,sig,mode,p1,p2,260)
                            m=metrics_split(idx,ys,ps,tss)
                            if m: rows.append({"name":f"{fname}_{tf}_{mode}{p1}h{p2}_{sess}",
                                               "family":fname,"tf":tf,**m})
        print(f"[{tf}] cum={len(rows)}", flush=True)

    df=pd.DataFrame(rows); df.to_csv("research/midfreq_results8.csv", index=False)
    sel=df[df.sel_total>0].sort_values("sel_usd_wk",ascending=False)
    both=sel[sel.blind_usd_wk>0]
    cols=["name","sel_usd_wk","blind_usd_wk","trades_wk","win_pct"]
    print(f"\npositive BOTH windows: {len(both)}; top 15:")
    print(both[cols].head(15).to_string(index=False))

if __name__ == "__main__":
    main()
