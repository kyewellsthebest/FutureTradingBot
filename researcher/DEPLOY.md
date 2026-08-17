# Deploying the research bot on Railway — step by step

The research bot is a **second Railway service off this same repo**. The
trading bot's service runs `python live_runner.py`; this one runs
`python research_service.py`, which searches continuously in a
background thread and serves a console on `$PORT`.

Running two services from one repo with different start commands is the
supported Railway pattern —
[Deploying a Monorepo](https://docs.railway.com/deployments/monorepo)
and [Set a Start Command](https://docs.railway.com/guides/start-command).

---

## Step 0 — check you are not about to replace the trading bot

**Do this first.** A new service created from this repo is named
`FutureTradingBot`, and so is the existing trading bot's service. They
look identical in the settings panel.

Open the project canvas (the graph icon, top left). Count the service
boxes:

- **Two or more boxes** → make sure the one you are editing is the *new*
  one, not the bot. Click each and check its Custom Start Command:
  the bot's says `python live_runner.py`.
- **One box only** → you are editing the trading bot's service.
  Deploying will stop the bot and replace it with the researcher. Back
  out and create a new service instead (Step 1).

---

## Step 1 — create the service

On the project canvas: **`⌘K` / `Ctrl+K`** → **Deploy from GitHub repo**
→ `kyewellsthebest/FutureTradingBot`. Or right-click the canvas → **New
Service**.

Then in the new service → **Settings** → **Source**:

- **Branch:** `claude/hello-vc2ivo`

Docs: [The Basics](https://docs.railway.com/overview/the-basics)

---

## Step 2 — point the service at `railway.research.json`

**Settings** → **Config-as-code** → **Railway Config File** → **Add File
Path**:

```
railway.research.json
```

**This step, not the Custom Start Command.** `railway.json` in the repo
root sets the *trading bot's* start command, and
[Railway's docs](https://docs.railway.com/config-as-code) are explicit
that *"configuration defined in code will always override values from
the dashboard."* So setting Custom Start Command to
`python research_service.py` does nothing — the service still runs
`python live_runner.py`, which on a service without Tradovate
credentials dies, and the domain returns **"Application failed to
respond."**

`railway.research.json` carries the correct start command, healthcheck
path and restart policy together:

```json
{
  "deploy": {
    "startCommand": "python research_service.py",
    "healthcheckPath": "/api/health",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10,
    "healthcheckTimeout": 300
  }
}
```

Because it sets the healthcheck too, **Step 5 becomes unnecessary** —
but a Custom Start Command left in the dashboard is harmless, since the
file wins either way.

To confirm it took: on the deployment details page, settings that came
from a config file show a small **file icon**. Hover it to see which
part of the file they came from.

---

## Step 3 — attach a volume  ← the one that actually matters

On the project canvas: **`⌘K` / `Ctrl+K`** → **New Volume** (or
right-click the canvas → **Volume**). Select **this service** and set:

- **Mount path:** `/data`

**Leading slash required.** The field turns red for `Data` or `data` —
Railway needs an absolute path. `/data` is valid.

That is all. Railway sets `RAILWAY_VOLUME_MOUNT_PATH` automatically at
runtime, and the service reads it and puts the ledger at
`/data/research`. **You do not need to set `RESEARCH_DIR`.**

Docs: [Using Volumes](https://docs.railway.com/volumes) ·
[Volumes reference](https://docs.railway.com/reference/volumes)

Two things worth knowing from those docs:

- Volumes mount at container **start**, not at build. Anything written
  during build does not land on the volume.
- A volume attach triggers a redeploy.

### Why this step is not optional

Railway's container filesystem is wiped on every deploy and restart. The
safety property of a searcher that never stops is that it counts its own
trials and raises its significance bar as `√(2 ln N)`. Lose the ledger
and:

- the trial count resets to zero
- the bar drops from ~5σ back to 3.0σ
- it starts reporting as *discoveries* the noise it had already ruled out

That failure does not degrade this system, it **inverts** it — same
code, same console, now efficiently fooling you. Two independent guards
exist because of that:

- `check_storage()` warns on boot and on the console if no volume is
  attached, or if a volume is attached but the ledger is being written
  outside it.
- `check_state_loss()` keeps a **high-water trial mark** and compares on
  every event. This is the guard that actually catches a wipe, because
  it does not depend on any assumption about paths. Verified against a
  simulated deploy wipe: it caught `6,108 → 518` and raised the alert.

If the state-loss banner appears, the searcher is still working — but
treat anything it reports as unproven until the trial count climbs back
past the mark shown.

---

## Step 4 — generate a domain

**Settings** → **Networking** → **Public Networking** → **Generate
Domain**.

Without this there is no URL and you cannot see the dashboard at all.

Railway auto-detects the port. The service listens on `0.0.0.0:$PORT`,
which is what Railway requires. If it ever asks for a target port, or
you see *"Application failed to respond"*, set the `PORT` variable
explicitly — but try without first.

Docs: [Public Networking](https://docs.railway.com/public-networking) ·
[Working with Domains](https://docs.railway.com/networking/domains/working-with-domains)
· [Application Failed to Respond](https://docs.railway.com/networking/troubleshooting/application-failed-to-respond)

---

## Step 5 — healthcheck (already handled by Step 2)

`railway.research.json` sets `healthcheckPath: /api/health` with a
300-second timeout, so there is nothing to do here. Setting it in the
dashboard as well is harmless.

The generous timeout is deliberate: the search thread reads 24 CSVs and
a 1.59M-row parquet at startup, and pandas holds the GIL in chunks while
it does. Measured on a cold start, `/api/health` answers in **1 second**
and then in **2-28 ms** while the search runs flat out, so the timeout
should never be reached -- it is headroom for a slower container, not a
workaround.

---

## Step 6 — deploy

Hit **Deploy**. Then **Deployments** → click the active deploy → **View
Logs**. You are looking for:

```
[research_service] console on :8080, storage /data/research
{"msg": "boot", "trials": 0, "bar": 3.0, ...}
{"msg": "loaded_tier1", "markets": [...], "n": 10, ...}
```

If you instead see `[storage] NO VOLUME IS ATTACHED`, go back to Step 3.

A full cycle takes roughly two minutes on your 8 vCPU / 8 GB.

---

## No secrets are needed

Leave the Variables tab empty. The researcher reads market data
committed in the repo and has no broker credentials and no code path
that could place an order.

If Railway copied the bot's variables into this service, that is
harmless — nothing in `research_service.py` reads them.

---

## What you should see on the console

**Data tiers** — three rows, all green:

| tier | what | source |
|---|---|---|
| 1 | breadth · 5-minute bars, 10 markets | `data/polygon/` (committed) |
| 2 | depth · NQ intraday bars, 8 quarters | `data/research_bars/` (committed, 15 MB) |
| 3 | book · NQ top-of-book, 1-second | `data/depth/` (committed) |

If tier 2 shows **ABSENT**, `data/research_bars/` did not make it into
the deploy. The raw 4.7 GB tick data is gitignored and never reaches
Railway; `researcher/build_deep_bars.py` resamples it to 15 MB, which is
what gets committed. Run that where the raw ticks live, commit its
output, redeploy.

**Zero survivors is the expected output and it is a real result.** The
headline states how many specific ideas have been ruled out, because
that is what the run bought. A searcher that reported a finding on day
one would be telling you something false — this repo has already
measured what happens when a search runs until something looks good:
ledger #19, 1.38 billion configurations with a *measured negative*
return to searching harder.

The two panels showing genuine learning:

- **Failure profiles** — not "it lost" but *why*. `cost_bound` is the
  valuable one: right direction, move smaller than the round trip. It
  licenses longer holds, because cost is fixed per trade while move size
  grows as √time. That is arithmetic, not a fitted preference.
- **Self-calibration** — every vault touch pairs a predicted strength
  with a realised one; the median ratio is the system's own overfitting
  coefficient and divides into the bar. It reads `UNKNOWN` until
  candidates actually reach the vault, and deliberately does not default
  to 1.0 — a calibration quietly claiming "we do not overfit" would be
  the most dangerous number on the page.

---

## Controls

| route | what it does |
|---|---|
| `/` | the console |
| `/api/state` | ledger, learning, tiers, storage, verdict |
| `/api/feed` | last 200 research events |
| `/api/health` | liveness (Railway healthcheck) |
| `POST /api/stop` | stop searching |
| `POST /api/start` | resume |

The stop button writes `RESEARCH_STOP` into the ledger directory. The
runner checks for it between every hypothesis, so it stops in seconds
rather than at the end of a cycle. On a volume that file **survives a
restart**, which is intended: stopped means stopped, not "stopped until
Railway redeploys".

---

## Why the GitHub Actions workflow has no schedule

`.github/workflows/researcher.yml` is `workflow_dispatch` only. Two
searchers on timers would keep two separate ledgers, each counting only
its own trials, so both bars would sit lower than the combined search
justifies — and the pair would manufacture a false positive faster than
either alone. Multiple testing does not care which machine did the
testing. Railway is the continuous searcher; Actions is a manual burst.
