import pandas as pd, time
order=["NQU3","NQZ3","NQH4","NQM4","NQU4","NQZ4","NQH5","NQM5","NQU5","NQZ5","NQH6","NQM6"]
t0=time.time(); barparts=[]
for c in order:
    df=pd.read_parquet(f"data/tick/raw/{c}.parquet", columns=["ts","price"])
    s=pd.Series(df["price"].values, index=pd.to_datetime(df["ts"].values))
    b=pd.DataFrame({"open":s.resample("1min").first(),"high":s.resample("1min").max(),
                    "low":s.resample("1min").min(),"close":s.resample("1min").last()}).dropna()
    barparts.append(b)
    print(f"  {c}: {len(b):,} bars  {time.time()-t0:.0f}s", flush=True)
    del df, s
bars=pd.concat(barparts).sort_index()
bars=bars[~bars.index.duplicated(keep="last")]
bars.to_parquet("data/tick/nq_bars_1m_2p5y.parquet")
print(f"BARS: {len(bars):,}  {bars.index.min()} -> {bars.index.max()}  ({time.time()-t0:.0f}s)", flush=True)
