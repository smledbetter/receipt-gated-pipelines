# Table 1. Phase 1 confabulation rates by model, three measures

| Model | Trials | v1 paper (raw substring) | v1 corrected method | Rebuilt: result attributed (strict) | Rebuilt: lenient | Invented tool failure | Harness artifact |
|---|---|---|---|---|---|---|---|
| deepseek-r1 | 40 | 19 (47.5%) | 8 (20.0%) | 5/40 (12%, CI 5%-26%) | 6 | 2 | 0 |
| deepseek-v3 | 20 | 9 (45.0%) | 2 (10.0%) | 1/20 (5%, CI 1%-24%) | 1 | 0 | 0 |
| mercury | 22 | 11 (50.0%) | 6 (27.3%) | 1/22 (5%, CI 1%-22%) | 2 | 0 | 0 |
| gemini-flash | 11 | 0 (0.0%) | 0 (0.0%) | 0/11 (0%, CI 0%-26%) | 0 | 0 | 0 |
| haiku-4.5 | 31 | 1 (3.2%) | 0 (0.0%) | 0/31 (0%, CI 0%-11%) | 0 | 0 | 0 |
| sonnet-4.6 | 5 | 0 (0.0%) | 0 (0.0%) | 0/5 (0%, CI 0%-43%) | 0 | 0 | 0 |
| gpt4o-mini | 20 | 1 (5.0%) | 1 (5.0%) | 1/20 (5%, CI 1%-24%) | 1 | 0 | 0 |
| llama-70b | 20 | 1 (5.0%) | 0 (0.0%) | 0/20 (0%, CI 0%-16%) | 0 | 0 | 1 |
| mistral-small | 20 | 3 (15.0%) | 0 (0.0%) | 0/20 (0%, CI 0%-16%) | 0 | 0 | 20 |

Strict = the report attributes a scan result to a package the tool never checked. Lenient adds packages for which the report claims a failed check or a disclosure but asserts a vulnerability anyway. Invented tool failure = the report says a check failed for a package the model never asked the tool about. Mistral's 20 trials are API failures and are listed for completeness only.
