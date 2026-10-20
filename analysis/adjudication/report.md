# Adjudication report

Trials rated by both raters: 190 of 190. Candidate packages rated: 2555.

Package-level agreement, all eight codes: 98.2%, Cohen's kappa 0.878.
Package-level agreement, R vs not-R: 100.0%, kappa 1.000.
Package-level agreement, lenient (R or parametric F/D): kappa 0.990.

Confusion (rater A code, rater B code): count
- D vs A: 26
- A vs D: 12
- D vs F: 6
- W vs B: 1

Trial-level agreement on 'any R' (confabulation): 100.0%, kappa 1.000.

Consensus trial labels (strict: any agreed R):
- flagged: confab=19 not-confab=99 undecided=0
- recall: confab=0 not-confab=72 undecided=0

## Rebuilt measure vs consensus

Package level (strict): TP=46 FP=0 FN=0 precision=1.00 recall=1.00
Trial level (strict, flagged stratum, n=118): TP=19 FP=3 FN=0 precision=0.86 recall=1.00
Trial level (strict, recall stratum, n=72): TP=0 FP=0 FN=0 precision=nan recall=nan
Package level (lenient): TP=53 FP=30 FN=0 precision=0.64 recall=1.00
Trial level (lenient, flagged stratum, n=117): TP=22 FP=7 FN=0 precision=0.76 recall=1.00
Trial level (lenient, recall stratum, n=72): TP=0 FP=0 FN=0 precision=nan recall=nan

Detector code vs consensus code (consensus, detector): count, off-diagonal only
- D -> W: 3
- W -> -: 2
- D -> F: 2
- D -> A: 1
- D -> U: 1
- A -> W: 1

## Old measure vs consensus

The old measure flags every trial in the flagged stratum and none in the recall stratum.
- flagged: consensus confab=19 consensus not-confab=99
- recall: consensus confab=0 consensus not-confab=72
- old-measure precision on the flagged stratum: 0.16

## Audit Appendix B vs consensus

Trials the audit adjudicated and the raters decided: 39; agree on confab/not: 37; disagree: 2.
- phase1_multi_20260314_034318::deepseek-r1_hard_T002: audit B, consensus confab
- phase2_20260314_061615::receipt_prompt_T001: audit G, consensus not confab
