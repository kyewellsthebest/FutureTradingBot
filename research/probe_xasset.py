import json,os,urllib.request,urllib.error
KEY=os.environ["POLYGON_API"]
def get(u):
    try:
        r=urllib.request.urlopen(urllib.request.Request(u+f"&apiKey={KEY}",headers={"User-Agent":"p/1"}),timeout=40)
        return json.loads(r.read().decode()),None
    except urllib.error.HTTPError as e:
        try:b=json.loads(e.read().decode())
        except:b={}
        return None,f"HTTP {e.code}: {b.get('message') or b.get('error')}"
    except Exception as e: return None,f"{type(e).__name__}:{e}"
base="https://api.polygon.io/futures/v1"
# ES, ZB(30y), ZN(10y), GC(gold) front-ish contracts; try 1-second aggs
for tk in ["ESM6","ESH6","ZBM6","ZNM6","GCM6","GCQ6"]:
    d,e=get(base+f"/aggs/{tk}?resolution=1_second&limit=3")
    if e: print(f"{tk}: {e}")
    else:
        r=(d or {}).get("results") or []
        print(f"{tk}: OK results={len(r)} sample={json.dumps(r[0]) if r else 'none'}")
# VIX index
for ix in ["I:VIX","I:VIX1D"]:
    d,e=get(f"https://api.polygon.io/v2/aggs/ticker/{ix}/range/1/minute/2026-06-01/2026-06-10?limit=3")
    print(f"{ix}: {e or ('OK '+str(len((d or {}).get('results') or [])))}")
