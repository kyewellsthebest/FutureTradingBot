"""Round 10: fifty MORE untouched families (patterns, structure,
liquidity, time-conditioned hybrids). Same honest engine + protocol."""
import numpy as np, pandas as pd
from multiprocessing import Pool
from research.midfreq_search import load_bars, resample
from research.midfreq_round4 import metrics_split, run_exit_ts

WEEKS = 156.1

def build(df):
    o=df["open"].to_numpy(); h=df["high"].to_numpy(); l=df["low"].to_numpy(); c=df["close"].to_numpy()
    idx=df.index; hrs=np.asarray(idx.hour)+np.asarray(idx.minute)/60.0; dk=idx.normalize()
    dow=np.asarray(idx.dayofweek)
    cs=pd.Series(c,index=idx); hs=pd.Series(h); ls=pd.Series(l)
    tr=np.maximum(h-l,np.abs(c-np.roll(c,1))); atr=pd.Series(tr).rolling(20).mean().to_numpy()
    rng=np.where((h-l)>0,h-l,np.nan); body=c-o; ubw=h-np.maximum(c,o); lbw=np.minimum(c,o)-l
    up=body>0; dn=body<0
    prevh=np.roll(h,1); prevl=np.roll(l,1); prevc=np.roll(c,1); prevo=np.roll(o,1)
    rth=(hrs>=13.5)&(hrs<20.9)
    ema20=cs.ewm(span=20,adjust=False).mean().to_numpy(); ema50=cs.ewm(span=50,adjust=False).mean().to_numpy()
    sma20=cs.rolling(20).mean().to_numpy(); sd20=cs.rolling(20).std().to_numpy()
    bbu=sma20+2*sd20; bbd=sma20-2*sd20
    lo30=ls.rolling(30).min().shift(1).to_numpy(); hi30=hs.rolling(30).max().shift(1).to_numpy()
    donmid=(hs.rolling(20).max().shift(1).to_numpy()+ls.rolling(20).min().shift(1).to_numpy())/2
    delta=cs.diff(); rup=delta.clip(lower=0).rolling(14).mean(); rdn=(-delta.clip(upper=0)).rolling(14).mean()
    rsi14=(100-100/(1+rup/rdn.replace(0,np.nan))).to_numpy()
    lr=cs.rolling(30).apply(lambda x: np.polyfit(np.arange(30),x,1)[0], raw=True).to_numpy()
    kama=cs.ewm(span=30,adjust=False).mean().to_numpy()
    bars_since_hi=np.zeros(len(c)); bars_since_lo=np.zeros(len(c))
    rh=hs.rolling(20).max().to_numpy(); rl20=ls.rolling(20).min().to_numpy()
    d_close=cs.resample('1D').last().dropna(); d_open=pd.Series(o,index=idx).resample('1D').first().dropna()
    d_up=(d_close>d_open).astype(int); run2=d_up.rolling(2).sum().shift(1)
    run2m=dk.map(run2).to_numpy(float)
    wk_hi=hs.groupby(pd.Series(idx-pd.to_timedelta(idx.dayofweek,unit='D')).dt.normalize().values).transform('max')
    pwh=cs.resample('1W').max().shift(1); pwl=pd.Series(l,index=idx).resample('1W').min().shift(1)
    pwhm=idx.to_period('W').start_time.map(pwh.groupby(pwh.index.to_period('W').start_time).first())
    pwhm=np.asarray(pwhm,dtype=float)
    gapmag=dk.map(d_close.shift(1)).to_numpy(float)
    smean=cs.groupby(dk).expanding().mean().reset_index(level=0,drop=True).reindex(idx).to_numpy()
    mom5=cs.diff(5).to_numpy(); mom10=cs.diff(10).to_numpy()
    inside=(h<prevh)&(l>prevl)
    ins2=inside&np.roll(inside,1)
    swept_lo=(l<lo30)&(c>prevc); swept_hi=(h>hi30)&(c<prevc)
    eqh=np.abs(hi30-np.roll(hi30,5))<1.0
    lunch=(hrs>=17.0)&(hrs<18.0); eu_close=(hrs>=15.4)&(hrs<15.6); pwr=(hrs>=19.0)&(hrs<20.9)
    hod=pd.Series(h,index=idx).groupby(dk).cummax().shift(1).to_numpy()
    lod=pd.Series(l,index=idx).groupby(dk).cummin().shift(1).to_numpy()
    fhh=pd.Series(np.where((hrs>=13.5)&(hrs<14.5),h,np.nan),index=idx).groupby(dk).transform('max').to_numpy()
    dayrng_h=pd.Series(h,index=idx).groupby(dk).cummax().to_numpy(); dayrng_l=pd.Series(l,index=idx).groupby(dk).cummin().to_numpy()
    F={}
    F['HAMMER']=((lbw>2*np.abs(body))&(l<=rl20)&up, (ubw>2*np.abs(body))&(h>=rh)&dn)
    F['TWEEZ']=((np.abs(l-prevl)<0.5)&up&np.roll(dn,1)&(l<=lo30+2), (np.abs(h-prevh)<0.5)&dn&np.roll(up,1)&(h>=hi30-2))
    F['MARU']=((np.abs(body)/rng>0.9)&up, (np.abs(body)/rng>0.9)&dn)
    F['DOJIB']=((np.abs(np.roll(body,1))/np.roll(rng,1)<0.1)&(c>prevh), (np.abs(np.roll(body,1))/np.roll(rng,1)<0.1)&(c<prevl))
    F['TLS']=(up&np.roll(dn,1)&np.roll(dn,2)&np.roll(dn,3)&(c>np.roll(o,3)), dn&np.roll(up,1)&np.roll(up,2)&np.roll(up,3)&(c<np.roll(o,3)))
    F['GNG']=((o>prevh)&up, (o<prevl)&dn)
    F['EXGF']=((o>prevh+0.5*np.nan_to_num(atr,nan=1e9))&dn, (o<prevl-0.5*np.nan_to_num(atr,nan=1e9))&up)
    F['MSTAR']=(np.roll(dn,2)&(np.abs(np.roll(body,1))/np.roll(rng,1)<0.3)&up&(c>np.roll((o+c)/2,2)), np.roll(up,2)&(np.abs(np.roll(body,1))/np.roll(rng,1)<0.3)&dn&(c<np.roll((o+c)/2,2)))
    F['BBWALK']=((c>bbu)&(prevc>np.roll(bbu,1))&(np.roll(c,2)>np.roll(bbu,2)), (c<bbd)&(prevc<np.roll(bbd,1))&(np.roll(c,2)<np.roll(bbd,2)))
    F['BWEXP']=(((bbu-bbd)>1.5*np.roll(bbu-bbd,10))&up, ((bbu-bbd)>1.5*np.roll(bbu-bbd,10))&dn)
    F['DONMID']=((c<donmid)&(np.roll(c,1)>=np.roll(donmid,1))&(ema50>np.roll(ema50,10)), (c>donmid)&(np.roll(c,1)<=np.roll(donmid,1))&(ema50<np.roll(ema50,10)))
    F['SWEEP']=(swept_lo, swept_hi)
    F['EQHB']=(eqh&(c>hi30), np.zeros(len(c),bool))
    F['TRIN']=(ins2&(c>prevh), ins2&(c<prevl))
    F['LUNCHF']=(lunch&(c<smean-10), lunch&(c>smean+10))
    F['EUREV']=(eu_close&(mom10<-15), eu_close&(mom10>15))
    F['PWRBO']=(pwr&(c>hod), pwr&(c<lod))
    F['D2UP']=((run2m>=2)&(l<=ema20)&(c>ema20), (run2m<=0)&(h>=ema20)&(c<ema20))
    F['FHFADE']=((h>=fhh)&dn&(hrs>=14.5), np.zeros(len(c),bool))
    F['GAPFILL']=((c<gapmag-10)&(c>np.roll(c,3)), (c>gapmag+10)&(c<np.roll(c,3)))
    F['LRB']=((lr>0.15)&(c>ema20), (lr<-0.15)&(c<ema20))
    F['LRF']=((lr<-0.15)&(l<=rl20), (lr>0.15)&(h>=rh))
    F['FRAC']=((h<np.roll(h,2))&False|( (np.roll(h,2)>np.roll(h,1))&(np.roll(h,2)>np.roll(h,3))&(np.roll(h,2)>h)&(np.roll(h,2)>np.roll(h,4))&(c>np.roll(h,2)) ), ((np.roll(l,2)<np.roll(l,1))&(np.roll(l,2)<np.roll(l,3))&(np.roll(l,2)<l)&(np.roll(l,2)<np.roll(l,4))&(c<np.roll(l,2))))
    hh=(h>prevh)&(l>prevl); ll=(h<prevh)&(l<prevl)
    F['MSS']=(hh&np.roll(hh,1)&np.roll(ll,3), ll&np.roll(ll,1)&np.roll(hh,3))
    F['RSI50']=((rsi14>50)&(np.roll(rsi14,1)<=50), (rsi14<50)&(np.roll(rsi14,1)>=50))
    F['RSIDIV']=((l<np.roll(rl20,1))&(rsi14>np.roll(rsi14,10)+5), (h>np.roll(rh,1))&(rsi14<np.roll(rsi14,10)-5))
    F['KAMAX']=((c>kama)&(prevc<=np.roll(kama,1)), (c<kama)&(prevc>=np.roll(kama,1)))
    F['THRTOD']=(((h-l)>2.5*np.nan_to_num(atr,nan=1e9))&up&(hrs>=14.5)&(hrs<16.5), ((h-l)>2.5*np.nan_to_num(atr,nan=1e9))&dn&(hrs>=14.5)&(hrs<16.5))
    F['SMBAND']=((c<smean-1.5*np.nan_to_num(atr,nan=1e9)), (c>smean+1.5*np.nan_to_num(atr,nan=1e9)))
    F['3PUSH']=((h>prevh)&(prevh>np.roll(h,2))&(np.roll(h,2)>np.roll(h,3))&dn, (l<prevl)&(prevl<np.roll(l,2))&(np.roll(l,2)<np.roll(l,3))&up)
    F['RET30']=(np.roll((c>hi30),3)&(l<=hi30)&(c>hi30), np.roll((c<lo30),3)&(h>=lo30)&(c<lo30))
    F['WKHL']=((c>pwhm), np.zeros(len(c),bool))
    F['MONF']=((dow==0)&(c<gapmag-20), (dow==0)&(c>gapmag+20))
    F['SQOFF']=((hrs>=20.3)&(hrs<20.6)&(mom10>10), (hrs>=20.3)&(hrs<20.6)&(mom10<-10))
    F['MIDBO']=((hrs>=16)&(hrs<18)&(c>dayrng_h*0+np.nan_to_num(hod,nan=1e18))&(c>hod), (hrs>=16)&(hrs<18)&(c<lod))
    F['ONHALF']=((c<(np.nan_to_num(hod)+np.nan_to_num(lod))/2-15)&rth, (c>(np.nan_to_num(hod)+np.nan_to_num(lod))/2+15)&rth)
    F['SHOOT']=((ubw>2.5*np.abs(body))&(h>=rh)&(hrs>=13.5), (lbw>2.5*np.abs(body))&(l<=rl20)&(hrs>=13.5))
    F['ENG2']=(up&(c>prevh)&(o<prevl), dn&(c<prevl)&(o>prevh))
    F['ATRREG']=((atr<np.nanpercentile(atr,30))&(c>hi30), (atr<np.nanpercentile(atr,30))&(c<lo30))
    F['SPKIN']=((np.roll((h-l)>3*np.nan_to_num(atr,nan=1e9),1))&inside&up, (np.roll((h-l)>3*np.nan_to_num(atr,nan=1e9),1))&inside&dn)
    F['SECENT']=((c>ema20)&(prevc<=np.roll(ema20,1))&(ema20>ema50), (c<ema20)&(prevc>=np.roll(ema20,1))&(ema20<ema50))
    F['FMACDF']=((np.roll((mom5>0),1))&(mom5<0)&(c>ema50), (np.roll((mom5<0),1))&(mom5>0)&(c<ema50))
    F['POCREV']=((np.abs(c-donmid)<1)&(mom5<-5), (np.abs(c-donmid)<1)&(mom5>5))
    F['WICKS']=((lbw/rng>0.6)&(lbw/np.roll(rng,1)>0.4)&rth, (ubw/rng>0.6)&rth)
    F['DRIVE3']=(up&np.roll(up,1)&np.roll(up,2)&(body>np.roll(body,1))&(np.roll(body,1)>np.roll(body,2)), dn&np.roll(dn,1)&np.roll(dn,2)&(np.abs(body)>np.abs(np.roll(body,1)))&(np.abs(np.roll(body,1))>np.abs(np.roll(body,2))))
    F['STALL']=(((h-l)<0.5*np.nan_to_num(atr,nan=0))&(np.roll((h-l)>2*np.nan_to_num(atr,nan=1e9),1))&up, ((h-l)<0.5*np.nan_to_num(atr,nan=0))&(np.roll((h-l)>2*np.nan_to_num(atr,nan=1e9),1))&dn)
    F['VWTREND']=((smean>np.roll(smean,30))&(l<=smean)&(c>smean), (smean<np.roll(smean,30))&(h>=smean)&(c<smean))
    F['OPRNG2']=((hrs>=14.0)&(c>fhh)&(mom5>0), np.zeros(len(c),bool))
    arrs=dict(o=o,h=h,l=l,c=c,atr=atr,ts=idx.asi8,years=idx.year.to_numpy(),idx=idx,rth=rth)
    return F, arrs

