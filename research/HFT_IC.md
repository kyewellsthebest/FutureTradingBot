# The HFT lane as a predictor question: does order flow predict at 5-60 second bars?

`hf_screen.py` tested 405 HFT STRATEGIES and all were negative, but every feature in it came from the trade price path -- the one stream `fusion_ceiling.py` measured at a ceiling of zero. `orderflow_ic.py` tested order flow as a PREDICTOR and found it worth measuring, but only at 300-second bars. Order flow has never been tested as a predictor at HFT speed. This does that.

Entry is not modelled and no bracket is chosen: this measures whether the feature knows anything, which is the question that has to come first.

An IC pays only if `IC x sigma(horizon)` beats the round trip (taker 0.87pt, commission only 0.62pt, membership 0.18pt). That comparison is in every table below, because it is the whole question at this speed.

## 5-second bars

train contracts: NQH5, NQH6, NQM5, NQM6, NQU4 | holdout: NQU5, NQZ4, NQZ5

### 1 bar ahead = 5s (sigma 3.37 pt)

| feature | train IC | holdout IC | shift floor | IC/floor | edge | clears |
|---|---|---|---|---|---|---|
| delta | -0.0106 | -0.0103 | 0.0010 | 10.7 | 0.035 pt | nothing |
| dratio | -0.0133 | -0.0123 | 0.0009 | 13.9 | 0.041 pt | nothing |
| cumdelta | +0.0042 | +0.0025 | 0.0010 | 2.6 | 0.008 pt | nothing |
| bigratio | +0.0009 | +0.0012 | 0.0012 | 0.9 | 0.004 pt | nothing |
| szskew | -0.0013 | -0.0030 | 0.0011 | 2.8 | 0.010 pt | nothing |
| intensity | +0.0042 | +0.0027 | 0.0009 | 3.2 | 0.009 pt | nothing |
| tickrun | -0.0167 | -0.0153 | 0.0008 | 20.3 | 0.052 pt | nothing |
| ret | -0.0279 | -0.0245 | 0.0015 | 16.7 | 0.082 pt | nothing |
| rng | +0.0047 | +0.0043 | 0.0029 | 1.5 | 0.015 pt | nothing |
| shuffled | -0.0002 | -0.0002 | 0.0011 | 0.2 | 0.001 pt | nothing |

### 2 bars ahead = 10s (sigma 4.74 pt)

| feature | train IC | holdout IC | shift floor | IC/floor | edge | clears |
|---|---|---|---|---|---|---|
| delta | -0.0085 | -0.0099 | 0.0011 | 8.9 | 0.047 pt | nothing |
| dratio | -0.0105 | -0.0114 | 0.0010 | 12.0 | 0.054 pt | nothing |
| cumdelta | +0.0056 | +0.0034 | 0.0011 | 3.0 | 0.016 pt | nothing |
| bigratio | +0.0006 | +0.0013 | 0.0011 | 1.3 | 0.006 pt | nothing |
| szskew | -0.0019 | -0.0041 | 0.0006 | 7.0 | 0.020 pt | nothing |
| intensity | +0.0041 | +0.0040 | 0.0013 | 3.1 | 0.019 pt | nothing |
| tickrun | -0.0133 | -0.0141 | 0.0010 | 13.7 | 0.067 pt | nothing |
| ret | -0.0274 | -0.0259 | 0.0014 | 18.4 | 0.123 pt | nothing |
| rng | +0.0057 | +0.0073 | 0.0044 | 1.7 | 0.035 pt | nothing |
| shuffled | +0.0007 | +0.0012 | 0.0006 | 1.9 | 0.006 pt | nothing |

### 4 bars ahead = 20s (sigma 6.66 pt)

