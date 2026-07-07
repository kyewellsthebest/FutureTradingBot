"""Round 9: FIFTY untouched signal families, high-frequency focus.
Spec: ONE strategy, >=200 trades/wk, >=\$1k/wk net avg. Honest fills."""
import numpy as np, pandas as pd
from multiprocessing import Pool
from research.midfreq_search import load_bars, resample
from research.midfreq_round4 import metrics_split, run_exit_ts

WEEKS = 156.1

def build_signals(df):
    o=df["open"].to_numpy(); h=df["high"].to_numpy(); l=df["low"].to_numpy(); c=df["close"].to_numpy()
    idx=df.index; hrs=np.asarray(idx.hour)+np.asarray(idx.minute)/60.0; dk=idx.normalize()
    cs=pd.Series(c,index=idx); hs=pd.Series(h); ls=pd.Series(l)
    tr=np.maximum(h-l,np.abs(c-np.roll(c,1))); atr=pd.Series(tr).rolling(20).mean().to_numpy()
    ema8=cs.ewm(span=8,adjust=False).mean().to_numpy(); ema9=cs.ewm(span=9,adjust=False).mean().to_numpy()
    ema20=cs.ewm(span=20,adjust=False).mean().to_numpy(); ema21=cs.ewm(span=21,adjust=False).mean().to_numpy()
    ema50=cs.ewm(span=50,adjust=False).mean().to_numpy()
    sma20=cs.rolling(20).mean().to_numpy(); sma50=cs.rolling(50).mean().to_numpy()
    sd20=cs.rolling(20).std().to_numpy()
    z20=(c-sma20)/np.where(sd20>0,sd20,np.nan)
    mom10=cs.diff(10).to_numpy(); mom5=cs.diff(5).to_numpy()
    macd=(cs.ewm(span=12,adjust=False).mean()-cs.ewm(span=26,adjust=False).mean())
    macds=macd.ewm(span=9,adjust=False).mean(); mh=(macd-macds).to_numpy(); macd=macd.to_numpy(); macds_=macds.to_numpy()
    lo14=ls.rolling(14).min().to_numpy(); hi14=hs.rolling(14).max().to_numpy()
    stoch=100*(c-lo14)/np.where((hi14-lo14)>0,hi14-lo14,np.nan)
    tp=(h+l+c)/3; tps=pd.Series(tp)
    cci=(tp-tps.rolling(20).mean().to_numpy())/np.where(0.015*tps.rolling(20).std().to_numpy()>0,0.015*tps.rolling(20).std().to_numpy(),np.nan)
    hod=pd.Series(h,index=idx).groupby(dk).cummax().shift(1).to_numpy()
    lod=pd.Series(l,index=idx).groupby(dk).cummin().shift(1).to_numpy()
    smean=cs.groupby(dk).expanding().mean().reset_index(level=0,drop=True).reindex(idx).to_numpy()
    body=c-o; rng=np.where((h-l)>0,h-l,np.nan)
    up=body>0; dn=body<0
    prevh=np.roll(h,1); prevl=np.roll(l,1); prevc=np.roll(c,1); prevo=np.roll(o,1)
    inside=(h<prevh)&(l>prevl); outside=(h>prevh)&(l<prevl)
    # HA
    hac=(o+h+l+c)/4; hao=np.empty_like(hac); hao[0]=o[0]
    for i in range(1,len(hac)): hao[i]=(hao[i-1]+hac[i-1])/2
    haup=hac>hao
    dhi=pd.Series(h,index=idx).resample('1D').max().dropna(); dlo=pd.Series(l,index=idx).resample('1D').min().dropna(); dcl=cs.resample('1D').last().dropna()
    piv=((dhi+dlo+dcl)/3).shift(1); pv=dk.map(piv).to_numpy(float)
    onh_=pd.Series(np.where((hrs>=22)|(hrs<13.5),h,np.nan),index=idx).groupby((idx+pd.Timedelta('2h')).normalize()).transform('max').to_numpy()
    onl_=pd.Series(np.where((hrs>=22)|(hrs<13.5),l,np.nan),index=idx).groupby((idx+pd.Timedelta('2h')).normalize()).transform('min').to_numpy()
    rth=(hrs>=13.5)&(hrs<20.9)
    kmid=ema20; kup=ema20+2*atr; kdn=ema20-2*atr
    bbu=sma20+2*sd20; bbd=sma20-2*sd20
    r30h=hs.rolling(30).max().shift(1).to_numpy(); r30l=ls.rolling(30).min().shift(1).to_numpy()
    rngpos=(c-r30l)/np.where((r30h-r30l)>0,r30h-r30l,np.nan)
    shrink=(h-l)<np.roll(h-l,1); shrink3=shrink&np.roll(shrink,1)&np.roll(shrink,2)
    div_l=(l<np.roll(ls.rolling(10).min().to_numpy(),1))&(mom10>np.roll(mom10,10))
    div_s=(h>np.roll(hs.rolling(10).max().to_numpy(),1))&(mom10<np.roll(mom10,10))
    m30=cs.rolling(30).mean().to_numpy()
    F={}
    F['KELTBO']=(c>kup, c<kdn); F['KELTF']=(c<kdn, c>kup)
    F['BBF']=(c<bbd, c>bbu); F['BBR']=(c>bbu, c<bbd)
    F['MACDX']=((macd>macds_)&(np.roll(macd,1)<=np.roll(macds_,1)),(macd<macds_)&(np.roll(macd,1)>=np.roll(macds_,1)))
    F['MACDH']=((mh>0)&(np.roll(mh,1)<=0),(mh<0)&(np.roll(mh,1)>=0))
    F['STOCHX']=((stoch>20)&(np.roll(stoch,1)<=20),(stoch<80)&(np.roll(stoch,1)>=80))
    F['WPR']=(stoch<5, stoch>95)
    F['CCIF']=(cci<-150, cci>150); F['CCIT']=((cci>100)&(np.roll(cci,1)<=100),(cci<-100)&(np.roll(cci,1)>=-100))
    F['ROCT']=(mom10>12, mom10<-12); F['ROCF']=(mom10<-12, mom10>12)
    F['HAFLIP']=(haup&~np.roll(haup,1), ~haup&np.roll(haup,1))
    F['HARUN']=(haup&np.roll(haup,1)&np.roll(haup,2), (~haup)&(~np.roll(haup,1))&(~np.roll(haup,2)))
    F['INSB']=(np.roll(inside,1)&(c>prevh), np.roll(inside,1)&(c<prevl))
    F['OUTF']=(outside&up, outside&dn); F['OUTR']=(outside&dn, outside&up)
    F['REV2']=(dn.astype(bool)&False|((np.roll(dn,1))&up&(l<=np.roll(l,1))), (np.roll(up,1))&dn&(h>=np.roll(h,1)))
    F['PIVB']=((l<=pv)&(c>pv), (h>=pv)&(c<pv)); F['PIVX']=((c>pv)&(prevc<=pv), (c<pv)&(prevc>=pv))
    F['SMX']=((c>smean)&(prevc<=np.roll(smean,1)), (c<smean)&(prevc>=np.roll(smean,1)))
    F['SMSL']=((smean>np.roll(smean,10))&(c>smean), (smean<np.roll(smean,10))&(c<smean))
    F['HODBO']=(c>hod, np.zeros(len(c),bool)); F['LODF']=(l<=lod, np.zeros(len(c),bool))
    F['CLPOS']=((c-l)/rng>0.9, (h-c)/rng>0.9)
    F['GAP1']=(o>prevh, o<prevl)
    F['VCT3']=(shrink3&(c>prevh), shrink3&(c<prevl))
    F['VEXPR']=(((h-l)>3*atr)&dn, ((h-l)>3*atr)&up)
    F['RIBB']=((ema8>ema21)&(ema21>ema50)&(l<=ema21)&(c>ema21), (ema8<ema21)&(ema21<ema50)&(h>=ema21)&(c<ema21))
    F['EMAX']=((ema9>ema21)&(np.roll(ema9,1)<=np.roll(ema21,1)), (ema9<ema21)&(np.roll(ema9,1)>=np.roll(ema21,1)))
    F['SMAX']=((sma20>sma50)&(np.roll(sma20,1)<=np.roll(sma50,1)), (sma20<sma50)&(np.roll(sma20,1)>=np.roll(sma50,1)))
    F['DIVG']=(div_l, div_s)
    F['ZF']=(z20<-2.2, z20>2.2); F['ZJ']=((z20>0)&(np.roll(z20,1)<=0), (z20<0)&(np.roll(z20,1)>=0))
    F['RPMR']=(rngpos<0.08, rngpos>0.92); F['RPMO']=(rngpos>0.92, rngpos<0.08)
    chop=pd.Series(np.abs(mom10)).rolling(30).mean().to_numpy()/np.where(atr>0,atr,np.nan)
    F['CHOPB']=((chop>2.2)&(c>r30h), (chop>2.2)&(c<r30l))
    dmp=np.maximum(h-prevh,0); dmm=np.maximum(prevl-l,0)
    dip=pd.Series(dmp).rolling(14).mean().to_numpy(); dim=pd.Series(dmm).rolling(14).mean().to_numpy()
    F['DIX']=((dip>dim)&(np.roll(dip,1)<=np.roll(dim,1)), (dip<dim)&(np.roll(dip,1)>=np.roll(dim,1)))
    hourb=(np.abs(hrs-np.round(hrs))<0.02)
    F['HRMOM']=(hourb&(mom5>6), hourb&(mom5<-6))
    F['M30F']=((c>m30)&(prevc<=np.roll(m30,1)), (c<m30)&(prevc>=np.roll(m30,1)))
    d25=np.abs(c-np.round(c/25)*25)
    F['R25F']=((d25<=1.5)&(mom5<=-6), (d25<=1.5)&(mom5>=6))
    F['DBLB']=((np.abs(l-lod)<=2)&up, (np.abs(h-hod)<=2)&dn)
    psm=dk.map(((dhi+dlo)/2).shift(1)).to_numpy(float)
    F['PSMR']=((c<psm-15), (c>psm+15))
    F['ONRB']=((c>onh_)&rth, (c<onl_)&rth); F['ONRF']=((c<onl_)&rth, (c>onh_)&rth)
    f15h=pd.Series(np.where((hrs>=13.5)&(hrs<13.75),h,np.nan),index=idx).groupby(dk).transform('max').to_numpy()
    f15l=pd.Series(np.where((hrs>=13.5)&(hrs<13.75),l,np.nan),index=idx).groupby(dk).transform('min').to_numpy()
    aft=(hrs>=13.75)
    F['F15']=(aft&(c>f15h)&rth, aft&(c<f15l)&rth)
    F['MPB2']=((mom10>10)&(mom5<0)&(c>ema20), (mom10<-10)&(mom5>0)&(c<ema20))
    above=pd.Series((c>smean).astype(float)).rolling(5).sum().to_numpy()
    F['PERS']=(above>=5, above<=0)
    F['BIGB']=((np.abs(body)/rng>0.8)&up&((h-l)>1.5*atr), (np.abs(body)/rng>0.8)&dn&((h-l)>1.5*atr))
    arrs=dict(o=o,h=h,l=l,c=c,atr=atr,ts=idx.asi8,years=idx.year.to_numpy(),idx=idx,rth=rth)
    return F, arrs

