"""Stack NON-OVERLAPPING edges on ONE contract + test new strategy classes.

Key insight: the intraday breakout is FLAT overnight; the overnight drift is
an overnight hold. They never hold simultaneously -> on a single MNQ their
daily P&L ADDS. Also tests genuinely new intraday classes (VWAP reversion,
opening-drive, NR-expansion breakout) held to close.
"""
import numpy as np, pandas as pd, time
import research.tick_zoo_2p5y as Z
from research.avenue_intraday_trend import prep
from research.tick_zoo_2p5y import PT, COMM
SPREAD=0.25; SLIP=0.5; RTH_LO=14.5; RTH_HI=20.92

def daily_pnl(trades):
    if not trades: return pd.Series(dtype=float)
    ts=pd.to_datetime([t[0] for t in trades]); pnl=np.array([t[1] for t in trades])*PT-COMM
    return pd.Series(pnl,index=ts).groupby(pd.Series(ts).dt.normalize().values).sum()

def rep(name,dser):
    if len(dser)==0: print(f"{name}: none"); return
    span=max(1,(dser.index.max()-dser.index.min()).days)
    sh=dser.mean()/dser.std()*np.sqrt(252) if dser.std()>0 else 0
    eq=dser.cumsum(); dd=(eq.cummax()-eq).max()
    yr=dser.groupby(dser.index.year).sum()
    pe="/".join(f"{y}:{v:.0f}" for y,v in yr.items())
    print(f"{name}: \${dser.sum()/ (len(dser)) :.1f}/trading-day  total=\${dser.sum():.0f}  sharpe={sh:.2f}  maxDD=\${dd:.0f}  pos_yrs={(yr>0).sum()}/{len(yr)}  [{pe}]")

# ---- breakout sleeve (RTH, flat by close) ----
def breakout(df,N=8):
    c=df["close"].to_numpy(); h=df["high"].to_numpy(); l=df["low"].to_numpy()
    hr=df["hr"].to_numpy(); day=df["day"].to_numpy(); ts=df.index.to_numpy("datetime64[ns]").astype("int64")
    dhi=pd.Series(h).rolling(N).max().shift(1).to_numpy(); dlo=pd.Series(l).rolling(N).min().shift(1).to_numpy()
    inrth=(hr>=RTH_LO)&(hr<RTH_HI); tr=[]; pos=0; epx=0; cur=None
    for i in range(N+2,len(c)):
        if pos!=0 and (hr[i]>=RTH_HI or day[i]!=cur): tr.append((ts[i],(c[i]-epx)*pos-(SPREAD+SLIP))); pos=0
        if not inrth[i]: continue
        if pos==0:
            sig=1 if (not np.isnan(dhi[i]) and c[i]>dhi[i]) else (-1 if (not np.isnan(dlo[i]) and c[i]<dlo[i]) else 0)
            if sig and cur!=day[i]: pos=sig; epx=c[i]; cur=day[i]
    return tr

# ---- overnight drift sleeve (enter ~21:00, exit next ~14:30) ----
def overnight(df,d=1):
    hr=df["hr"].to_numpy(); day=df["day"].to_numpy(); c=df["close"].to_numpy(); ts=df.index.to_numpy("datetime64[ns]").astype("int64")
    tr=[]; days=np.unique(day)
    for k in range(len(days)-1):
        din=np.where((day==days[k])&(hr>=21.0))[0]
        dout=np.where((day==days[k+1])&(hr>=14.5))[0]
        if len(din) and len(dout):
            e=c[din[0]]; x=c[dout[0]]
            tr.append((ts[dout[0]],(x-e)*d-(SPREAD+SLIP)))
    return tr