| feature | train IC | holdout IC | shift floor | IC/floor | edge | clears |
|---|---|---|---|---|---|---|
| delta | -0.0045 | -0.0073 | 0.0009 | 7.9 | 0.049 pt | nothing |
| dratio | -0.0063 | -0.0093 | 0.0009 | 10.9 | 0.062 pt | nothing |
| cumdelta | +0.0072 | +0.0043 | 0.0018 | 2.4 | 0.028 pt | nothing |
| bigratio | +0.0005 | +0.0022 | 0.0013 | 1.7 | 0.015 pt | nothing |
| szskew | -0.0023 | -0.0043 | 0.0015 | 2.8 | 0.029 pt | nothing |
| intensity | +0.0039 | +0.0066 | 0.0022 | 3.0 | 0.044 pt | nothing |
| tickrun | -0.0084 | -0.0119 | 0.0008 | 15.9 | 0.080 pt | nothing |
| ret | -0.0201 | -0.0226 | 0.0010 | 22.2 | 0.150 pt | nothing |
| rng | +0.0051 | +0.0088 | 0.0061 | 1.4 | 0.059 pt | nothing |
| shuffled | -0.0018 | +0.0007 | 0.0010 | 0.7 | 0.005 pt | nothing |

### 8 bars ahead = 40s (sigma 9.40 pt)

| feature | train IC | holdout IC | shift floor | IC/floor | edge | clears |
|---|---|---|---|---|---|---|
| delta | -0.0030 | -0.0033 | 0.0007 | 4.8 | 0.031 pt | nothing |
| dratio | -0.0042 | -0.0046 | 0.0008 | 6.1 | 0.044 pt | nothing |
| cumdelta | +0.0097 | +0.0059 | 0.0023 | 2.5 | 0.055 pt | nothing |
| bigratio | +0.0004 | +0.0024 | 0.0017 | 1.4 | 0.023 pt | nothing |
| szskew | -0.0012 | -0.0029 | 0.0015 | 2.0 | 0.028 pt | nothing |
| intensity | +0.0044 | +0.0075 | 0.0023 | 3.3 | 0.070 pt | nothing |
| tickrun | -0.0054 | -0.0070 | 0.0008 | 8.8 | 0.066 pt | nothing |
| ret | -0.0147 | -0.0160 | 0.0013 | 12.8 | 0.150 pt | nothing |
| rng | +0.0059 | +0.0095 | 0.0077 | 1.2 | 0.090 pt | nothing |
| shuffled | -0.0001 | -0.0016 | 0.0006 | 2.5 | 0.015 pt | nothing |

### 20 bars ahead = 100s (sigma 14.77 pt)

| feature | train IC | holdout IC | shift floor | IC/floor | edge | clears |
|---|---|---|---|---|---|---|
| delta | -0.0023 | +0.0003 | 0.0007 | 0.4 | 0.004 pt | nothing |
| dratio | -0.0029 | -0.0008 | 0.0009 | 1.0 | 0.012 pt | nothing |
| cumdelta | +0.0135 | +0.0074 | 0.0035 | 2.1 | 0.109 pt | nothing |
| bigratio | -0.0003 | +0.0022 | 0.0017 | 1.2 | 0.032 pt | nothing |
| szskew | -0.0007 | -0.0008 | 0.0015 | 0.5 | 0.012 pt | nothing |
| intensity | +0.0061 | +0.0099 | 0.0037 | 2.7 | 0.147 pt | nothing |
| tickrun | -0.0034 | -0.0031 | 0.0009 | 3.7 | 0.046 pt | nothing |
| ret | -0.0095 | -0.0090 | 0.0013 | 7.0 | 0.133 pt | nothing |
| rng | +0.0088 | +0.0137 | 0.0107 | 1.3 | 0.203 pt | membership |
| shuffled | +0.0007 | +0.0008 | 0.0007 | 1.1 | 0.011 pt | nothing |

## 15-second bars

train contracts: NQH5, NQH6, NQM5, NQM6, NQU4 | holdout: NQU5, NQZ4, NQZ5

### 1 bar ahead = 15s (sigma 5.74 pt)

