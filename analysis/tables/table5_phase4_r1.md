# Table 5. Phase 4, DeepSeek R1

| Arm | N | v1 corrected | Adjudicated: result attributed | Adjudicated: lenient | Invented failure | Errored check reported as result | Disclosed | Censored | Detector (strict) | Low mode (<=30 calls) | Mean coverage |
|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline (Phase 2) | 50 | 11 | 4/50 (8%, CI 3%-19%) | 6 | 3 | 7 | 0 | 0 | 4 | 20 (40%) | 48.5% |
| echo_only | 25 | 2 | 1/25 (4%, CI 1%-20%) | 1 | 0 | 13 | 0 | 13 | 1 | 0 (0%) | 77.3% |
| disclosure_only | 25 | 7 | 2/25 (8%, CI 2%-25%) | 2 | 0 | 7 | 8 | 6 | 2 | 1 (4%) | 74.8% |
| both (Phase 2 receipt prompt) | 50 | 5 | 1/50 (2%, CI 0%-10%) | 1 | 0 | 3 | 10 | 19 | 1 | 1 (2%) | 75.8% |

Baseline and 'both' are the Phase 2 arms the v1 paper reused. Echo-only and disclosure-only ran about three hours later, so this is a historical comparison, not a concurrent one.