def run_family(args):
    tf, fname, rl, rs_, arrs = args
    o,h,l,c,atr,ts,years,idx,rth = (arrs[k] for k in ('o','h','l','c','atr','ts','years','idx','rth'))
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
                    out.append({"name":f"{fname}_{tf}_{mode}{p1}_{sess}","tf":tf,
                                "net_wk":net,"fees_wk":fees,"gross_wk":round(net+fees,1),**m})
    return out

def main():
    base=load_bars()
    jobs=[]
    store={}
    for tf in ("1min","3min"):
        df=resample(base,tf)
        F,arrs=build_signals(df)
        print(f"[{tf}] {len(F)} families", flush=True)
        for fname,(rl,rs_) in F.items():
            jobs.append((tf,fname,rl,rs_,arrs))
    with Pool(5) as pool:
        res=pool.map(run_family, jobs)
    rows=[r for sub in res for r in sub]
    df=pd.DataFrame(rows); df.to_csv("research/round9_results.csv", index=False)
    print(f"\nALL {len(df)} configs saved")
    band=df[df.trades_wk>=200]
    print(f"\n>=200 trades/wk: {len(band)} configs")
    ok=band[(band.sel_total>0)&(band.blind_usd_wk>0)].sort_values("net_wk",ascending=False)
    cols=["name","gross_wk","fees_wk","net_wk","trades_wk","win_pct","sel_usd_wk","blind_usd_wk"]
    print(f"\nQUALIFIERS (>=200tr/wk, positive both windows): {len(ok)}")
    print(ok[cols].head(20).to_string(index=False))
    print("\nBest net_wk in band regardless of windows (frontier):")
    print(band.sort_values("net_wk",ascending=False)[cols].head(15).to_string(index=False))

if __name__ == "__main__":
    main()
