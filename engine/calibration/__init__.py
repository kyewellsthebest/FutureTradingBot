"""SimFillModel calibration. Ingests real Tradovate fills, computes
empirical slippage / latency / fill-rate distributions, updates
SimFillParams so the backtest matches live behaviour.

Standard workflow:
  1. Run live for N days, collect fills (the engine logs each Fill with
     intended_price, fill_price, latency_ms, slippage_pts).
  2. python -m engine.calibration.run_calibration
     - reads the fill log
     - computes empirical distribution per regime (calm/fast/news)
     - writes a calibrated SimFillParams to engine/calibration/params.json
  3. Reload bot; the SimFillModel now uses the calibrated params.
  4. Re-run backtest; compare predicted vs actual P&L. Should match
     within statistical noise.

This file is the CONTRACT. The actual calibration runner is in
run_calibration.py.
"""
