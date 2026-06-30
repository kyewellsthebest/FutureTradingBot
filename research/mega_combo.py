"""Phase 2 (deeper): 2-signal COMBINATIONS (AND/OR) + cross-asset confirmation.
Reuses the single-position engine. Combinatorial -> tens of thousands of combos.
Target bar: beat $500/day. Survivors stream to research/combo_survivors.csv."""
from __future__ import annotations
import itertools, time
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd
import research.mega_search as MS
from research.mega_search import sig, backtest, metrics, _TF, SESSIONS, EXITS

# base signals that were productive in Phase 1 (trend/breakout/momentum + reversion + xasset)
BASE={
 "donch":[(6,),(8,),(12,)],
 "mom":[(3,0.001),(5,0.001),(10,0.001)],
 "ema":[(9,50),(9,20),(20,50)],
 "keltbreak":[(20,1.0),(20,1.5)],
 "bbbreak":[(20,2.0),(50,2.0)],
 "rsirev":[(14,30,70),(7,20,80)],
 "zrev":[(20,2.0),(60,2.0)],
}

def es_sig(A):
    """ES-momentum confirmation signal aligned to NQ bars (already in _TF? no)."""
    return None  # cross-asset handled separately in Phase 3 if needed

def combo_sig(A, s1, s2, logic):
    z1=sig(s1[0],A,s1[1]); z2=sig(s2[0],A,s2[1])
    out=np.zeros(len(z1),"int8")
    if logic=="and":
        # both agree on direction (use z1 trigger gated by z2 same-sign recent state)
        # carry z2 last non-zero as a regime
        st=pd.Series(z2).replace(0,np.nan).ffill().fillna(0).to_numpy()
        out[(z1==1)&(st==1)]=1; out[(z1==-1)&(st==-1)]=-1
    else: # or
        out[(z1==1)|(z2==1)]=1; out[(z1==-1)|(z2==-1)]=-1
        out[((z1==1)|(z2==1))&((z1==-1)|(z2==-1))]=0
    return out

def _eval(item):
    tf,s1,s2,logic=item; A=_TF[tf]
    z=combo_sig(A,s1,s2,logic)
    if (z!=0).sum()<80: return []
    out=[]
    for sess in ("rth","morning"):
        for ex in EXITS:
            m=metrics(backtest(z,A,sess,ex,False))
            if not m: continue
            m.update(tf=tf,combo=f"{s1[0]}{s1[1]}&{s2[0]}{s2[1]}",logic=logic,sess=sess,exit=f"{ex[0]}{ex[1]}/{ex[2]}/{ex[3]}")
            out.append(m)
    return out

def main():
    t0=time.time(); MS._init()
    specs=[(n,p) for n,ps in BASE.items() for p in ps]
    items=[]
    for tf in ("3min","5min"):
        for i in range(len(specs)):
            for j in range(len(specs)):
                if i==j: continue
                for logic in ("and","or"):
                    items.append((tf,specs[i],specs[j],logic))
    print(f"COMBO SEARCH: {len(items)} combos x sess x exits  {time.time()-t0:.0f}s",flush=True)
    allrows=[]; surv=[]; best=0
    with ProcessPoolExecutor(max_workers=4) as ex:
        for k,res in enumerate(ex.map(_eval,items,chunksize=4)):
            allrows.extend(res)
            for m in res:
                if m["per_day"]>best: best=m["per_day"]
                if m["per_day"]>500 and m["pos_yrs"]==m["n_yrs"]:
                    surv.append(m); print("!!! >$500 SURVIVOR:",m,flush=True)
            if (k+1)%50==0:
                print(f"  {k+1}/{len(items)}  {time.time()-t0:.0f}s rows={len(allrows)} best/day=${best:.0f}",flush=True)
                pd.DataFrame(allrows).to_csv("research/combo_all.csv",index=False)
    df=pd.DataFrame(allrows); df.to_csv("research/combo_all.csv",index=False)
    print(f"\nDONE {time.time()-t0:.0f}s | {len(df)} results | best/day=${best:.0f} | >$500: {len(surv)}",flush=True)
    cols=["per_day","sharpe","maxDD","pos_yrs","n_yrs","worst_yr","n","tf","combo","logic","sess","exit"]
    print("\n=== TOP 25 by per_day ===")
    print(df.sort_values("per_day",ascending=False).head(25)[cols].to_string(index=False))

if __name__=="__main__":
    main()
