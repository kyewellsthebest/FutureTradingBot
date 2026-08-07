tick-native simulation, 8 NQ contracts
impulse 8.0pt over 400 prints, 20% retrace, stop 6.0pt, target 12.0pt

  NQH5: 24,827,411 prints
  NQH6: 21,416,028 prints
  NQM5: 25,222,233 prints
  NQM6: 24,740,742 prints
  NQU4: 25,188,096 prints
  NQU5: 18,720,266 prints
  NQZ4: 20,179,829 prints
  NQZ5: 23,801,630 prints

         exit rule      arm   trades   win%   $/trade     +/-     HOLD  STRAT-RND

--- queue 0 ---
        fixed 6/12    strat   58,437  33.5%    0.0671  0.0703    0.054   +0.2040
                     random   58,125  33.0%   -0.1369  0.0702   -0.142 (2.1 sigma)
   trail 2 after 2    strat   58,437  66.8%    0.1023  0.0334    0.048   +0.0484
                     random   58,125  65.7%    0.0539  0.0351    0.126 (1.0 sigma)
   trail 2 after 4    strat   58,437  59.9%    0.1101  0.0434    0.125   +0.1109
                     random   58,125  58.8%   -0.0008  0.0450    0.129 (1.8 sigma)
   trail 2 after 8    strat   58,437  43.1%    0.1033  0.0589    0.140   +0.1487
                     random   58,125  42.2%   -0.0454  0.0599    0.040 (1.8 sigma)
   trail 3 after 2    strat   58,437  50.9%    0.1062  0.0371    0.032   +0.0528
                     random   58,125  50.1%    0.0535  0.0389    0.107 (1.0 sigma)
   trail 3 after 4    strat   58,437  59.9%    0.0903  0.0457    0.075   +0.1071
                     random   58,125  58.8%   -0.0168  0.0472    0.087 (1.6 sigma)
   trail 3 after 8    strat   58,437  43.1%    0.0709  0.0601    0.091   +0.1448
                     random   58,125  42.2%   -0.0739  0.0610    0.015 (1.7 sigma)
   trail 4 after 2    strat   58,437  44.3%    0.0745  0.0416   -0.007   +0.0881
                     random   58,125  43.5%   -0.0136  0.0430   -0.006 (1.5 sigma)
  NQU5: 18,720,266 prints
  NQZ4: 20,179,829 prints
  NQZ5: 23,801,630 prints
--- queue 0 ---
   trail 4 after 4    strat   58,437  56.7%    0.0505  0.0485    0.017   +0.1189
                     random   58,125  55.5%   -0.0684  0.0499    0.010 (1.7 sigma)
   trail 4 after 8    strat   58,437  43.1%    0.0513  0.0617    0.040   +0.1723
                     random   58,125  42.2%   -0.1210  0.0624   -0.019 (2.0 sigma)
   trail 6 after 2    strat   58,437  38.0%    0.0733  0.0529   -0.100   +0.1399
                     random   58,125  37.5%   -0.0666  0.0538    0.012 (1.9 sigma)
   trail 6 after 4    strat   58,437  42.0%    0.0880  0.0568   -0.047   +0.1726
                     random   58,125  41.3%   -0.0847  0.0576   -0.009 (2.1 sigma)
   trail 6 after 8    strat   58,437  43.1%    0.0389  0.0661   -0.005   +0.1728
                     random   58,125  42.2%   -0.1339  0.0669   -0.076 (1.8 sigma)
queue 0 is the touch-fill fantasy every backtest here has used.
STRAT-RND is the whole answer: the same exit rule, the same costs, the
same holds, entries that carry information against entries that do not.
A trailing stop that only beats zero has beaten nothing.