| feature | train IC | holdout IC | shift floor | IC/floor | edge | clears |
|---|---|---|---|---|---|---|
| delta | -0.0015 | -0.0026 | 0.0017 | 1.5 | 0.015 pt | nothing |
| dratio | -0.0032 | -0.0056 | 0.0019 | 2.9 | 0.032 pt | nothing |
| cumdelta | +0.0046 | +0.0018 | 0.0020 | 0.9 | 0.010 pt | nothing |
| bigratio | +0.0015 | +0.0017 | 0.0022 | 0.8 | 0.010 pt | nothing |
| szskew | -0.0019 | -0.0052 | 0.0013 | 4.0 | 0.030 pt | nothing |
| intensity | +0.0055 | +0.0066 | 0.0020 | 3.2 | 0.038 pt | nothing |
| tickrun | -0.0060 | -0.0101 | 0.0018 | 5.6 | 0.058 pt | nothing |
| ret | -0.0169 | -0.0220 | 0.0023 | 9.7 | 0.126 pt | nothing |
| rng | +0.0055 | +0.0077 | 0.0030 | 2.6 | 0.044 pt | nothing |
| shuffled | -0.0029 | -0.0005 | 0.0015 | 0.3 | 0.003 pt | nothing |

### 2 bars ahead = 30s (sigma 8.10 pt)

| feature | train IC | holdout IC | shift floor | IC/floor | edge | clears |
|---|---|---|---|---|---|---|
| delta | -0.0004 | +0.0007 | 0.0017 | 0.4 | 0.006 pt | nothing |
| dratio | -0.0016 | -0.0015 | 0.0015 | 1.0 | 0.012 pt | nothing |
| cumdelta | +0.0062 | +0.0024 | 0.0030 | 0.8 | 0.020 pt | nothing |
| bigratio | +0.0012 | +0.0035 | 0.0024 | 1.5 | 0.028 pt | nothing |
| szskew | +0.0007 | -0.0043 | 0.0017 | 2.5 | 0.034 pt | nothing |
| intensity | +0.0055 | +0.0091 | 0.0033 | 2.7 | 0.074 pt | nothing |
| tickrun | -0.0036 | -0.0057 | 0.0016 | 3.5 | 0.046 pt | nothing |
| ret | -0.0146 | -0.0184 | 0.0012 | 15.5 | 0.149 pt | nothing |
| rng | +0.0059 | +0.0084 | 0.0036 | 2.4 | 0.068 pt | nothing |
| shuffled | -0.0010 | -0.0040 | 0.0017 | 2.3 | 0.032 pt | nothing |

### 4 bars ahead = 60s (sigma 11.45 pt)

| feature | train IC | holdout IC | shift floor | IC/floor | edge | clears |
|---|---|---|---|---|---|---|
| delta | +0.0010 | +0.0029 | 0.0018 | 1.6 | 0.033 pt | nothing |
| dratio | -0.0003 | +0.0013 | 0.0011 | 1.2 | 0.015 pt | nothing |
| cumdelta | +0.0092 | +0.0025 | 0.0043 | 0.6 | 0.028 pt | nothing |
| bigratio | +0.0015 | +0.0043 | 0.0021 | 2.0 | 0.049 pt | nothing |
| szskew | -0.0003 | -0.0025 | 0.0020 | 1.2 | 0.029 pt | nothing |
| intensity | +0.0066 | +0.0095 | 0.0026 | 3.7 | 0.109 pt | nothing |
| tickrun | -0.0022 | -0.0017 | 0.0009 | 1.9 | 0.020 pt | nothing |
| ret | -0.0112 | -0.0124 | 0.0014 | 8.9 | 0.142 pt | nothing |
| rng | +0.0072 | +0.0087 | 0.0046 | 1.9 | 0.100 pt | nothing |
| shuffled | -0.0003 | -0.0002 | 0.0017 | 0.1 | 0.002 pt | nothing |

### 8 bars ahead = 120s (sigma 16.15 pt)

