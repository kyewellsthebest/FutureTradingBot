"""Market structure engine: computes session-level price reference points
(PDH/PDL/POC/VAH/VAL/OR/ON/VWAP) from existing 1-min bars. NO external
data needed -- pure computation off the bars the bot already has.

The structure points are what gives trades CONTEXT. Bots that respect
these levels for filtering / sizing systematically outperform bots that
treat every bar identically.
"""
