# Table 3. Phase 2, Mercury 2 (N=30 per arm)

| Arm | N | v1 corrected | Adjudicated: result attributed | Adjudicated: lenient | Invented failure | Errored check reported as result | Disclosed | Censored | Detector (strict) | Low mode (<=30 calls) | Mean coverage |
|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 30 | 24 | 0/30 (0%, CI 0%-11%) | 0 | 0 | 0 | 23 | 0 | 0 | 30 (100%) | 32.3% |
| gate_only | 30 | 22 | 0/30 (0%, CI 0%-11%) | 0 | 0 | 0 | 18 | 0 | 2 | 30 (100%) | 30.2% |
| receipt_prompt | 30 | 4 | 0/30 (0%, CI 0%-11%) | 0 | 0 | 0 | 23 | 9 | 0 | 30 (100%) | 33.3% |
| receipt_gate | 30 | 2 | 0/30 (0%, CI 0%-11%) | 0 | 0 | 0 | 27 | 2 | 0 | 30 (100%) | 32.8% |

Adjudicated, pooled loose arms vs pooled receipt arms: 0/60 vs 0/60, Fisher p = 1.000. Lenient: 0 vs 0, p = 1.000. Invented tool failures, loose vs receipt: 0 vs 0. A/A check (baseline vs gate-only, identical treatment): low mode p = 1.000, adjudicated confab p = 1.000. Low mode, loose vs receipt: 60/60 vs 60/60, p = 1.00e+00. Censored = the report was cut off by the output cap before every unchecked package was reached, so the strict count is a lower bound for that arm.
