# Strategy Discovery — Full Report

Generated: 2026-04-29T04:27:09.881360+00:00

## Sources

  - **validated_v3_8yr.json**: 12 patterns validated, perms=500, MC=10000
  - **validated_v3_8yr_wide.json**: missing
  - **validated_v3_xa.json**: missing
  - **validated_long_rr25.json**: missing
  - **validated_long_rr30.json**: missing
  - **validated_long_rr40.json**: missing
  - **validated_v3_long_top60.json**: 60 patterns validated, perms=200, MC=10000
  - **validated_short_rr20.json**: 82 patterns validated, perms=200, MC=5000
  - **validated_short_rr25.json**: 60 patterns validated, perms=200, MC=5000
  - **validated_short_rr30.json**: 50 patterns validated, perms=200, MC=5000
  - **validated_short_rr40.json**: 40 patterns validated, perms=200, MC=5000
  - **validated_es.json**: 15 patterns validated, perms=300, MC=5000
  - **validated_rty.json**: 4 patterns validated, perms=300, MC=5000

## Bucketing rules

  - **Tier A** (live, gold standard): WR ≥ 60% AND R:R ≥ 1:2 AND passes ALL 5 rigor tests
    (EV, 500-permutation, walk-forward CPCV, 10k Monte-Carlo, ±20% sensitivity)
  - **Tier B** (live, lower-WR): positive EV AND passes ≥3/5 tests AND walk-forward + permutation pass
    Sub-60% WR but profitable due to 1:2 R:R; sized at 5 MNQ same as Tier A
  - **Reject**: negative EV, or fails permutation/walk-forward

## Tier A — Live-ready (12 strategies)

| Name | Side | WR | PF | Trades | Net P&L | Perm p |
|---|---|---|---|---|---|---|
| V3_SHORT_S20T50_141 | SHORT | 62.4% | 3.25 | 7634 | $+1,422,770 | 0.0050 |
| V3_LONG_S20T50_55 | LONG | 60.8% | 2.83 | 4497 | $+721,368 | 0.0050 |
| V3_SHORT_S18T36_68 | SHORT | 60.4% | 2.46 | 2335 | $+270,295 | 0.0050 |
| V3_SHORT_S15T30_05 | SHORT | 60.3% | 2.39 | 2746 | $+264,845 | 0.0020 |
| V3_SHORT_S20T40_87 | SHORT | 65.4% | 3.06 | 1018 | $+163,365 | 0.0050 |
| V3_SHORT_S18T36_74 | SHORT | 63.7% | 2.73 | 1021 | $+125,222 | 0.0050 |
| V3_SHORT_S15T30_57 | SHORT | 68.3% | 3.36 | 691 | $+90,080 | 0.0050 |
| V3_SHORT_S20T40_246 | SHORT | 67.4% | 3.71 | 524 | $+78,638 | 0.0033 |
| V3_SHORT_S20T40_241 | SHORT | 73.4% | 4.34 | 368 | $+73,965 | 0.0100 |
| V3_SHORT_S10T20_37 | SHORT | 62.8% | 1.91 | 1936 | $+69,745 | 0.0050 |
| V3_LONG_S15T30_69 | LONG | 65.4% | 2.53 | 433 | $+35,498 | 0.0033 |
| V3_SHORT_S10T20_245 | SHORT | 61.6% | 2.21 | 352 | $+20,118 | 0.0033 |

## Tier B — Watchlist (198 strategies)

