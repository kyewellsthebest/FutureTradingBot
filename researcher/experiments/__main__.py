"""`python -m researcher.experiments` -- run the queue's self-test.

A package cannot be executed through the `if __name__ == "__main__"`
block in its own `__init__.py`, so the documented entry point needs
this file to actually exist.
"""
from researcher.experiments import selftest

f = selftest()
print("\nexperiments selftest:", "PASS" if not f else f"FAIL {f}")
raise SystemExit(1 if f else 0)
