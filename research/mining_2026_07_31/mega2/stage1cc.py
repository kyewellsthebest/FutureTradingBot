"""CAPITAL-CONSTRAINED multi-market search.

Everything before this measured P&L per trade and multiplied by trade count,
with no limit on concurrent positions. A 539-trade/week config peaked at 36 open
contracts -- $1.6M notional on a $4,100 account. Its headline $4,240/week was
leverage, and its real drawdown was -$27,689, or 675% of the account.

Two things are different here:

  POSITION LIMIT IS A HARD CONSTRAINT. A signal is only taken if a slot is
  free, exactly as it would be live. Everything else is skipped.

  THE OBJECTIVE IS THE CURVE, NOT THE REVENUE. Configs must keep drawdown,
  worst week and green-week rate inside what a small account survives.
  Weekly dollars only breaks ties among survivors.

And it searches the markets that fit the account. NQ carries $39 of risk at a
2xATR stop, second highest of anything tradeable; M2K carries $12 for the same
shape and the same ~225 bars a day. NQ was the only market searched in depth
before this, and it was the wrong one.
"""
import json, sys, os, gzip, time, itertools
import numpy as np, pandas as pd
REPO=os.environ.get("M2_REPO","/home/user/FutureTradingBot")
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from econ import ECON
ROOT=sys.argv[1]; TF=os.environ.get("M2_TF","5")
SHARD=os.environ.get("M2_SHARD",""); SH_K,SH_N=(int(SHARD.split("/")[0]),int(SHARD.split("/")[1])) if SHARD else (0,1)
ACCT=float(os.environ.get("M2_ACCT","4100"))
MAXRISK=float(os.environ.get("M2_MAXRISK","30"))     # $ risk per trade ceiling
MAXDD=float(os.environ.get("M2_MAXDD","800"))        # $ drawdown ceiling
MAXPOS=[int(x) for x in os.environ.get("M2_MAXPOS","1,2,3").split(",")]
PV,TICK,COMM,TRADED,MARG,AFF=ECON[ROOT]
COMM*=float(os.environ.get("M2_COMMMULT","1.0"))
DPT=PV*TICK                                          # dollars per tick
t0=time.time()
df=pd.read_csv(f"{REPO}/data/polygon/{ROOT}_5min.csv")
df["ts"]=pd.to_datetime(df.ts,utc=True)
if TF!="5":
    df=(df.set_index("ts").resample(f"{TF}min",label="left",closed="left")
        .agg(open=("open","first"),high=("high","max"),low=("low","min"),
             close=("close","last")).dropna(subset=["close"]).reset_index())
df=df.sort_values("ts").reset_index(drop=True)
C=df.close.values.astype(float); H=df.high.values.astype(float); L=df.low.values.astype(float)
n=len(C); dt=df.ts
d1=np.abs(np.r_[0,np.diff(C)])/TICK
ATR=pd.Series(d1).rolling(50,min_periods=20).mean().values
hr=(dt.dt.hour+dt.dt.minute/60.0).values
gap=(dt.diff()>pd.Timedelta("3h")).values
contam=pd.Series(gap).rolling(60,min_periods=1).max().fillna(0).values.astype(bool)
OK=np.isfinite(ATR)&(ATR>0)&~contam&~((hr>=21.0)&(hr<22.5))
days=dt.dt.date.nunique(); wks=days/5.0; cut=int(n*0.75)
PAD=300
Hp=np.r_[H,np.full(PAD,np.nan)]; Lp=np.r_[L,np.full(PAD,np.nan)]; Cp=np.r_[C,np.full(PAD,np.nan)]
dayk=pd.factorize(dt.dt.date)[0]; wkk=pd.factorize(dt.dt.strftime("%G-W%V"))[0]
print(f"{ROOT}({TRADED}) tf{TF}: {n:,} bars, {days}d ({wks:.0f}wk), "
      f"ATR {np.nanmedian(ATR):.1f}tk = ${np.nanmedian(ATR)*DPT:.0f}, RT ${COMM:.2f}",flush=True)