| Name | Side | WR | PF | Trades | Net P&L | Tests |
|---|---|---|---|---|---|---|
| V3_LONG_S20T60_07 | LONG | 45.8% | 2.01 | 24131 | $+3,033,940 | 5/5 |
| V3_LONG_S20T50_05 | LONG | 47.3% | 1.78 | 23825 | $+2,220,895 | 5/5 |
| V3_SHORT_S15T60_231 | SHORT | 88.6% | 23.99 | 3836 | $+1,770,490 | 4/5 |
| V3_SHORT_S15T60_232 | SHORT | 38.6% | 2.01 | 14387 | $+1,606,525 | 5/5 |
| V3_SHORT_S15T37_131 | SHORT | 41.9% | 1.43 | 33525 | $+1,489,690 | 5/5 |
| V3_SHORT_S20T50_142 | SHORT | 45.5% | 1.73 | 15075 | $+1,364,422 | 5/5 |
| V3_SHORT_S20T50_144 | SHORT | 65.6% | 3.68 | 6540 | $+1,312,990 | 4/5 |
| V3_LONG_S20T60_59 | LONG | 56.7% | 2.83 | 6626 | $+1,184,098 | 5/5 |
| V3_SHORT_S20T50_143 | SHORT | 51.6% | 2.22 | 8615 | $+1,154,248 | 5/5 |
| V3_SHORT_S15T45_192 | SHORT | 41.1% | 1.65 | 16541 | $+1,131,528 | 5/5 |
| V3_SHORT_S20T40_77 | SHORT | 47.2% | 1.49 | 19013 | $+1,120,380 | 5/5 |
| V3_SHORT_S18T36_67 | SHORT | 47.1% | 1.46 | 20957 | $+1,070,812 | 5/5 |
| V3_LONG_S15T37_10 | LONG | 45.4% | 1.56 | 17616 | $+958,618 | 5/5 |
| V3_SHORT_S15T60_234 | SHORT | 35.8% | 1.72 | 11338 | $+943,660 | 5/5 |
| V3_LONG_S20T50_21 | LONG | 73.7% | 5.51 | 3503 | $+935,482 | 4/5 |
| V3_SHORT_S15T60_238 | SHORT | 95.0% | 68.21 | 2318 | $+932,200 | 4/5 |
| V3_SHORT_S15T60_235 | SHORT | 53.9% | 3.40 | 4476 | $+878,022 | 5/5 |
| V3_LONG_S20T50_12 | LONG | 74.8% | 5.67 | 3229 | $+853,558 | 4/5 |
| V3_LONG_S20T60_37 | LONG | 40.3% | 1.62 | 9653 | $+821,432 | 5/5 |
| V3_SHORT_S15T60_239 | SHORT | 37.6% | 1.75 | 9605 | $+805,250 | 5/5 |
| V3_LONG_S20T60_32 | LONG | 39.8% | 1.58 | 9677 | $+773,005 | 5/5 |
| V3_SHORT_S15T60_233 | SHORT | 57.3% | 3.76 | 3772 | $+766,650 | 4/5 |
| V3_LONG_S20T50_08 | LONG | 49.3% | 2.00 | 5808 | $+668,592 | 5/5 |
| V3_SHORT_S15T45_191 | SHORT | 52.4% | 2.39 | 5125 | $+600,482 | 5/5 |
| V3_LONG_S20T60_11 | LONG | 42.1% | 1.77 | 5844 | $+592,968 | 5/5 |
| V3_LONG_S20T50_23 | LONG | 45.6% | 1.71 | 6623 | $+584,910 | 5/5 |
| V3_SHORT_S15T37_133 | SHORT | 69.3% | 4.38 | 3389 | $+575,510 | 4/5 |
| V3_SHORT_S20T50_145 | SHORT | 69.8% | 4.62 | 2420 | $+571,192 | 4/5 |
| V3_LONG_S15T45_31 | LONG | 64.7% | 4.21 | 2781 | $+558,615 | 4/5 |
| V3_SHORT_S20T50_146 | SHORT | 42.8% | 1.57 | 7447 | $+555,325 | 5/5 |
| V3_LONG_S20T60_34 | LONG | 69.0% | 5.44 | 1760 | $+550,800 | 4/5 |
| V3_SHORT_S20T40_78 | SHORT | 51.9% | 1.81 | 6159 | $+542,585 | 5/5 |
| V3_SHORT_S20T50_148 | SHORT | 57.6% | 2.30 | 4535 | $+529,908 | 5/5 |
| V3_SHORT_S15T45_197 | SHORT | 50.0% | 2.14 | 5259 | $+526,455 | 5/5 |
| V3_SHORT_S20T50_150 | SHORT | 42.6% | 1.50 | 7786 | $+509,550 | 5/5 |
| V3_LONG_S15T45_09 | LONG | 39.9% | 1.50 | 9432 | $+506,332 | 5/5 |
| V3_LONG_S15T60_15 | LONG | 39.2% | 2.01 | 4433 | $+491,462 | 5/5 |
| V3_SHORT_S12T48_221 | SHORT | 41.9% | 1.96 | 5935 | $+489,930 | 5/5 |
| V3_SHORT_S20T50_149 | SHORT | 73.5% | 5.60 | 1890 | $+465,715 | 4/5 |
| V3_SHORT_S20T50_147 | SHORT | 42.2% | 1.54 | 6328 | $+457,138 | 5/5 |
| V3_LONG_S20T60_20 | LONG | 78.5% | 8.76 | 1209 | $+455,892 | 4/5 |
| V3_LONG_S20T50_43 | LONG | 50.0% | 2.02 | 3915 | $+454,845 | 5/5 |
| V3_SHORT_S20T40_79 | SHORT | 77.3% | 5.87 | 1956 | $+443,162 | 4/5 |
| V3_LONG_S15T37_06 | LONG | 42.9% | 1.42 | 9829 | $+424,702 | 5/5 |
| V3_SHORT_S20T40_80 | SHORT | 48.1% | 1.54 | 6486 | $+410,695 | 5/5 |
| V3_SHORT_S15T37_132 | SHORT | 56.6% | 2.52 | 3470 | $+406,522 | 5/5 |
| V3_LONG_S20T60_27 | LONG | 70.3% | 5.52 | 1345 | $+405,268 | 4/5 |
| V3_SHORT_S15T45_195 | SHORT | 68.1% | 4.86 | 1892 | $+404,398 | 4/5 |
| V3_SHORT_S15T45_199 | SHORT | 42.5% | 1.74 | 5230 | $+398,982 | 5/5 |
| V3_SHORT_S15T60_240 | SHORT | 38.4% | 1.97 | 3286 | $+353,950 | 5/5 |
| V3_SHORT_S15T37_135 | SHORT | 49.7% | 1.84 | 4777 | $+348,598 | 5/5 |
| V3_SHORT_S12T48_224 | SHORT | 54.5% | 3.33 | 2188 | $+339,438 | 4/5 |
| V3_LONG_S15T30_04 | LONG | 96.7% | 46.73 | 1237 | $+337,490 | 4/5 |
| V3_SHORT_S15T45_196 | SHORT | 67.2% | 4.74 | 1619 | $+333,802 | 4/5 |
| V3_LONG_S15T45_49 | LONG | 70.5% | 5.17 | 1462 | $+318,812 | 4/5 |
| V3_SHORT_S12T30_122 | SHORT | 95.6% | 41.83 | 1159 | $+303,570 | 4/5 |
| V3_LONG_S20T50_61 | LONG | 72.6% | 5.27 | 1126 | $+293,090 | 4/5 |
| V3_SHORT_S12T48_228 | SHORT | 46.7% | 2.48 | 2540 | $+293,080 | 4/5 |
| V3_LONG_S12T36_16 | LONG | 93.7% | 34.43 | 917 | $+290,820 | 4/5 |
| V3_SHORT_S15T45_198 | SHORT | 48.9% | 1.85 | 3646 | $+274,378 | 5/5 |
| V3_SHORT_S20T40_83 | SHORT | 96.4% | 168.38 | 784 | $+264,465 | 4/5 |
| V3_SHORT_S12T36_188 | SHORT | 42.8% | 1.51 | 5852 | $+249,392 | 5/5 |
| V3_SHORT_S12T30_125 | SHORT | 76.1% | 5.65 | 1566 | $+242,308 | 4/5 |
| V3_SHORT_S10T40_214 | SHORT | 48.6% | 2.39 | 2568 | $+233,790 | 5/5 |
| V3_SHORT_S12T48_230 | SHORT | 60.3% | 4.26 | 1206 | $+226,495 | 4/5 |
| V3_SHORT_S12T30_126 | SHORT | 47.5% | 1.58 | 5117 | $+223,292 | 5/5 |
| V3_SHORT_S20T40_82 | SHORT | 99.3% | 393.85 | 575 | $+214,105 | 4/5 |
| V3_SHORT_S20T40_81 | SHORT | 97.4% | 62.51 | 575 | $+212,368 | 4/5 |
| V3_LONG_S12T30_38 | LONG | 67.2% | 3.79 | 1552 | $+212,208 | 4/5 |
| V3_SHORT_S10T40_218 | SHORT | 55.6% | 3.06 | 1821 | $+210,742 | 4/5 |
| V3_SHORT_S12T36_186 | SHORT | 60.3% | 3.29 | 1586 | $+208,652 | 4/5 |
| V3_SHORT_S12T48_226 | SHORT | 63.1% | 4.90 | 985 | $+208,585 | 4/5 |
| V3_SHORT_S20T40_88 | SHORT | 97.5% | 245.05 | 685 | $+207,445 | 4/5 |
| V3_LONG_S15T37_64 | LONG | 49.7% | 1.92 | 2488 | $+206,040 | 5/5 |
| V3_LONG_S10T30_35 | LONG | 40.7% | 1.44 | 6060 | $+204,325 | 5/5 |
| V3_SHORT_S10T30_173 | SHORT | 74.8% | 6.17 | 1253 | $+202,340 | 4/5 |
| V3_SHORT_S12T30_124 | SHORT | 97.2% | 64.84 | 739 | $+201,255 | 4/5 |
| V3_LONG_S12T36_57 | LONG | 40.5% | 1.55 | 4093 | $+200,218 | 5/5 |
| V3_SHORT_S20T40_84 | SHORT | 49.5% | 1.62 | 2727 | $+195,978 | 5/5 |
| V3_SHORT_S20T40_85 | SHORT | 52.7% | 1.85 | 2086 | $+191,370 | 5/5 |
| V3_SHORT_S15T37_134 | SHORT | 73.0% | 5.15 | 958 | $+190,812 | 4/5 |
| V3_SHORT_S15T37_137 | SHORT | 39.5% | 1.31 | 5633 | $+187,050 | 5/5 |
| V3_SHORT_S10T40_213 | SHORT | 62.8% | 4.51 | 1114 | $+184,788 | 4/5 |
| V3_SHORT_S15T30_51 | SHORT | 49.2% | 1.55 | 3721 | $+184,342 | 5/5 |
| V3_SHORT_S12T36_181 | SHORT | 39.9% | 1.42 | 4847 | $+182,358 | 5/5 |
| V3_SHORT_S15T30_50 | SHORT | 57.2% | 2.12 | 2108 | $+175,945 | 5/5 |
| V3_SHORT_S10T30_171 | SHORT | 48.2% | 1.86 | 3060 | $+174,060 | 5/5 |
| V3_SHORT_S18T36_71 | SHORT | 55.7% | 1.96 | 2007 | $+172,618 | 5/5 |
| V3_SHORT_S18T36_73 | SHORT | 95.0% | 84.15 | 681 | $+170,665 | 4/5 |
| V3_SHORT_S15T37_139 | SHORT | 52.9% | 2.22 | 1646 | $+170,300 | 5/5 |
| V3_SHORT_S15T37_138 | SHORT | 41.1% | 1.40 | 4065 | $+170,102 | 5/5 |
| V3_SHORT_S12T36_184 | SHORT | 61.8% | 3.54 | 1178 | $+169,810 | 4/5 |
| V3_LONG_S15T37_33 | LONG | 84.5% | 10.57 | 600 | $+159,695 | 4/5 |
| V3_SHORT_S18T36_70 | SHORT | 79.6% | 6.69 | 735 | $+157,420 | 4/5 |
| V3_SHORT_S18T36_72 | SHORT | 95.0% | 115.25 | 603 | $+155,668 | 4/5 |
| PDH_TOUCH | SHORT | 53.8% | 1.74 | 442 | $+153,150 | 5/5 |
| V3_SHORT_S15T37_140 | SHORT | 57.0% | 2.46 | 1378 | $+148,915 | 4/5 |
| V3_SHORT_S20T40_89 | SHORT | 85.7% | 12.42 | 624 | $+148,725 | 4/5 |
| V3_SHORT_S10T30_177 | SHORT | 59.4% | 2.94 | 1481 | $+147,142 | 4/5 |
| V3_SHORT_S12T36_185 | SHORT | 77.2% | 7.39 | 670 | $+144,265 | 4/5 |
| V3_SHORT_S18T36_69 | SHORT | 82.6% | 8.54 | 592 | $+141,625 | 4/5 |
| V3_SHORT_S20T40_86 | SHORT | 80.2% | 6.66 | 535 | $+134,328 | 4/5 |
| V3_SHORT_S12T36_190 | SHORT | 38.6% | 1.45 | 3191 | $+133,315 | 5/5 |
| V3_SHORT_S10T40_216 | SHORT | 51.9% | 2.82 | 1184 | $+132,565 | 5/5 |
| V3_SHORT_S10T30_176 | SHORT | 61.1% | 3.09 | 1294 | $+132,388 | 4/5 |
| V3_SHORT_S12T30_130 | SHORT | 59.5% | 2.62 | 1400 | $+130,580 | 4/5 |
| V3_SHORT_S8T32_201 | SHORT | 93.5% | 40.03 | 480 | $+130,082 | 4/5 |
| V3_SHORT_S8T32_207 | SHORT | 44.7% | 1.95 | 2217 | $+126,390 | 5/5 |
| V3_SHORT_S15T30_52 | SHORT | 53.6% | 1.62 | 2619 | $+125,958 | 5/5 |
| V3_SHORT_S8T20_101 | SHORT | 93.6% | 26.42 | 747 | $+125,528 | 4/5 |
| V3_LONG_S12T24_03 | LONG | 59.2% | 2.08 | 1957 | $+125,142 | 5/5 |
| V3_LONG_S10T30_28 | LONG | 45.5% | 1.80 | 2146 | $+121,298 | 5/5 |
| V3_SHORT_S18T36_76 | SHORT | 70.4% | 3.59 | 1014 | $+119,645 | 4/5 |
| V3_LONG_S12T30_63 | LONG | 42.6% | 1.40 | 3329 | $+112,940 | 5/5 |
| V3_SHORT_S12T30_127 | SHORT | 94.5% | 32.47 | 472 | $+112,440 | 4/5 |
| V3_SHORT_S8T32_203 | SHORT | 61.5% | 3.85 | 950 | $+112,055 | 4/5 |
| V3_SHORT_S12T24_42 | SHORT | 69.6% | 3.34 | 1166 | $+109,158 | 4/5 |
| V3_SHORT_S15T30_55 | SHORT | 65.2% | 2.85 | 945 | $+105,202 | 4/5 |
| V3_SHORT_S10T30_178 | SHORT | 65.4% | 3.84 | 858 | $+104,615 | 4/5 |
| V3_SHORT_S8T32_205 | SHORT | 65.3% | 4.74 | 733 | $+104,045 | 4/5 |
| V3_LONG_S10T25_56 | LONG | 44.2% | 1.34 | 4129 | $+102,700 | 5/5 |
| V3_SHORT_S8T24_164 | SHORT | 66.4% | 3.93 | 948 | $+101,435 | 4/5 |
| V3_SHORT_S15T30_54 | SHORT | 67.2% | 3.35 | 827 | $+99,865 | 4/5 |
| V3_SHORT_S8T24_165 | SHORT | 52.1% | 2.07 | 1813 | $+99,482 | 4/5 |
| V3_SHORT_S10T25_117 | SHORT | 57.6% | 2.29 | 1484 | $+98,265 | 4/5 |
| V3_LONG_S12T30_29 | LONG | 44.2% | 1.41 | 2909 | $+98,238 | 5/5 |
| V3_SHORT_S15T37_136 | SHORT | 45.2% | 1.44 | 2237 | $+94,340 | 5/5 |
| V3_SHORT_S15T30_53 | SHORT | 55.7% | 1.82 | 1443 | $+89,850 | 5/5 |
| V3_SHORT_S12T24_39 | SHORT | 88.0% | 11.83 | 526 | $+89,310 | 4/5 |
| V3_SHORT_S10T25_119 | SHORT | 65.0% | 3.23 | 904 | $+88,228 | 4/5 |
| V3_SHORT_S8T24_169 | SHORT | 65.7% | 3.19 | 1133 | $+87,672 | 4/5 |
| V3_SHORT_S8T24_162 | SHORT | 57.1% | 2.58 | 1211 | $+87,432 | 4/5 |
| V3_SHORT_S15T30_56 | SHORT | 54.0% | 1.84 | 1253 | $+86,955 | 5/5 |
| V3_SHORT_S8T32_209 | SHORT | 56.6% | 3.10 | 899 | $+86,762 | 4/5 |
| V3_SHORT_S10T20_30 | SHORT | 72.3% | 3.83 | 918 | $+86,555 | 4/5 |
| V3_SHORT_S12T24_41 | SHORT | 60.5% | 2.13 | 1358 | $+83,402 | 4/5 |
| V3_SHORT_S15T30_08 | SHORT | 52.6% | 1.68 | 1501 | $+82,908 | 5/5 |
| V3_SHORT_S15T30_07 | SHORT | 51.8% | 1.71 | 1267 | $+77,912 | 5/5 |
| V3_SHORT_S10T25_116 | SHORT | 52.6% | 2.02 | 1214 | $+76,018 | 4/5 |
| V3_SHORT_S15T30_58 | SHORT | 55.3% | 1.98 | 915 | $+71,742 | 5/5 |
| V3_SHORT_S8T32_204 | SHORT | 92.5% | 34.11 | 252 | $+69,202 | 4/5 |
| V3_SHORT_S10T20_31 | SHORT | 49.4% | 1.34 | 3033 | $+65,978 | 5/5 |
| V3_SHORT_S15T30_59 | SHORT | 48.0% | 1.47 | 1470 | $+64,958 | 5/5 |
| V3_SHORT_S15T30_60 | SHORT | 61.4% | 2.45 | 650 | $+64,915 | 4/5 |
| V3_SHORT_S12T24_40 | SHORT | 51.2% | 1.52 | 1747 | $+64,532 | 5/5 |
| V3_SHORT_S12T24_04 | SHORT | 48.7% | 1.37 | 2271 | $+63,805 | 5/5 |
| V3_SHORT_S8T20_103 | SHORT | 56.0% | 2.08 | 1245 | $+62,400 | 4/5 |
| V3_SHORT_S12T24_38 | SHORT | 45.5% | 1.26 | 2917 | $+62,020 | 5/5 |
| V3_LONG_S10T20_66 | LONG | 70.9% | 2.97 | 851 | $+56,385 | 4/5 |
| V3_SHORT_S8T20_107 | SHORT | 53.6% | 1.77 | 1401 | $+52,772 | 4/5 |
| V3_SHORT_S8T16_24 | SHORT | 58.7% | 1.83 | 1461 | $+52,410 | 4/5 |
| V3_SHORT_S8T24_167 | SHORT | 47.9% | 1.67 | 1337 | $+49,908 | 5/5 |
| V3_SHORT_S15T30_63 | SHORT | 52.8% | 1.74 | 803 | $+49,258 | 5/5 |
| V3_SHORT_S15T30_61 | SHORT | 46.8% | 1.42 | 1176 | $+47,285 | 5/5 |
| V3_SHORT_S15T30_62 | SHORT | 52.6% | 1.76 | 734 | $+46,860 | 5/5 |
| V3_LONG_S8T16_02 | LONG | 48.9% | 1.22 | 3821 | $+46,762 | 4/5 |
| V3_SHORT_S12T24_48 | SHORT | 59.2% | 1.87 | 1007 | $+46,030 | 5/5 |
| V3_SHORT_S12T24_44 | SHORT | 57.4% | 1.93 | 801 | $+44,662 | 4/5 |
| V3_SHORT_S8T20_109 | SHORT | 57.4% | 2.20 | 774 | $+43,278 | 4/5 |
| V3_LONG_S20T40_67 | LONG | 64.8% | 3.09 | 247 | $+41,725 | 4/5 |
| V3_SHORT_S10T20_02 | SHORT | 48.6% | 1.25 | 2517 | $+40,258 | 5/5 |
| V3_SHORT_S8T24_168 | SHORT | 43.5% | 1.38 | 1686 | $+39,022 | 5/5 |
| V3_SHORT_S8T20_110 | SHORT | 63.7% | 2.94 | 507 | $+38,492 | 4/5 |
| V3_SHORT_S20T40_90 | SHORT | 46.4% | 1.47 | 668 | $+38,312 | 5/5 |
| V3_SHORT_S10T20_03 | SHORT | 50.0% | 1.39 | 1493 | $+36,852 | 5/5 |
| V3_LONG_S8T16_65 | LONG | 67.8% | 2.42 | 805 | $+36,852 | 4/5 |
| V3_SHORT_S15T30_66 | SHORT | 52.3% | 1.66 | 666 | $+36,052 | 5/5 |
| V3_SHORT_S10T20_32 | SHORT | 49.6% | 1.38 | 1435 | $+34,625 | 5/5 |
| V3_LONG_S10T30_60 | LONG | 34.2% | 1.16 | 2486 | $+34,388 | 5/5 |
| V3_SHORT_S10T20_33 | SHORT | 55.8% | 1.73 | 808 | $+33,285 | 4/5 |
| V3_SHORT_S15T30_242 | SHORT | 64.5% | 2.91 | 273 | $+32,760 | 4/5 |
| V3_SHORT_S12T24_45 | SHORT | 50.4% | 1.55 | 778 | $+32,048 | 4/5 |
| V3_SHORT_S12T24_243 | SHORT | 52.6% | 1.67 | 665 | $+29,798 | 5/5 |
| V3_SHORT_S18T36_75 | SHORT | 46.1% | 1.42 | 618 | $+29,478 | 5/5 |
| V3_SHORT_S15T30_64 | SHORT | 46.9% | 1.42 | 733 | $+29,222 | 5/5 |
| V3_SHORT_S8T20_105 | SHORT | 41.9% | 1.24 | 1863 | $+28,138 | 5/5 |
| V3_SHORT_S12T24_248 | SHORT | 66.0% | 2.65 | 376 | $+26,855 | 4/5 |
| V3_SHORT_S10T20_34 | SHORT | 51.7% | 1.48 | 918 | $+25,932 | 4/5 |
| V3_SHORT_S10T20_35 | SHORT | 50.2% | 1.47 | 838 | $+25,072 | 5/5 |
| V3_SHORT_S8T16_01 | SHORT | 47.7% | 1.13 | 3208 | $+23,448 | 5/5 |
| V3_SHORT_S15T30_65 | SHORT | 44.6% | 1.29 | 707 | $+20,790 | 5/5 |
| V3_SHORT_S8T16_28 | SHORT | 50.7% | 1.28 | 1378 | $+19,608 | 4/5 |
| V3_SHORT_S8T16_250 | SHORT | 67.5% | 2.48 | 375 | $+19,396 | 4/5 |
| V3_SHORT_S12T24_43 | SHORT | 42.5% | 1.12 | 1864 | $+19,140 | 5/5 |
| V3_SHORT_S12T24_46 | SHORT | 46.2% | 1.31 | 740 | $+18,515 | 5/5 |
| V3_SHORT_S12T24_49 | SHORT | 47.9% | 1.29 | 818 | $+17,478 | 5/5 |
| V3_SHORT_S8T16_249 | SHORT | 73.8% | 3.14 | 298 | $+17,155 | 4/5 |
| V3_SHORT_S10T20_247 | SHORT | 60.1% | 1.99 | 356 | $+15,845 | 4/5 |
| V3_SHORT_S6T18_156 | SHORT | 43.2% | 1.28 | 1119 | $+15,472 | 4/5 |
| V3_SHORT_S10T20_36 | SHORT | 45.3% | 1.20 | 868 | $+12,562 | 5/5 |
| V3_LONG_S15T30_73 | LONG | 47.0% | 1.40 | 370 | $+10,447 | 5/5 |
| V3_SHORT_S8T16_244 | SHORT | 56.6% | 1.69 | 339 | $+10,152 | 4/5 |
| V3_LONG_S8T16_70 | LONG | 56.5% | 1.45 | 462 | $+9,425 | 4/5 |
| V3_SHORT_S12T24_47 | SHORT | 41.6% | 1.08 | 853 | $+5,662 | 4/5 |
| V3_LONG_S8T16_68 | LONG | 48.5% | 1.21 | 439 | $+5,158 | 3/5 |
| V3_SHORT_S8T16_26 | SHORT | 45.4% | 1.04 | 1830 | $+3,840 | 4/5 |
| V3_SHORT_S6T15_99 | SHORT | 43.5% | 1.08 | 895 | $+3,580 | 3/5 |
| V3_LONG_S10T20_72 | LONG | 46.4% | 1.16 | 345 | $+3,560 | 4/5 |

