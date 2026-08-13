"""What exactly does $125 of Databento credit buy for the maker question?

Prices every schema x window combination BEFORE spending anything: the
metadata endpoints are free, and the answer decides the purchase. The maker
assumption (+$0.355/trade front-of-queue on MNQ) lives at the top of the
book, so mbp-1 might already be enough; mbp-10 gives level context; mbo is
the full per-order feed and the only one that shows exact queue position.

Runs on GitHub Actions -- the research container's egress proxy blocks
databento.com.
"""
import os
import sys

import databento as db

KEY = os.environ.get("DATABENTO_KEY")
if not KEY:
    sys.exit("DATABENTO_KEY not set")
c = db.Historical(KEY)

DATASET = "GLBX.MDP3"
# NQU6 is the front month across July 2026; ESU6 priced for comparison.
WINDOWS = [
    ("2026-07-27", "2026-08-01", "1 week (Jul 27-31)"),
    ("2026-07-01", "2026-08-01", "July 2026"),
    ("2026-06-01", "2026-08-01", "Jun+Jul 2026"),
]
SYMS = ["NQU6", "MNQU6", "ESU6"]

print(f"{'symbol':<7} {'schema':<7} {'window':<20} {'GB':>8} {'cost':>10}")
print("-" * 58)
for sym in SYMS:
    for schema in ("mbp-1", "mbp-10", "mbo", "trades"):
        for s, e, label in WINDOWS:
            try:
                size = c.metadata.get_billable_size(
                    dataset=DATASET, symbols=[sym], stype_in="raw_symbol",
                    schema=schema, start=s, end=e)
                cost = c.metadata.get_cost(
                    dataset=DATASET, symbols=[sym], stype_in="raw_symbol",
                    schema=schema, start=s, end=e)
                print(f"{sym:<7} {schema:<7} {label:<20} "
                      f"{size/1e9:>7.2f}G {cost:>9.2f}$", flush=True)
            except Exception as exc:                             # noqa: BLE001
                print(f"{sym:<7} {schema:<7} {label:<20} "
                      f"error: {str(exc)[:60]}", flush=True)
print("-" * 58)
print("metadata queries are free; nothing was purchased.")
