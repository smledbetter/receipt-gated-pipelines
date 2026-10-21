# Table 6. Phase 4, Mercury 2

| Arm | N | v1 corrected | Adjudicated: result attributed | Adjudicated: lenient | Invented failure | Errored check reported as result | Disclosed | Censored | Detector (strict) | Low mode (<=30 calls) | Mean coverage |
|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline (Phase 2) | 30 | 24 | 0/30 (0%, CI 0%-11%) | 0 | 0 | 0 | 23 | 0 | 0 | 30 (100%) | 32.3% |
| echo_only | 15 | 4 | 0/15 (0%, CI 0%-20%) | 0 | 0 | 0 | 3 | 2 | 0 | 15 (100%) | 33.6% |
| disclosure_only | 15 | 1 | 0/15 (0%, CI 0%-20%) | 0 | 0 | 0 | 11 | 3 | 0 | 15 (100%) | 33.1% |
| both (Phase 2 receipt prompt) | 30 | 4 | 0/30 (0%, CI 0%-11%) | 0 | 0 | 0 | 23 | 9 | 0 | 30 (100%) | 33.3% |

Baseline and 'both' are the Phase 2 arms the v1 paper reused. Echo-only and disclosure-only ran about three hours later, so this is a historical comparison, not a concurrent one.
