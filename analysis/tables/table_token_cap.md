# Table 7. The 4,096-token output cap in the first tool-call batch

| Model | Production trials | First turn at 76 or 77 calls | Batches of 70+ calls | Exactly 4,096 output tokens | Last call cut off mid-JSON | Calls = prompt-order prefix |
|---|---|---|---|---|---|---|
| deepseek-r1 | 290 | 179 | 186 | 0 | 30 | 141 |
| deepseek-v3 | 20 | 9 | 11 | 11 | 10 | 9 |

R1's reported output tokens include reasoning tokens, so its batches never read exactly 4,096. The 76/77 stopping point at V3's tokens-per-call rate is the evidence for R1.
