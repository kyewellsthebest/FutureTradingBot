"""Strategy implementations. Each Strategy is a PURE FUNCTION over bar
history -- no I/O, no side effects, no state held between calls.

State (pending setups, active trades) lives in the Runtime, not the
strategy. This is the rule that makes backtest = live possible.
"""
