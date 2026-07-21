import numpy as np, pandas as pd, gc, glob, time
import pyarrow.parquet as pq
PT,FEE,TICK,LAT=2.0,1.50,0.25,65_000_000
TGT,STP=260.0,80.0; HOLD=240
LO_H,HI_H=14.0,20.44; EOD=(20*60+55)*60_000_000_000
OFFS=[0.0,25,-25,50,-50,75,-75,100,-100,150,-150]  # session-open ± NQ pts
CAPS=[1,3,5,7]
t0=time.time()
def bracket(ts,px,fi,entry,s,t_max,n):
    xe=min(np.searchsorted(ts,t_max,"left"),n-1)
    if xe<=fi: return None,fi
    tl,sl=entry+TGT*s,entry-STP*s; seg=px[fi+1:xe]
    if not len(seg): return px[xe]-TICK*s,xe
    ht=np.flatnonzero(seg*s>(tl+TICK*s)*s-1e-9); hs=np.flatnonzero(seg*s<=sl*s+1e-9)
    it=ht[0] if len(ht) else 10**9; is_=hs[0] if len(hs) else 10**9
    if it<is_: return tl,fi+1+int(it)
    if is_<it:
        k=fi+1+int(is_); rw=min(px[k],sl) if s>0 else max(px[k],sl); return rw-TICK*s,k
    return px[xe]-TICK*s,xe
ALL=[]  # (t_in, t_out, pnl)
def process(ts,px):
    d=ts//86_400_000_000_000
    st=np.concatenate(([0],np.flatnonzero(np.diff(d))+1)); en=np.concatenate((st[1:],[len(ts)]))
    for di in range(len(st)):
        day0=int(d[st[di]])*86_400_000_000_000; a,b=st[di],en[di]
        tsd,pxd=ts[a:b],px[a:b]; n=len(tsd)
        i0=np.searchsorted(tsd,day0+int(LO_H*3600e9)); i1=np.searchsorted(tsd,day0+int(HI_H*3600e9))
        if i1-i0<5000: continue
        anchor=pxd[i0]
        for off in OFFS:
            lev=anchor+off
            abv=pxd[i0:i1]>lev
            fx=i0+np.flatnonzero(abv!=np.roll(abv,1))[1:][:40]
            busy=0
            for j in fx:
                if tsd[j]<busy: continue
                s_=1 if pxd[j]>lev else -1
                fi=np.searchsorted(tsd,tsd[j]+LAT)
                if fi>=n: break
                entry=pxd[fi]+TICK*s_
                t_max=min(tsd[fi]+HOLD*60_000_000_000,day0+EOD)
                fill,k=bracket(tsd,pxd,fi,entry,s_,t_max,n)
                if fill is None: continue
                ALL.append((int(tsd[fi]),int(tsd[k]),(fill-entry)*s_*PT-FEE)); busy=tsd[k]
# 2026 tape
import sys; sys.path.insert(0,"research"); import round54_clock as K
K.build_tape(); process(K.D["ts"],K.D["px"]); K.D.clear(); gc.collect()
print(f"2026 done ({time.time()-t0:.0f}s), trades so far {len(ALL)}")
# history 2024-2025
pf=pq.ParquetFile("data/tick/nq_ticks_2p5y.parquet"); YB={}
for batch in pf.iter_batches(batch_size=8_000_000,columns=["ts","price"]):
    bt=batch.column("ts").to_numpy(); bp=batch.column("price").to_numpy().astype(np.float32)
    keep=bt<1_767_225_600_000_000_000
    bt,bp=bt[keep],bp[keep]
    if not len(bt): continue
    for y in np.unique(bt//31_536_000_000_000_000):
        m=(bt//31_536_000_000_000_000)==y; YB.setdefault(int(y),[]).append((bt[m],bp[m]))
for y in sorted(YB):
    ts=np.concatenate([a for a,_ in YB[y]]); px=np.concatenate([b for _,b in YB[y]]).astype(np.float64)
    YB[y]=None; gc.collect(); o=np.argsort(ts,kind="stable"); ts,px=ts[o],px[o]
    wd=(ts//86_400_000_000_000+4)%7; keep=np.isfinite(px)&(wd<5); ts,px=ts[keep],px[keep]
    if len(ts)>500_000: process(ts,px)
    del ts,px; gc.collect(); print(f"  hist {y} done ({time.time()-t0:.0f}s), trades {len(ALL)}")
# concurrency-capped P&L
ALL.sort()
print(f"\ntotal raw rung-trades: {len(ALL)}")
for M in CAPS:
    openx=[]; kept=[]
    for ti,to,pnl in ALL:
        openx=[x for x in openx if x>ti]
        if len(openx)>=M: continue
        kept.append((to,pnl)); openx.append(to)
    p=np.array([k[1] for k in kept]); et=np.array([k[0] for k in kept])
    sr=pd.Series(p,index=pd.to_datetime(et,utc=True)).sort_index()
    wk=sr.resample("W").sum(); wk=wk[wk!=0]; dy=sr.resample("D").sum(); dy=dy[dy!=0]
    print(f"CAP {M}: {len(p)} tr | ${sr.sum()/len(wk):+.0f}/wk | WR {100*(p>0).mean():.0f}% "
          f"| posW {100*(wk>0).mean():.0f}% | worstday ${dy.min():+.0f}")
print(f"DONE ({time.time()-t0:.0f}s)")
