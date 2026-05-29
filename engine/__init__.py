"""Shared execution engine for futures scalping bot.

DESIGN PRINCIPLE: the same code runs in backtest and live. There is ONE
strategy implementation, ONE fill model interface, ONE risk engine, ONE
runtime. Backtest and live differ only in:
  - Who feeds bars to the runtime (DataFrame iteration vs live stream)
  - Which FillModel implementation is plugged in (SimFillModel vs
    TradovateFillModel)

Anything more than that is a divergence bug waiting to happen.
"""