LBS=[2,3,5,8,12,20,32]; KS=[0.75,1.0,1.5,2.0,3.0]
PBS=[0.15,0.25,0.35,0.5,0.7,1.0,1.3]; SPS=[0.5,0.75,1.0,1.5,2.0,3.0]
RRS=[1.5,1.75,2.0]; HOLDS=[3,6,12,24,48]; TTLS=[3,6,12]
SESS=[None,"us","eu","peak"]; DIRS=[1,-1]
rows=[]; ncfg=0
for si,(lb,k) in enumerate(itertools.product(LBS,KS)):
    if si%SH_N!=SH_K: continue
    mom=np.r_[np.full(lb,np.nan),(C[lb:]-C[:-lb])/TICK]
    base=OK&np.isfinite(mom)&(np.abs(mom)>k*ATR); base[:max(lb,60)]=False; base[n-200:]=False
    for sess in SESS:
        sg=base.copy()
        if sess=="us": sg&=(hr>=13.5)&(hr<20.0)
        elif sess=="eu": sg&=(hr>=7.0)&(hr<13.5)
        elif sess=="peak": sg&=(hr>=13.5)&(hr<16.0)
        idx=np.where(sg)[0]
        if len(idx)<200: continue
        sgn=np.sign(mom[idx]).astype(np.int64)
        for DIRN in DIRS:
            side=DIRN*sgn
            for pb,ttl in itertools.product(PBS,TTLS):
                lim=C[idx]-(pb*np.abs(mom[idx])*TICK)*side
                st=np.arange(1,ttl+1); bars=idx[:,None]+st[None,:]
                adv=np.where(side[:,None]>0,Lp[bars],Hp[bars])
                thr=(adv*side[:,None])<=(lim*side)[:,None]-TICK+1e-9
                j=np.where(thr.any(1),thr.argmax(1),10**9); ok=j<10**9
                if ok.sum()<200: continue
                fb=idx[ok]+1+j[ok]; sd=side[ok]; ep=lim[ok]; av=ATR[idx][ok]
                for hold in HOLDS:
                    js=np.arange(0,hold+1); wb=fb[:,None]+js[None,:]
                    g=sd[:,None].astype(float)
                    lo=np.where(g>0,Lp[wb],Hp[wb])*g; hi=np.where(g>0,Hp[wb],Lp[wb])*g
                    cw=Cp[wb]; ar=np.arange(len(fb)); eps=ep*sd
                    for sp,rr in itertools.product(SPS,RRS):
                        stk=np.maximum(sp*av,2.0); risk=np.median(stk)*DPT
                        ncfg+=1
                        if risk>MAXRISK: continue      # too big for the account
                        sl=eps-stk*TICK; tp=eps+rr*stk*TICK
                        hs=lo<=sl[:,None]; ht=hi>=tp[:,None]; ht[:,0]=False
                        j1=np.where(hs.any(1),hs.argmax(1),10**9)
                        j2=np.where(ht.any(1),ht.argmax(1),10**9)
                        ks_=j1<=np.minimum(j2,hold); kt=(~ks_)&(j2<=hold)
                        xj=np.where(ks_,np.minimum(j1,hold),np.where(kt,np.minimum(j2,hold),hold))
                        xp=np.where(ks_,(sl-TICK)*sd,np.where(kt,tp*sd,
                                    cw[ar,np.minimum(xj,hold)]-TICK*sd))
                        gd=np.isfinite(xp)
                        if gd.sum()<200: continue
                        P=(xp[gd]-ep[gd])*sd[gd]*(1/TICK)*DPT-COMM
                        F=fb[gd]; X=fb[gd]+xj[gd]
                        o=np.argsort(F); P,F,X=P[o],F[o],X[o]
                        for mp in MAXPOS:
                            free=np.zeros(mp,dtype=np.int64); took=np.zeros(len(P),bool)
                            for i in range(len(P)):
                                s_=int(np.argmin(free))
                                if free[s_]<=F[i]: took[i]=True; free[s_]=X[i]
                            p=P[took]; f=F[took]
                            if len(p)<120: continue
                            eq=np.cumsum(p); dd=(eq-np.maximum.accumulate(eq)).min()
                            if dd<-MAXDD: continue      # blows the account
                            dsum=np.bincount(dayk[np.clip(f,0,n-1)],weights=p)
                            wsum=np.bincount(wkk[np.clip(f,0,n-1)],weights=p)
                            dsum=dsum[dsum!=0]; wsum=wsum[wsum!=0]
                            gw=(wsum>0).mean()
                            if gw<0.60: continue
                            m=f<cut
                            if m.sum()<80 or (~m).sum()<30: continue
                            if p[~m].mean()<=0 or p[m].mean()<=0: continue
                            stq=0; mxs=0
                            for q in p: stq=stq+1 if q<=0 else 0; mxs=max(mxs,stq)
                            rows.append(dict(mkt=ROOT,traded=TRADED,tf=TF,dir="fol" if DIRN>0 else "fade",
                                lb=lb,k=k,pb=pb,ttl=ttl,sp=sp,rr=rr,hold=hold,sess=sess or "all",
                                maxpos=mp,risk=round(risk,1),tpw=round(len(p)/wks,1),
                                wr=round(float((p>0).mean()),4),avg=round(float(p.mean()),3),
                                wkly=round(float(p.sum()/wks),1),maxdd=round(float(dd),0),
                                worst_day=round(float(dsum.min()),0),worst_wk=round(float(wsum.min()),0),
                                green_wk=round(float(gw),3),green_day=round(float((dsum>0).mean()),3),
                                streak=int(mxs),tr=round(float(p[m].mean()),3),
                                ho=round(float(p[~m].mean()),3),n=int(len(p))))
d=pd.DataFrame(rows)
el=time.time()-t0
print(f"{ROOT}: {ncfg:,} configs, {len(d):,} survive the account constraints, {el:.0f}s",flush=True)
if len(d):
    d=d.sort_values("wkly",ascending=False).head(3000)
    print(d.head(10)[["dir","lb","k","pb","sp","rr","hold","sess","maxpos","risk",
        "tpw","wr","wkly","maxdd","worst_day","worst_wk","green_wk","streak","ho"]].to_string(index=False))
suf=f"cc_{ROOT}_tf{TF}"+(f"_sh{SH_K}" if SHARD else "")
with gzip.open(f"{os.path.dirname(os.path.abspath(__file__))}/{suf}.json.gz","wt") as f:
    json.dump(dict(root=ROOT,traded=TRADED,tf=TF,n_cfg=ncfg,n_ok=len(d),
                   dpt=DPT,comm=COMM,elapsed=round(el),
                   top=d.to_dict("records") if len(d) else []),f)
print(f"-> {suf}.json.gz",flush=True)