# ---- new class: VWAP reversion (fade stretch from session VWAP) ----
def vwap_rev(df,stretch=15.0,d_follow=-1):
    c=df["close"].to_numpy(); hr=df["hr"].to_numpy(); day=df["day"].to_numpy(); ts=df.index.to_numpy("datetime64[ns]").astype("int64")
    inrth=(hr>=RTH_LO)&(hr<RTH_HI); tr=[]; pos=0; epx=0; cur=None
    csum=0.0; cnt=0
    for i in range(len(c)):
        if day[i]!=cur and inrth[i]: csum=0.0; cnt=0; cur=day[i]
        if inrth[i]: csum+=c[i]; cnt+=1; vwap=csum/cnt
        if pos!=0 and (hr[i]>=RTH_HI or day[i]!=cur): tr.append((ts[i],(c[i]-epx)*pos-(SPREAD+SLIP))); pos=0
        if not inrth[i] or cnt<10: continue
        if pos==0:
            dev=c[i]-vwap
            if dev>=stretch: pos=d_follow*1*(-1)  # stretched up -> fade short if d_follow=-1
            elif dev<=-stretch: pos=d_follow*1
            if pos: epx=c[i]
    return tr

# ---- new class: opening-drive (first 30min direction, ride to close) ----
def opening_drive(df):
    o=df["open"].to_numpy(); c=df["close"].to_numpy(); hr=df["hr"].to_numpy(); day=df["day"].to_numpy(); ts=df.index.to_numpy("datetime64[ns]").astype("int64")
    tr=[]; days=np.unique(day)
    for dd in days:
        op=np.where((day==dd)&(hr>=RTH_LO))[0]
        mid=np.where((day==dd)&(hr>=RTH_LO+0.5))[0]
        cl=np.where((day==dd)&(hr<RTH_HI))[0]
        if len(op) and len(mid) and len(cl):
            drive=c[mid[0]]-o[op[0]]
            if abs(drive)<2: continue
            d=1 if drive>0 else -1; e=c[mid[0]]; x=c[cl[-1]]
            tr.append((ts[cl[-1]],(x-e)*d-(SPREAD+SLIP)))
    return tr

# ---- new class: NR-expansion breakout (narrow-range day -> breakout) ----
def nr_expand(df,N=8):
    h=df["high"].to_numpy(); l=df["low"].to_numpy(); c=df["close"].to_numpy(); hr=df["hr"].to_numpy(); day=df["day"].to_numpy(); ts=df.index.to_numpy("datetime64[ns]").astype("int64")
    rng=pd.Series(h-l).rolling(N).mean().to_numpy()
    dhi=pd.Series(h).rolling(N).max().shift(1).to_numpy(); dlo=pd.Series(l).rolling(N).min().shift(1).to_numpy()
    medr=pd.Series(rng).rolling(200).median().to_numpy()
    inrth=(hr>=RTH_LO)&(hr<RTH_HI); tr=[]; pos=0; epx=0; cur=None
    for i in range(200,len(c)):
        if pos!=0 and (hr[i]>=RTH_HI or day[i]!=cur): tr.append((ts[i],(c[i]-epx)*pos-(SPREAD+SLIP))); pos=0
        if not inrth[i] or np.isnan(medr[i]): continue
        if pos==0 and rng[i]<0.7*medr[i]:   # compressed
            sig=1 if (c[i]>dhi[i]) else (-1 if c[i]<dlo[i] else 0)
            if sig and cur!=day[i]: pos=sig; epx=c[i]; cur=day[i]
    return tr

t0=time.time(); Z._init(); bars=Z._BARS
df3=prep(bars,"3min"); df5=prep(bars,"5min")
print(f"prepped {time.time()-t0:.0f}s\n")
bo=daily_pnl(breakout(df3,8)); on=daily_pnl(overnight(df5,1))
rep("breakout(3m,N8)          ",bo)
rep("overnight drift          ",on)
comb=bo.add(on,fill_value=0)
rep("STACKED breakout+overnight",comb)
print()
rep("VWAP reversion(3m)       ",daily_pnl(vwap_rev(df3,15.0,-1)))
rep("opening-drive(5m)        ",daily_pnl(opening_drive(df5)))
rep("NR-expansion breakout(3m)",daily_pnl(nr_expand(df3,8)))
