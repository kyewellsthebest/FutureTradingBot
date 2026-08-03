import sys,os
sys.path.insert(0,"/home/user/FutureTradingBot/research/mining_2026_07_31/mega2")
os.environ.update(M2_TF="5",M2_THIN="1",M2_DEPTH="2",M2_SHARD="0/1",M2_COMM="0")
sys.argv=["x",sys.argv[1] if len(sys.argv)>1 else "NQ"]
src=open("stage1f.py").read()
cut="# ------------------------------------------------------- fills and outcomes"
hdr,rest=src.split(cut)[0],cut+src.split(cut)[1]
rest=rest.split("# ------------------------------------------------------------ scoring loop")[0]
exec(compile(hdr.replace("def streams():","def _u():"),"h","exec"))
exec(compile(rest,"r","exec"))
import numpy as np,pandas as pd
wks=len(pd.Series(ts.dt.strftime('%G-W%V')).unique())
print(f"\n{ROOT}: BREAK-EVEN ROUND TURN BY PULLBACK DEPTH  (stop 2xATR, target 1.5R)")
print(f"{'pullback':>9}{'trades/wk':>11}{'gross $/tr':>12}{'BREAK-EVEN':>12}"
      f"{'net@$1.42':>11}{'net@$0.62':>11}{'$/wk@0.62':>11}{'win%':>7}")
best=[]
for lb,k in ((12,2.5),(8,1.75),(3,1.25),(20,2.5)):
    m=mom(lb); sig=sigok&np.isfinite(m)&(np.abs(m)>k*ATR)
    idx=thin(np.where(sig)[0]); side=np.sign(m[idx]).astype(np.int64)
    ok=side!=0; idx,side=idx[ok],side[ok]
    for pb in (0.05,0.08,0.12,0.16,0.20,0.25,0.30,0.382,0.5,0.618):
        px=rnd(C_[idx]-pb*m[idx])
        fb,epx=resolve_fills(idx,side,px,"L",9,1.0)
        f=fb>=0
        if f.sum()<200: continue
        w=build_windows(fb[f],side[f],24)
        xj,xpx=outcomes(w,fb[f],epx[f],side[f],ATR[idx][f],2.0,1.5,2.5,24)
        g=xj>=0
        if g.sum()<200: continue
        pnl=(xpx[g]-epx[f][g])*side[f][g]*PV
        tpw=g.sum()/wks; gross=pnl.mean(); wr=(pnl>0).mean()
        best.append((lb,k,pb,tpw,gross,wr))
        if (lb,k)==(12,2.5):
            print(f"{pb:>9.2f}{tpw:>11.0f}{gross:>12.2f}{gross:>12.2f}"
                  f"{gross-1.42:>11.2f}{gross-0.62:>11.2f}{(gross-0.62)*tpw:>11.0f}{wr*100:>7.0f}")
print("\n=== ANY SETUP REACHING >=125 TRADES/WEEK (what 4 strategies need for 500) ===")
print(f"{'lb':>4}{'k':>6}{'pb':>7}{'trades/wk':>11}{'gross $/tr':>12}{'BREAK-EVEN':>12}{'$/wk@0.62':>11}{'win%':>7}")
hi=[b for b in best if b[3]>=125]
for lb,k,pb,tpw,gross,wr in sorted(hi,key=lambda x:-x[3])[:12]:
    print(f"{lb:>4}{k:>6.2f}{pb:>7.2f}{tpw:>11.0f}{gross:>12.2f}{gross:>12.2f}"
          f"{(gross-0.62)*tpw:>11.0f}{wr*100:>7.0f}")
if not hi: print("  none")
