"""Market economics for MEGA2 honest hunt. All figures are for the contract
the user could actually trade on a ~$4k Tradovate account (micro where one
exists, full-size otherwise). PV = $ per 1.0 of quoted price, tick = minimum
increment, comm = round-trip commission+fees, margin = intraday margin est.
afford = tradable on a $4k account without dominating margin."""

# root: (pv, tick, comm_rt, traded_as, margin_est, afford)
ECON = {
    "ES":  (5.0,      0.25,       1.80, "MES",  50.0,   True),
    "RTY": (5.0,      0.10,       1.80, "M2K",  50.0,   True),
    "YM":  (0.5,      1.0,        1.80, "MYM",  50.0,   True),
    "GC":  (10.0,     0.10,       2.20, "MGC",  250.0,  True),
    "CL":  (100.0,    0.01,       2.20, "MCL",  250.0,  True),
    "NG":  (2500.0,   0.001,      2.60, "MNG",  400.0,  True),
    "HG":  (2500.0,   0.0005,     2.60, "MHG",  400.0,  True),
    "ZB":  (1000.0,   0.03125,    4.50, "ZB",   800.0,  True),
    "ZN":  (1000.0,   0.015625,   4.50, "ZN",   700.0,  True),
    "ZF":  (1000.0,   0.0078125,  4.50, "ZF",   600.0,  True),
    "ZT":  (2000.0,   0.0078125,  4.50, "ZT",   500.0,  True),
    "6E":  (12500.0,  0.0001,     1.60, "M6E",  300.0,  True),
    "6B":  (6250.0,   0.0001,     1.60, "M6B",  300.0,  True),
    "6A":  (10000.0,  0.0001,     1.60, "M6A",  300.0,  True),
    "6J":  (12500000.0, 0.0000005, 3.20, "6J",  2800.0, False),
    "MBT": (0.1,      5.0,        2.20, "MBT",  900.0,  True),
    "ETH": (0.1,      0.25,       2.20, "MET",  500.0,  True),
    "ZC":  (50.0,     0.25,       4.00, "ZC",   1200.0, True),
    "ZW":  (50.0,     0.25,       4.00, "ZW",   1700.0, True),
    "ZS":  (50.0,     0.25,       4.00, "ZS",   2200.0, False),
    "HO":  (42000.0,  0.0001,     3.50, "HO",   7000.0, False),
    "RB":  (42000.0,  0.0001,     3.50, "RB",   7500.0, False),
}
# NQ/MNQ and SI/SIL are permanently excluded by user directive.

TRAIN_END = "2026-05-22T00:00:00Z"   # same split every campaign this session
OOS10     = "2026-05-18T00:00:00Z"
OOS3      = "2026-07-06T00:00:00Z"