def run_family(args):
    tf, fname, rl, rs_, arrs = args
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
                    out.append({"name":f"{fname}_{tf}_{mode}{p1}_{sess}","tf":tf,
                                "net_wk":net,"fees_wk":fees,"gross_wk":round(net+fees,1),**m})
    return out

def main():
    base=load_bars(); jobs=[]
    for tf in ("1min","3min"):
        df=resample(base,tf); F,arrs=build(df)
        print(f"[{tf}] {len(F)} families", flush=True)
        for fname,(rl,rs_) in F.items(): jobs.append((tf,fname,rl,rs_,arrs))
    with Pool(5) as pool: res=pool.map(run_family, jobs)
    rows=[r for s in res for r in s]
    df=pd.DataFrame(rows); df.to_csv("research/round10_results.csv", index=False)
    print(f"\nALL {len(df)} configs")
    band=df[df.trades_wk>=200]
    ok=band[(band.sel_total>0)&(band.blind_usd_wk>0)].sort_values("net_wk",ascending=False)
    cols=["name","gross_wk","fees_wk","net_wk","trades_wk","win_pct"]
    print(f"\n>=200tr/wk: {len(band)} | QUALIFIERS: {len(ok)}")
    print(ok[cols].head(15).to_string(index=False) if len(ok) else "(none)")
    print("\nBand frontier (best net regardless):")
    print(band.sort_values("net_wk",ascending=False)[cols].head(10).to_string(index=False))
    lowf=df[(df.sel_total>0)&(df.blind_usd_wk>0)&(df.trades_wk<200)].sort_values("net_wk",ascending=False)
    print(f"\nBONUS: low-freq both-window-positive (stack candidates): {len(lowf)}")
    print(lowf[cols+['blind_usd_wk']].head(10).to_string(index=False))

if __name__ == "__main__":
    main()