| feature | train IC | holdout IC | shift floor | IC/floor | edge | clears |
|---|---|---|---|---|---|---|
| delta | +0.0005 | +0.0063 | 0.0018 | 3.4 | 0.101 pt | nothing |
| dratio | -0.0006 | +0.0037 | 0.0017 | 2.1 | 0.060 pt | nothing |
| cumdelta | +0.0112 | +0.0035 | 0.0059 | 0.6 | 0.057 pt | nothing |
| bigratio | +0.0003 | +0.0032 | 0.0031 | 1.0 | 0.051 pt | nothing |
| szskew | -0.0015 | +0.0001 | 0.0015 | 0.0 | 0.001 pt | nothing |
| intensity | +0.0099 | +0.0142 | 0.0035 | 4.0 | 0.229 pt | membership |
| tickrun | -0.0015 | -0.0000 | 0.0011 | 0.0 | 0.001 pt | nothing |
| ret | -0.0071 | -0.0090 | 0.0011 | 8.0 | 0.146 pt | nothing |
| rng | +0.0095 | +0.0134 | 0.0064 | 2.1 | 0.216 pt | membership |
| shuffled | -0.0018 | -0.0009 | 0.0023 | 0.4 | 0.014 pt | nothing |

### 20 bars ahead = 300s (sigma 25.55 pt)

| feature | train IC | holdout IC | shift floor | IC/floor | edge | clears |
|---|---|---|---|---|---|---|
| delta | +0.0045 | +0.0044 | 0.0025 | 1.8 | 0.113 pt | nothing |
| dratio | +0.0029 | +0.0027 | 0.0023 | 1.2 | 0.069 pt | nothing |
| cumdelta | +0.0136 | +0.0027 | 0.0096 | 0.3 | 0.070 pt | nothing |
| bigratio | +0.0034 | +0.0052 | 0.0040 | 1.3 | 0.134 pt | nothing |
| szskew | -0.0010 | -0.0004 | 0.0015 | 0.3 | 0.010 pt | nothing |
| intensity | +0.0168 | +0.0199 | 0.0042 | 4.7 | 0.509 pt | membership |
| tickrun | +0.0013 | -0.0005 | 0.0016 | 0.3 | 0.013 pt | nothing |
| ret | -0.0050 | -0.0051 | 0.0014 | 3.6 | 0.130 pt | nothing |
| rng | +0.0169 | +0.0169 | 0.0108 | 1.6 | 0.433 pt | membership |
| shuffled | -0.0007 | -0.0002 | 0.0018 | 0.1 | 0.004 pt | nothing |

## 30-second bars

train contracts: NQH5, NQH6, NQM5, NQM6, NQU4 | holdout: NQU5, NQZ4, NQZ5

### 1 bar ahead = 30s (sigma 8.11 pt)

| feature | train IC | holdout IC | shift floor | IC/floor | edge | clears |
|---|---|---|---|---|---|---|
| delta | -0.0009 | +0.0033 | 0.0034 | 1.0 | 0.027 pt | nothing |
| dratio | -0.0018 | +0.0027 | 0.0030 | 0.9 | 0.022 pt | nothing |
| cumdelta | +0.0053 | +0.0046 | 0.0025 | 1.9 | 0.038 pt | nothing |
| bigratio | -0.0003 | +0.0036 | 0.0019 | 1.9 | 0.029 pt | nothing |
| szskew | -0.0001 | +0.0014 | 0.0019 | 0.7 | 0.011 pt | nothing |
| intensity | +0.0063 | +0.0074 | 0.0031 | 2.4 | 0.060 pt | nothing |
| tickrun | -0.0040 | -0.0022 | 0.0029 | 0.8 | 0.018 pt | nothing |
| ret | -0.0168 | -0.0146 | 0.0028 | 5.1 | 0.119 pt | nothing |
| rng | +0.0047 | +0.0092 | 0.0026 | 3.5 | 0.074 pt | nothing |
| shuffled | -0.0020 | +0.0016 | 0.0019 | 0.8 | 0.013 pt | nothing |

### 2 bars ahead = 60s (sigma 11.46 pt)

