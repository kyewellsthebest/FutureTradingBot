"""Market economics for MEGA2 honest hunt. All figures are for the contract
the user could actually trade on a ~$4k Tradovate account (micro where one
exists, full-size otherwise). PV = $ per 1.0 of quoted price, tick = minimum
increment, comm = round-trip commission+fees, margin = intraday margin est.
afford = tradable on a $4k account without dominating margin."""

# root: (pv, tick, comm_rt, traded_as, margin_est, afford)
ECON = {
    # Nasdaq re-admitted 2026-08-02 by user directive. MNQ has the best
    # volatility-to-cost ratio of anything tradable here: tick $0.50 against a
    # ~$19.66 average 5-min move = 10.2x, vs 3.7x for MES and 0.9x for ZB.
    "NQ":  (2.0,      0.25,       1.42, "MNQ",  100.0,  True),
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

# ---------------------------------------------------------------------------
# COMMISSION, BUILT FROM COMPONENTS RATHER THAN GUESSED
#
# The comm_rt figures above were round-turn estimates and several were badly
# overstated -- \$1.80 for MES/M2K/MYM and \$2.20 for MGC where the real number
# is nearer \$1.32, and \$2.60 for MHG against about \$1.52.
#
# Tradovate's broker commission per side, per the user's plan screen:
#     free plan      \$0.39 / micro
#     \$99 a month    \$0.29 / micro
#     \$1,499 lifetime \$0.09 / micro
# On top sits exchange + clearing + NFA, which the plan does not change.
#
# Set COMM_PLAN=free|monthly|lifetime to price any study at that tier.
# ---------------------------------------------------------------------------
import os as _os

BROKER_SIDE = {"free": 0.39, "monthly": 0.29, "lifetime": 0.09}
PLAN = _os.environ.get("COMM_PLAN", "free").lower()
_BRK = BROKER_SIDE.get(PLAN, 0.39)

# exchange + clearing + NFA per side, by traded contract
_FEES = {
    "MNQ": 0.27, "MES": 0.27, "M2K": 0.27, "MYM": 0.27,
    "MGC": 0.27, "MHG": 0.37, "MCL": 0.52, "MNG": 0.52,
    "M6E": 0.26, "M6B": 0.26, "M6A": 0.26,
    "MBT": 2.52, "MET": 0.22,
}


def comm_rt(traded):
    """Round-turn cost for one contract at the configured plan."""
    return 2.0 * (_BRK + _FEES.get(traded, 0.60))


# Rewrite the table's comm figures from the component model, leaving
# full-size contracts (no micro available) on their original estimates.
ECON = {k: ((v[0], v[1], round(comm_rt(v[3]), 2), v[3], v[4], v[5])
            if v[3] in _FEES else v)
        for k, v in ECON.items()}

# SI/SIL remain excluded (margin). NQ re-admitted 2026-08-02.

TRAIN_END = "2026-05-22T00:00:00Z"   # same split every campaign this session
OOS10     = "2026-05-18T00:00:00Z"
OOS3      = "2026-07-06T00:00:00Z"