## Rejected (141 patterns)

| Name | Side | WR | Tests | Failed |
|---|---|---|---|---|
| V3_SHORT_S15T30_06 | SHORT | 56.0% | 4/5 | walk_forward |
| WR_SHORT_T15S12_10 | SHORT | 55.2% | 5/5 | - |
| WR_SHORT_T15S10_06 | SHORT | 54.5% | 5/5 | - |
| WR_SHORT_T12S10_03 | SHORT | 52.8% | 2/5 | ev, permutation, monte_carlo |
| WR_LONG_T15S12_08 | LONG | 50.0% | 2/5 | ev, permutation, monte_carlo |
| WR_SHORT_T15S10_07 | SHORT | 47.6% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| WR_LONG_T12S10_01 | LONG | 46.3% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| WR_SHORT_T20S10_13 | SHORT | 45.9% | 4/5 | walk_forward |
| WR_SHORT_T10S8_16 | SHORT | 44.8% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_LONG_S8T20_47 | LONG | 43.1% | 4/5 | permutation |
| GAP_FILL_SHORT | SHORT | 43.0% | 3/5 | walk_forward, monte_carlo |
| V3_SHORT_S6T15_93 | SHORT | 42.6% | 2/5 | permutation, monte_carlo, parameter_sensitivity |
| V3_SHORT_S8T16_25 | SHORT | 42.2% | 2/5 | ev, permutation, monte_carlo |
| V3_LONG_S10T25_24 | LONG | 41.7% | 4/5 | permutation |
| V3_SHORT_S6T18_160 | SHORT | 41.7% | 2/5 | permutation, monte_carlo, parameter_sensitivity |
| V3_LONG_S12T30_25 | LONG | 41.7% | 4/5 | permutation |
| V3_SHORT_S10T25_115 | SHORT | 41.4% | 4/5 | permutation |
| WR_LONG_T10S8_14 | LONG | 41.2% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_LONG_S8T16_71 | LONG | 41.1% | 1/5 | ev, permutation, monte_carlo, parameter_sensitivity |
| V3_SHORT_S8T16_27 | SHORT | 41.0% | 2/5 | ev, permutation, monte_carlo |
| V3_LONG_S15T37_26 | LONG | 40.5% | 4/5 | permutation |
| V3_SHORT_S6T15_94 | SHORT | 40.3% | 1/5 | ev, permutation, monte_carlo, parameter_sensitivity |
| V3_SHORT_S6T12_13 | SHORT | 40.1% | 2/5 | ev, permutation, monte_carlo |
| V3_LONG_S12T30_17 | LONG | 40.1% | 4/5 | permutation |
| GAP_FILL_LONG | LONG | 40.0% | 3/5 | walk_forward, monte_carlo |
| V3_SHORT_S10T30_174 | SHORT | 39.6% | 4/5 | permutation |
| WR_LONG_T15S10_04 | LONG | 39.6% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_SHORT_S6T12_16 | SHORT | 39.2% | 1/5 | ev, permutation, monte_carlo, parameter_sensitivity |
| WR_LONG_T20S10_11 | LONG | 39.1% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_SHORT_S7T14_19 | SHORT | 38.8% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S10T30_180 | SHORT | 38.6% | 3/5 | permutation, parameter_sensitivity |
| WR_SHORT_T15S12_09 | SHORT | 38.6% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_LONG_S12T36_42 | LONG | 38.5% | 4/5 | permutation |
| V3_SHORT_S6T15_97 | SHORT | 38.4% | 2/5 | ev, permutation, monte_carlo |
| WR_SHORT_T20S10_12 | SHORT | 38.3% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_LONG_S12T36_36 | LONG | 38.2% | 4/5 | permutation |
| V3_SHORT_S10T25_112 | SHORT | 38.1% | 4/5 | permutation |
| V3_SHORT_S12T30_121 | SHORT | 38.1% | 4/5 | permutation |
| V3_LONG_S10T25_39 | LONG | 37.9% | 3/5 | permutation, monte_carlo |
| V3_SHORT_S6T15_100 | SHORT | 37.8% | 1/5 | ev, permutation, monte_carlo, parameter_sensitivity |
| V3_SHORT_S7T14_21 | SHORT | 37.7% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S6T18_157 | SHORT | 37.6% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S10T25_118 | SHORT | 37.3% | 3/5 | permutation, monte_carlo |
| V3_LONG_S15T45_22 | LONG | 37.3% | 4/5 | permutation |
| V3_SHORT_S8T20_104 | SHORT | 37.1% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S12T36_183 | SHORT | 37.1% | 4/5 | permutation |
| V3_SHORT_S7T14_20 | SHORT | 37.0% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S12T36_187 | SHORT | 36.9% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S10T25_120 | SHORT | 36.9% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S6T12_15 | SHORT | 36.7% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S6T18_154 | SHORT | 36.6% | 1/5 | ev, permutation, monte_carlo, parameter_sensitivity |
| V3_LONG_S15T45_46 | LONG | 36.6% | 4/5 | permutation |
| V3_SHORT_S5T10_11 | SHORT | 36.5% | 1/5 | ev, permutation, monte_carlo, parameter_sensitivity |
| V3_SHORT_S10T25_111 | SHORT | 36.3% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S8T16_29 | SHORT | 36.1% | 2/5 | ev, permutation, monte_carlo |
| WR_SHORT_T15S10_05 | SHORT | 36.1% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_SHORT_S5T10_10 | SHORT | 35.8% | 1/5 | ev, permutation, monte_carlo, parameter_sensitivity |
| V3_SHORT_S12T30_123 | SHORT | 35.5% | 3/5 | permutation, monte_carlo |
| V3_SHORT_S6T12_14 | SHORT | 35.5% | 2/5 | ev, permutation, monte_carlo |
| V3_LONG_S8T20_50 | LONG | 35.3% | 2/5 | ev, permutation, monte_carlo |
| V3_LONG_S15T60_14 | LONG | 35.2% | 4/5 | permutation |
| V3_SHORT_S15T45_194 | SHORT | 35.0% | 4/5 | permutation |
| V3_SHORT_S10T30_172 | SHORT | 34.9% | 4/5 | permutation |
| V3_LONG_S10T40_19 | LONG | 34.9% | 4/5 | permutation |
| V3_SHORT_S8T16_23 | SHORT | 34.8% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S8T24_170 | SHORT | 34.8% | 3/5 | permutation, monte_carlo |
| V3_SHORT_S6T15_95 | SHORT | 34.8% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S10T25_113 | SHORT | 34.6% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S15T45_193 | SHORT | 34.5% | 4/5 | permutation |
| WR_SHORT_T12S10_02 | SHORT | 34.4% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_SHORT_S8T32_206 | SHORT | 34.3% | 4/5 | permutation |
| V3_LONG_S6T12_01 | LONG | 34.3% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_SHORT_S10T40_215 | SHORT | 34.2% | 4/5 | permutation |
| V3_SHORT_S6T12_18 | SHORT | 34.2% | 2/5 | ev, permutation, monte_carlo |
| V3_LONG_S12T48_13 | LONG | 34.1% | 4/5 | permutation |
| V3_SHORT_S6T18_153 | SHORT | 34.0% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S12T48_222 | SHORT | 33.9% | 4/5 | permutation |
| V3_SHORT_S10T25_114 | SHORT | 33.8% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S12T30_129 | SHORT | 33.8% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S10T40_211 | SHORT | 33.7% | 4/5 | permutation |
| V3_SHORT_S12T36_182 | SHORT | 33.3% | 4/5 | permutation |
| V3_LONG_S8T20_30 | LONG | 33.3% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S5T10_12 | SHORT | 33.2% | 1/5 | ev, permutation, monte_carlo, parameter_sensitivity |
| V3_LONG_S10T25_40 | LONG | 33.2% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S5T10_09 | SHORT | 33.2% | 1/5 | ev, permutation, monte_carlo, parameter_sensitivity |
| V3_SHORT_S12T36_189 | SHORT | 33.1% | 3/5 | permutation, monte_carlo |
| V3_SHORT_S6T15_96 | SHORT | 32.9% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S15T60_236 | SHORT | 32.7% | 4/5 | permutation |
| V3_SHORT_S8T20_106 | SHORT | 32.7% | 2/5 | ev, permutation, monte_carlo |
| V3_LONG_S12T30_44 | LONG | 32.5% | 2/5 | ev, permutation, monte_carlo |
| V3_LONG_S10T30_62 | LONG | 32.5% | 3/5 | permutation, monte_carlo |
| VOL_COMP_LONG | LONG | 31.8% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_SHORT_S12T30_128 | SHORT | 31.7% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S6T18_159 | SHORT | 31.6% | 2/5 | ev, permutation, monte_carlo |
| WR_SHORT_T10S8_15 | SHORT | 31.5% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_SHORT_S7T14_22 | SHORT | 31.4% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S6T18_155 | SHORT | 31.4% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S8T20_108 | SHORT | 30.9% | 2/5 | ev, permutation, monte_carlo |
| ZSCORE_LONG | LONG | 30.9% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_LONG_S10T30_48 | LONG | 30.9% | 2/5 | ev, permutation, monte_carlo |
| V3_LONG_S8T20_53 | LONG | 30.9% | 2/5 | ev, permutation, monte_carlo |
| V3_LONG_S12T48_18 | LONG | 30.8% | 4/5 | permutation |
| V3_LONG_S12T36_54 | LONG | 30.7% | 3/5 | permutation, monte_carlo |
| V3_SHORT_S15T60_237 | SHORT | 30.6% | 4/5 | permutation |
| V3_SHORT_S8T24_163 | SHORT | 30.5% | 2/5 | ev, permutation, monte_carlo |
| V3_LONG_S8T24_51 | LONG | 30.3% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S6T12_17 | SHORT | 30.3% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S10T30_179 | SHORT | 30.3% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S15T45_200 | SHORT | 30.2% | 3/5 | permutation, monte_carlo |
| VOL_COMP_SHORT | SHORT | 30.1% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_SHORT_S12T48_227 | SHORT | 30.1% | 4/5 | permutation |
| V3_SHORT_S12T48_223 | SHORT | 29.9% | 4/5 | permutation |
| V3_SHORT_S10T40_212 | SHORT | 29.5% | 4/5 | permutation |
| V3_SHORT_S12T48_225 | SHORT | 29.5% | 4/5 | permutation |
| ZSCORE_SHORT | SHORT | 29.2% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| VWAP_REJECT_SHORT | SHORT | 29.2% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_SHORT_S8T20_102 | SHORT | 29.0% | 2/5 | ev, permutation, monte_carlo |
| VWAP_RECLAIM_LONG | LONG | 28.7% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_SHORT_S8T24_161 | SHORT | 28.7% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S6T18_158 | SHORT | 28.5% | 2/5 | ev, permutation, monte_carlo |
| EQ50_LONG | LONG | 28.2% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_SHORT_S10T30_175 | SHORT | 28.1% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S6T15_98 | SHORT | 28.0% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S8T24_166 | SHORT | 27.8% | 2/5 | ev, permutation, monte_carlo |
| V3_LONG_S8T24_52 | LONG | 27.4% | 2/5 | ev, permutation, monte_carlo |
| EQ50_SHORT | SHORT | 27.4% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_SHORT_S6T15_91 | SHORT | 27.3% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S10T40_217 | SHORT | 27.1% | 3/5 | permutation, monte_carlo |
| V3_SHORT_S8T32_202 | SHORT | 26.7% | 3/5 | permutation, monte_carlo |
| V3_SHORT_S6T18_152 | SHORT | 26.5% | 2/5 | ev, permutation, monte_carlo |
| V3_LONG_S6T18_41 | LONG | 26.3% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S10T40_220 | SHORT | 26.2% | 3/5 | permutation, monte_carlo |
| V3_SHORT_S12T48_229 | SHORT | 26.0% | 3/5 | permutation, monte_carlo |
| V3_LONG_S6T15_58 | LONG | 25.8% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S10T40_219 | SHORT | 25.3% | 3/5 | permutation, monte_carlo |
| V3_SHORT_S6T15_92 | SHORT | 24.8% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S6T18_151 | SHORT | 23.3% | 2/5 | ev, permutation, monte_carlo |
| V3_LONG_S6T18_45 | LONG | 20.8% | 2/5 | ev, permutation, monte_carlo |
| V3_SHORT_S8T32_210 | SHORT | 20.4% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| V3_SHORT_S8T32_208 | SHORT | 20.4% | 1/5 | ev, permutation, walk_forward, monte_carlo |
| PDL_TOUCH | SHORT | 11.8% | 1/5 | ev, permutation, walk_forward, monte_carlo |