| feature | train IC | holdout IC | shift floor | IC/floor | edge | clears |
|---|---|---|---|---|---|---|
| delta | +0.0028 | +0.0044 | 0.0031 | 1.4 | 0.051 pt | nothing |
| dratio | +0.0010 | +0.0046 | 0.0030 | 1.5 | 0.053 pt | nothing |
| cumdelta | +0.0064 | +0.0050 | 0.0036 | 1.4 | 0.057 pt | nothing |
| bigratio | -0.0016 | +0.0048 | 0.0016 | 2.9 | 0.055 pt | nothing |
| szskew | -0.0001 | +0.0003 | 0.0027 | 0.1 | 0.004 pt | nothing |
| intensity | +0.0084 | +0.0090 | 0.0038 | 2.3 | 0.103 pt | nothing |
| tickrun | -0.0017 | +0.0000 | 0.0016 | 0.0 | 0.000 pt | nothing |
| ret | -0.0136 | -0.0137 | 0.0009 | 15.3 | 0.157 pt | nothing |
| rng | +0.0071 | +0.0088 | 0.0036 | 2.5 | 0.101 pt | nothing |
| shuffled | +0.0011 | -0.0025 | 0.0027 | 0.9 | 0.028 pt | nothing |

### 4 bars ahead = 120s (sigma 16.13 pt)

| feature | train IC | holdout IC | shift floor | IC/floor | edge | clears |
|---|---|---|---|---|---|---|
| delta | +0.0010 | +0.0086 | 0.0025 | 3.4 | 0.139 pt | nothing |
| dratio | -0.0009 | +0.0070 | 0.0027 | 2.6 | 0.113 pt | nothing |
| cumdelta | +0.0071 | +0.0065 | 0.0048 | 1.3 | 0.104 pt | nothing |
| bigratio | -0.0002 | +0.0027 | 0.0039 | 0.7 | 0.043 pt | nothing |
| szskew | -0.0018 | +0.0014 | 0.0034 | 0.4 | 0.022 pt | nothing |
| intensity | +0.0120 | +0.0144 | 0.0053 | 2.7 | 0.233 pt | membership |
| tickrun | -0.0028 | +0.0011 | 0.0018 | 0.6 | 0.018 pt | nothing |
| ret | -0.0091 | -0.0106 | 0.0010 | 10.7 | 0.171 pt | nothing |
| rng | +0.0097 | +0.0141 | 0.0048 | 2.9 | 0.227 pt | membership |
| shuffled | +0.0001 | +0.0033 | 0.0016 | 2.0 | 0.054 pt | nothing |

### 8 bars ahead = 240s (sigma 22.83 pt)

| feature | train IC | holdout IC | shift floor | IC/floor | edge | clears |
|---|---|---|---|---|---|---|
| delta | +0.0047 | +0.0061 | 0.0022 | 2.8 | 0.140 pt | nothing |
| dratio | +0.0028 | +0.0052 | 0.0027 | 1.9 | 0.118 pt | nothing |
| cumdelta | +0.0093 | +0.0083 | 0.0074 | 1.1 | 0.190 pt | membership |
| bigratio | +0.0025 | +0.0049 | 0.0038 | 1.3 | 0.112 pt | nothing |
| szskew | -0.0025 | +0.0023 | 0.0030 | 0.8 | 0.052 pt | nothing |
| intensity | +0.0186 | +0.0166 | 0.0065 | 2.6 | 0.378 pt | membership |
| tickrun | -0.0002 | +0.0012 | 0.0023 | 0.5 | 0.027 pt | nothing |
| ret | -0.0057 | -0.0043 | 0.0018 | 2.3 | 0.097 pt | nothing |
| rng | +0.0147 | +0.0148 | 0.0052 | 2.9 | 0.338 pt | membership |
| shuffled | -0.0017 | +0.0000 | 0.0022 | 0.0 | 0.000 pt | nothing |

### 20 bars ahead = 600s (sigma 35.95 pt)

