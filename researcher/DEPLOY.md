# Deploying the research bot on Railway

A **second Railway service off this same repo**. The trading bot's
service runs `python live_runner.py`; this one runs
`python research_service.py`, which searches continuously in a
background thread and serves a console on `$PORT`.

## Steps

1. **New service** in the same Railway project → deploy from this repo,
   branch `claude/hello-vc2ivo`.

2. **Override the start command** (Settings → Deploy → Custom Start
   Command):

   ```
   python research_service.py
   ```

   This is required. `railway.json` in the repo root sets the *bot's*
   start command, and without the override the second service would boot
   a second copy of the trading bot.

3. **Add a volume** (Settings → Volumes), mount path `/data`.

4. **Set the environment variable:**

   ```
   RESEARCH_DIR = /data/research
   ```

5. **Healthcheck path:** `/api/health`

No secrets are needed. The searcher reads local market data from the
repo and never places an order — it has no broker credentials and no
code path that could.

## Step 3 and 4 are not optional, and here is why

Railway's container filesystem is **ephemeral**: every deploy and every
restart wipes it. The safety property of a searcher that never stops is
that it counts its own trials and raises its own significance bar as
`√(2 ln N)`. Lose the ledger and:

- the trial count resets to zero
- the bar drops from ~5σ back to 3.0σ
- the searcher starts reporting as *discoveries* the noise it had
  already ruled out

A quiet state loss does not degrade this system, it **inverts** it. It
would go from a machine that refuses to fool you into a machine that
fools you efficiently, and it would look identical while doing it.

So there are two independent guards:

- `check_storage()` warns on boot and on the console if `RESEARCH_DIR`
  is not an explicit path outside the app directory.
- `check_state_loss()` keeps a **high-water trial mark** and compares
  against it on every event. This is the one that actually catches a
  wipe, because it does not depend on guessing whether storage is
  durable. Verified against a simulated Railway deploy wipe: it caught
  `6,108 → 518` and raised the alert.

If you see the state-loss banner, the searcher is still working — but
treat anything it reports as unproven until the trial count climbs back
past the high-water mark shown.

## Console

| route | what it does |
|---|---|
| `/` | the console |
| `/api/state` | ledger, learning, storage, verdict |
| `/api/feed` | last 200 research events |
| `/api/health` | liveness (Railway healthcheck) |
| `POST /api/stop` | stop searching (takes effect within seconds) |
| `POST /api/start` | resume |

The stop button writes `RESEARCH_STOP` into `RESEARCH_DIR`. The runner
checks for it between every hypothesis, so it stops in seconds rather
than at the end of a cycle. On a mounted volume that file **survives a
restart**, which is intended: stopped means stopped, not "stopped until
Railway redeploys".

## Reading the console

**Zero survivors is the expected output and it is a real result.** The
headline says how many specific ideas have been ruled out, because that
is what the run bought. A searcher that reported a finding on day one
would be telling you something false — this repo has already measured
what happens when a search is allowed to keep going until something
looks good: hypothesis ledger #19, 1.38 billion configurations with a
*measured negative* return to searching harder.

The two panels that show genuine learning:

- **Failure profiles.** Not "it lost" but *why*. `cost_bound` is the
  valuable one — right direction, move smaller than the round trip —
  and it licenses longer holds, because cost is fixed per trade while
  move size grows as √time. That is arithmetic, not a fitted preference.
- **Self-calibration.** Every vault touch pairs a predicted strength
  with a realised one; the median ratio is the system's own overfitting
  coefficient and it divides into the bar. It reads `UNKNOWN` until
  candidates have actually reached the vault, and deliberately does not
  default to 1.0 — a calibration quietly claiming "we do not overfit"
  would be the most dangerous number on the page.

## Why the GitHub Actions workflow has no schedule

`.github/workflows/researcher.yml` is `workflow_dispatch` only. Two
searchers on timers would keep two separate ledgers, each counting only
its own trials, so both bars would sit lower than the combined search
justifies — and the pair would manufacture a false positive faster than
either alone. Multiple testing does not care which machine did the
testing. Railway is the continuous searcher; Actions is a manual burst.
