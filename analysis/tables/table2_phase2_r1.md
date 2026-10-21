# Table 2. Phase 2, DeepSeek R1 (N=50 per arm)

| Arm | N | v1 corrected | Adjudicated: result attributed | Adjudicated: lenient | Invented failure | Errored check reported as result | Disclosed | Censored | Detector (strict) | Low mode (<=30 calls) | Mean coverage |
|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 50 | 11 | 4/50 (8%, CI 3%-19%) | 6 | 3 | 7 | 0 | 0 | 4 | 20 (40%) | 48.5% |
| gate_only | 50 | 13 | 4/50 (8%, CI 3%-19%) | 4 | 3 | 6 | 2 | 0 | 4 | 32 (64%) | 35.5% |
| receipt_prompt | 50 | 5 | 1/50 (2%, CI 0%-10%) | 1 | 0 | 3 | 10 | 19 | 1 | 1 (2%) | 75.8% |
| receipt_gate | 50 | 6 | 0/50 (0%, CI 0%-7%) | 0 | 1 | 4 | 7 | 26 | 0 | 1 (2%) | 73.7% |

Adjudicated, pooled loose arms vs pooled receipt arms: 8/100 vs 1/100, Fisher p = 0.035. Lenient: 10 vs 1, p = 0.010. Invented tool failures, loose vs receipt: 6 vs 1. A/A check (baseline vs gate-only, identical treatment): low mode p = 0.027, adjudicated confab p = 1.000. Low mode, loose vs receipt: 52/100 vs 2/100, p = 3.23e-17. Censored = the report was cut off by the output cap before every unchecked package was reached, so the strict count is a lower bound for that arm.