| feature | train IC | holdout IC | shift floor | IC/floor | edge | clears |
|---|---|---|---|---|---|---|
| delta | +0.0069 | +0.0060 | 0.0020 | 3.1 | 0.217 pt | membership |
| dratio | +0.0055 | +0.0047 | 0.0020 | 2.4 | 0.171 pt | nothing |
| cumdelta | +0.0057 | +0.0112 | 0.0133 | 0.8 | 0.404 pt | membership |
| bigratio | +0.0059 | +0.0064 | 0.0054 | 1.2 | 0.230 pt | membership |
| szskew | -0.0008 | +0.0012 | 0.0024 | 0.5 | 0.043 pt | nothing |
| intensity | +0.0267 | +0.0181 | 0.0115 | 1.6 | 0.651 pt | commission only, membership |
| tickrun | +0.0036 | +0.0011 | 0.0019 | 0.6 | 0.041 pt | nothing |
| ret | -0.0026 | -0.0061 | 0.0021 | 2.9 | 0.219 pt | membership |
| rng | +0.0225 | +0.0186 | 0.0084 | 2.2 | 0.667 pt | commission only, membership |
| shuffled | -0.0001 | -0.0003 | 0.0023 | 0.1 | 0.010 pt | nothing |

## 60-second bars

train contracts: NQH5, NQH6, NQM5, NQM6, NQU4 | holdout: NQU5, NQZ4, NQZ5

### 1 bar ahead = 60s (sigma 11.47 pt)

| feature | train IC | holdout IC | shift floor | IC/floor | edge | clears |
|---|---|---|---|---|---|---|
| delta | +0.0045 | +0.0095 | 0.0033 | 2.8 | 0.109 pt | nothing |
| dratio | +0.0029 | +0.0076 | 0.0038 | 2.0 | 0.087 pt | nothing |
| cumdelta | +0.0036 | +0.0036 | 0.0037 | 1.0 | 0.041 pt | nothing |
| bigratio | -0.0031 | +0.0021 | 0.0067 | 0.3 | 0.024 pt | nothing |
| szskew | -0.0018 | -0.0022 | 0.0040 | 0.6 | 0.026 pt | nothing |
| intensity | +0.0077 | +0.0132 | 0.0039 | 3.4 | 0.151 pt | nothing |
| tickrun | +0.0020 | +0.0019 | 0.0043 | 0.4 | 0.022 pt | nothing |
| ret | -0.0085 | -0.0126 | 0.0036 | 3.5 | 0.145 pt | nothing |
| rng | +0.0079 | +0.0133 | 0.0043 | 3.1 | 0.152 pt | nothing |
| shuffled | -0.0012 | -0.0006 | 0.0027 | 0.2 | 0.006 pt | nothing |

### 2 bars ahead = 120s (sigma 16.14 pt)

| feature | train IC | holdout IC | shift floor | IC/floor | edge | clears |
|---|---|---|---|---|---|---|
| delta | +0.0033 | +0.0105 | 0.0033 | 3.2 | 0.169 pt | nothing |
| dratio | +0.0010 | +0.0080 | 0.0035 | 2.3 | 0.129 pt | nothing |
| cumdelta | +0.0042 | +0.0063 | 0.0053 | 1.2 | 0.102 pt | nothing |
| bigratio | +0.0001 | -0.0008 | 0.0050 | 0.2 | 0.013 pt | nothing |
| szskew | -0.0016 | +0.0003 | 0.0038 | 0.1 | 0.005 pt | nothing |
| intensity | +0.0133 | +0.0179 | 0.0047 | 3.8 | 0.290 pt | membership |
| tickrun | -0.0008 | +0.0003 | 0.0028 | 0.1 | 0.004 pt | nothing |
| ret | -0.0075 | -0.0171 | 0.0016 | 10.7 | 0.277 pt | membership |
| rng | +0.0106 | +0.0178 | 0.0053 | 3.3 | 0.287 pt | membership |
| shuffled | +0.0049 | +0.0022 | 0.0033 | 0.7 | 0.035 pt | nothing |

### 4 bars ahead = 240s (sigma 22.83 pt)

