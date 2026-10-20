# Table 3. Phase 2, Mercury 2 (N=30 per arm)

| Arm | N | v1 corrected | Rebuilt strict | Rebuilt lenient | Invented failure | Disclosed | Censored | Low mode (<=30 calls) | Mean coverage |
|---|---|---|---|---|---|---|---|---|---|
| baseline | 30 | 24 | 0/30 (0%, CI 0%-11%) | 2 | 1 | 24 | 0 | 30 (100%) | 32.3% |
| gate_only | 30 | 22 | 2/30 (7%, CI 2%-21%) | 4 | 0 | 18 | 0 | 30 (100%) | 30.2% |
| receipt_prompt | 30 | 4 | 0/30 (0%, CI 0%-11%) | 0 | 0 | 23 | 9 | 30 (100%) | 33.3% |
| receipt_gate | 30 | 2 | 0/30 (0%, CI 0%-11%) | 0 | 0 | 27 | 2 | 30 (100%) | 32.8% |

Pooled loose arms vs pooled receipt arms, strict: 2/60 vs 0/60, Fisher p = 0.496. Lenient: 6 vs 0, p = 0.027. A/A check (baseline vs gate-only, identical treatment): low mode p = 1.000, strict confab p = 0.492. Low mode, loose vs receipt: 60/60 vs 60/60, p = 1.00e+00. Censored = the report was cut off by the output cap before every unchecked package was reached, so the strict count is a lower bound for that arm.