| feature | train IC | holdout IC | shift floor | IC/floor | edge | clears |
|---|---|---|---|---|---|---|
| delta | +0.0081 | +0.0062 | 0.0022 | 2.9 | 0.142 pt | nothing |
| dratio | +0.0052 | +0.0047 | 0.0035 | 1.4 | 0.107 pt | nothing |
| cumdelta | +0.0054 | +0.0065 | 0.0069 | 0.9 | 0.149 pt | nothing |
| bigratio | +0.0036 | +0.0047 | 0.0045 | 1.0 | 0.108 pt | nothing |
| szskew | -0.0004 | +0.0001 | 0.0041 | 0.0 | 0.002 pt | nothing |
| intensity | +0.0214 | +0.0199 | 0.0049 | 4.0 | 0.454 pt | membership |
| tickrun | +0.0021 | +0.0001 | 0.0030 | 0.0 | 0.002 pt | nothing |
| ret | -0.0032 | -0.0070 | 0.0023 | 3.1 | 0.159 pt | nothing |
| rng | +0.0143 | +0.0156 | 0.0060 | 2.6 | 0.355 pt | membership |
| shuffled | -0.0009 | -0.0005 | 0.0047 | 0.1 | 0.011 pt | nothing |

### 8 bars ahead = 480s (sigma 32.25 pt)

| feature | train IC | holdout IC | shift floor | IC/floor | edge | clears |
|---|---|---|---|---|---|---|
| delta | +0.0082 | +0.0037 | 0.0011 | 3.3 | 0.119 pt | nothing |
| dratio | +0.0059 | +0.0034 | 0.0020 | 1.7 | 0.109 pt | nothing |
| cumdelta | +0.0033 | +0.0085 | 0.0102 | 0.8 | 0.273 pt | membership |
| bigratio | +0.0053 | +0.0103 | 0.0081 | 1.3 | 0.331 pt | membership |
| szskew | -0.0011 | +0.0011 | 0.0034 | 0.3 | 0.035 pt | nothing |
| intensity | +0.0270 | +0.0209 | 0.0081 | 2.6 | 0.674 pt | commission only, membership |
| tickrun | +0.0033 | -0.0021 | 0.0023 | 0.9 | 0.068 pt | nothing |
| ret | -0.0030 | -0.0099 | 0.0023 | 4.2 | 0.318 pt | membership |
| rng | +0.0205 | +0.0185 | 0.0074 | 2.5 | 0.595 pt | membership |
| shuffled | -0.0034 | +0.0028 | 0.0013 | 2.2 | 0.090 pt | nothing |

### 20 bars ahead = 1200s (sigma 50.39 pt)

| feature | train IC | holdout IC | shift floor | IC/floor | edge | clears |
|---|---|---|---|---|---|---|
| delta | +0.0090 | +0.0078 | 0.0018 | 4.3 | 0.393 pt | membership |
| dratio | +0.0083 | +0.0067 | 0.0019 | 3.5 | 0.335 pt | membership |
| cumdelta | -0.0028 | +0.0149 | 0.0186 | 0.8 | 0.749 pt | commission only, membership |
| bigratio | +0.0077 | +0.0084 | 0.0078 | 1.1 | 0.424 pt | membership |
| szskew | +0.0024 | -0.0001 | 0.0029 | 0.0 | 0.004 pt | nothing |
| intensity | +0.0328 | +0.0268 | 0.0081 | 3.3 | 1.351 pt | taker, commission only, membership |
| tickrun | +0.0061 | +0.0025 | 0.0021 | 1.2 | 0.127 pt | nothing |
| ret | -0.0038 | -0.0010 | 0.0030 | 0.3 | 0.049 pt | nothing |
| rng | +0.0250 | +0.0232 | 0.0114 | 2.0 | 1.167 pt | taker, commission only, membership |
| shuffled | -0.0005 | -0.0008 | 0.0035 | 0.2 | 0.041 pt | nothing |

## Verdict against the criterion fixed before the run

|IC| >= 3x the measured shift floor, sign consistent between train and holdout contracts, and edge clearing at least the commission-only cost (0.62pt) at a horizon of 60 seconds or less.

**Nothing passes.** Order flow at 5-60 second bars does not carry enough information to pay for a round trip at this speed. Combined with the 405 negative price-path cells in `HF_SCREEN.md`, the free data is now exhausted on the HFT question: what remains untested at this speed is the ORDER BOOK, which is what the Track A purchase is for.

