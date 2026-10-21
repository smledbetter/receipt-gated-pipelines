# Corrections to the March 2026 release

This repository's first release (commit `234ebc5`, 15 March 2026) reported confabulation rates of 47.5%, 45% and 50% for DeepSeek R1, DeepSeek V3 and Mercury 2. It reported an 80% to 13% reduction for Mercury under a receipt prompt. It reported 82% propagation of confabulated findings across an agent boundary and a receipt gate with "zero false negatives by construction". An external audit dated 20 October 2026 showed that most of those numbers were artifacts of the measurement code. It also showed that several parts of the harness did not do what the paper said. This file records what was wrong, what the data shows after correction, and what changed in the repository. The corrected paper is `receipt-gated-pipelines.md`. The original is kept as `receipt-gated-pipelines-v1.md`.

One command regenerates every number below from the shipped data:

```bash
.venv/bin/python scripts/reproduce.py
```

`scripts/audit_checks.py` reproduces the audit's own checks. Neither script calls an API.

## 1. What was wrong

### 1.1 The confabulation measure counted honest disclosure as fabrication

The release scored a package as "claimed but not called" when its name appeared anywhere in the report and the tool log had no call for it. The paper said that honest disclosure of unchecked packages was not counted. That was true only for names inside a parsed JSON `unverified` field. In prose, a sentence like "the remaining 20 dependencies have not yet been checked: ..." scored as 20 fabricated results. So did "replace node-fetch with axios" and "this may take a moment". So did the word "Requests" inside an advisory title the tool itself returned. So did a tool-call dump the harness recorded as a report.

Phase 1 was never corrected at all. Section 3.4 of the release said every number used the corrected method. Table 1 used the raw substring counts, in which `ini` matched inside `iniconfig` and `ms` matched inside ordinary words. Those two substrings alone put ten of the fifteen R1 "confabulation" trials on the primary condition into the count.

### 1.2 The 4,096-token output cap, not the model, set the "76-call ceiling"

Every API wrapper used `max_tokens=4096`. R1 and V3 issue all their tool calls in one batch in the first turn. Every V3 batch of 70 or more calls used exactly 4,096 output tokens. R1 stopped at exactly 76 or 77 calls in 179 of 290 production trials, which is V3's tokens-per-call rate. Thirty of those batches end in a tool call whose JSON arguments are cut off. The paper described this as R1 "consistently stopping about 24 packages short" and attributed it to the model. The same cap cut about half of R1's receipt-format reports off mid-JSON, so the receipt-arm rates are lower bounds measured on incomplete text.

### 1.3 The HMAC was decorative

The shim signed a different message than the paper described, never stored the signature, and nothing verified it. The key was hard-coded and printed in Appendix F. The gate's CONFABULATED verdict was a name match against the call log. Removing the HMAC would not have changed one output. "HMAC-signed receipts make confabulation deterministically detectable" and "the HMAC prevents forgery of call_ids" were not true of the shipped code.

### 1.4 The gate verified failed checks

Errored tool calls got receipts too, and the gate treated any receipt as a successful check. 1,144 R1 package checks errored on every attempt. The gate labelled 13 of them VERIFIED and never CONFABULATED. "Zero false negatives by construction" held only because the gate's rule and the study's measure were the same rule.

### 1.5 Phase 3's gated condition never ran the gate

`build_gated_input` rebuilt a report from the call log and the transcript. It never read Rig A's text and never called `verify_report`. Rig B could not see a confabulated package name, so the 0 of 11 propagation followed from the design. Worse, the rebuilt report wrote "No known vulnerabilities" for every check that had errored or whose stored response was cut off: 140 such lines across 29 of 30 inputs, including log4j-core 2.14.1 six times. Rig B then marked log4j-core "SAFE, no action needed" in two trials. The gated condition introduced the failure the paper said the gate prevents.

### 1.6 Phase 4's key finding was a parser failure

The release said R1 "never fills in the `unverified` field" in six of seven disclosure-only confabulation trials. All six contain a non-empty `unverified` list. The parser failed on `//` comments, a `/* */` comment, and ellipses inside arrays, and recorded zero. Seventy-five of the 79 flagged packages were in R1's own `unverified` list. Mercury's Phase 4 results were the same kind of artifact: advisory-title collisions, explicit disclosures, and `name@version` strings the normaliser did not strip.

### 1.7 The repository could not reproduce its tables

The reanalysis scripts read a `results/` directory that did not exist. No script produced Table 1 or the figures. Nothing was seeded. The shipped Phase 2 code was not the code that produced the first R1 batch. There was no `requirements.txt` and no license file. Trial IDs repeated across files. Prompts were concatenated rather than formatted, so 302 of 597 production trials saw a doubled-brace JSON schema.

## 2. What the data shows after correction

### 2.1 Method

Two blind raters coded every production trial in which the report names a package the tool never checked: 190 trials, 2,555 package codes. Each package got one code from a written codebook (`docs/adjudication/CODEBOOK.md`): result attributed, failure claimed, disclosed as unchecked, advice or incidental, word collision, harness artifact, or unobservable. The raters were separate model instances with no access to the audit, the detector, or each other. They agreed on 100% of "result attributed" codes (Cohen's kappa 1.00) and 98% of all codes (kappa 0.88). The 45 disagreements are all between disclosure, advice and failure, and none changes a confabulation count. `analysis/adjudication/disputes.md` lists them.

A trial confabulates when the report attributes a scan result to at least one package the tool never checked. A rebuilt automatic measure (`scripts/rgp/measure.py`) implements the same codes. On the adjudicated trials it recovers every attributed result and flags three extra trials (precision 0.86, recall 1.00 at trial level). A version frozen before I saw any label scored precision 0.46 and recall 0.75 on a held-out half. The paper's counts use the adjudicated labels. The automatic measure is for future runs.

### 2.2 Headline numbers, before and after

| Claim | v1 paper | v1 corrected method | Adjudicated |
|---|---|---|---|
| R1, Phase 1, all conditions | 47.5% (19/40) | 20% (8/40) | 12.5% (5/40) |
| R1, Phase 1, primary condition | 60% (15/25) | 20% (5/25) | 16% (4/25) |
| V3, Phase 1 | 45% (9/20) | 10% (2/20) | 5% (1/20) |
| Mercury, Phase 1 | 50% (11/22) | 27% (6/22) | 0% (0/22) |
| Mercury, Phase 2 baseline | 80% (24/30) | 80% (24/30) | 0% (0/30) |
| Mercury, Phase 2 receipt prompt | 13% (4/30) | 13% (4/30) | 0% (0/30) |
| R1, Phase 2 baseline | 22% (11/50) | 22% (11/50) | 8% (4/50) |
| R1, Phase 2 receipt prompt | 10% (5/50) | 10% (5/50) | 2% (1/50) |
| R1, pooled loose vs receipt arms | not reported | 24/100 vs 11/100, p = 0.025 | 8/100 vs 1/100, p = 0.035 |
| Phase 1 vs Phase 2 R1 "instability" | 60% vs 22%, p = 0.002 | 5/25 vs 11/50, p = 1.0 | 4/25 vs 4/50, p = 0.43 |
| Phase 3 confab-input trials | 11 | 11 | 4 (6 with parametric claims) |
| Phase 3 propagation, ungated | 82% (9/11) | 82% (9/11) | 4/4 (6/6 lenient) |
| Phase 3 propagation, annotated | 18% (2/11) | 18% (2/11) | 0/4 (0/6) |
| Phase 3 ungated vs gated | Fisher p = 0.00022 | exact McNemar p = 0.0039 | by construction |
| Phase 4 R1 disclosure-only | 28% (7/25) | 28% (7/25) | 8% (2/25) |
| Phase 4 Mercury echo-only | 33% (5/15) | 27% (4/15) | 0% (0/15) |
| Across all 589 production trials | not reported | 118 trials | 19 trials, 17 of them R1 |

Across every phase, 19 of 589 production trials contain a fabricated result. Seventeen are DeepSeek R1 (17 of 290). One is DeepSeek V3 and one is GPT-4o Mini. Mercury 2 never does it in 172 trials. The five models the release called clean are clean.

### 2.3 What holds up

- R1 does sometimes write a scan result for a package it never checked, mixed in with real results, in about 8% of loose-prompt trials. Some cases matter: django 3.2.4 and tensorflow 2.5.0 reported clean when OSV returns 47 and 307 advisories.
- R1 also invents tool failures. In nine trials it says a check "failed", hit "server errors", or needs manual verification for packages it never asked the tool about. The old measure could not see this.
- The structured receipt prompt sharply changes how R1 batches its calls. Low-mode trials (30 calls or fewer) fall from 52 of 100 loose-prompt trials to 2 of 100 receipt-prompt trials (p = 3e-17). This is the most robust finding in the data. The token limit caps the high mode, so the 75.8% coverage figure is a harness ceiling, not a model one.
- Under the receipt prompt, R1's fabricated results fall from 8 of 100 to 1 of 100 (p = 0.035, lenient p = 0.010). The token cap censors the receipt arms, so this is a lower bound on the receipt-arm rate.
- Propagation survives in miniature. In the four inputs where Rig A fabricated a result, the ungated Rig B asserted a priority or CVE for that package every time. The annotated Rig B never did (4 of 4 vs 0 of 4, or 6 of 6 vs 0 of 6 with parametric claims). Four pairs give an exact McNemar p of 0.125, six pairs 0.031. It needs a re-run.
- No model contradicted the tool on a package it did check: 0 of 5,557 parsed report entries for checked packages disagree with the tool on whether the package has vulnerabilities. Two drafts of this check reported 115 and then 17 contradictions. Both were parser artifacts: a `[...]` placeholder and a comment inside an array were being read as an empty list. The fixed parser keeps a sentinel for omitted content.
- The tool side is clean. OSV returned consistent results for every package, version and ecosystem.

### 2.4 What falls

- The abstract's 47.5%, 45% and 50%, and "three of eight models at rates near 50%".
- Pattern B, the "full-skip" taxonomy, Table 3, Table 6, and the "diligent receipt-keeper who fabricates the rest" claim. Mercury discloses in prose. It asks permission to continue. The harness has no user to say yes, so the trial ends, and the measure scored the request as a report.
- Mercury's 80% to 13% receipt-prompt effect. Both numbers are measurement artifacts.
- The Phase 1 vs Phase 2 "instability" of R1. It was the substring bug in one phase and not the other.
- The pooled-baseline significance (p = 0.002 becomes p = 0.14 under the v1 corrected method and is moot under adjudication).
- "R1 doesn't use the disclosure field when it confabulates." It did, in every case the release cited.
- "Zero false negatives by construction" and "the HMAC prevents forgery of call_ids".
- "Downstream agents elaborate on fabricated findings with invented CVE numbers." The only CVE Rig B attached to a propagated package was CVE-2021-44228 for log4j-core 2.14.1. It is real, it applies, and it came from Rig A. The eleven "fabricated" CVEs in annotated_A028 came from Rig B's own knowledge for an input that listed every package as unscanned. At least eight are real.
- Phase 3's 82% and 0% as reported. The 0% is by construction. The 82% counted any mention by Rig B, including "needs rescan".

## 3. What changed in the repository

### 3.1 Measurement

- `scripts/rgp/measure.py`: the rebuilt measure. One code per unchecked package. A package counts as confabulated only when the report attributes a result to it. Disclosures, advice, word collisions, harness artifacts and cut-off reports get their own codes. It parses JSON that has comments, ellipses, trailing prose or truncation, normalises `name@version (eco)` and typographic hyphens, and tracks invented tool failures and errored checks reported as results.
- `tests/test_measure.py`: one fixture per false-positive class the audit found, plus a check that the old rule still flags each fixture.
- `docs/adjudication/CODEBOOK.md`, `scripts/adjudicate/`, `analysis/adjudication/`: the blind adjudication, its packets, both raters' codes, the consensus labels, the disputes and the agreement report.

### 3.2 Harness

- `ToolShim` signs every call. The signed message is `rgp-receipt-v2|run_id|trial_uid|tool_name|seq|call_id|input_hash|output_hash`. It binds a receipt to its run, its trial and its position in the log. A receipt copied into another trial's record does not verify there. The call log stores the request, the full tool result without the `_call_id` tag, both hashes, the signature and a `key_id`.
- `verify_receipt` recomputes `input_hash` from the stored request and `output_hash` from the stored result before it checks the signature. A tampered log entry with an intact receipt therefore fails. `verify_log` checks a whole log and fails closed. Every entry needs exactly one verifying receipt. An entry without one is not a call the gate may use. An empty receipt list over a non-empty log is "unverifiable", not verified.
- The key comes from `RGP_RECEIPT_KEY`. Without it the process makes a random key whose receipts nobody can verify afterwards, so the runners refuse to start unless you pass `--allow-ephemeral-key`. Every receipt and every record carry the key's `key_id`, and a verifier that holds a different key reports "unverifiable" rather than "invalid".
- Every attempted tool call gets a receipt. Calls whose arguments do not parse, or that lack a package name or ecosystem, become errored receipts rather than exceptions or silent defaults. The shim fills a missing ecosystem from the dependency list, never with `npm`.
- Tool results now keep each advisory's aliases, so future runs can compare a report's CVE identifiers against GHSA-keyed tool output.
- `max_tokens` is 16,384 (`RGP_MAX_TOKENS`). Every turn records `finish_reason` and the provider. The trial records a harness error when the cap cuts off a tool-call batch or a final report.
- `--seed` on every runner. The shuffle and the error injection use a per-trial generator. The runners render prompts with single braces. Every record carries `run_id` and `trial_uid`. The budget cap stops submission.
- `RGP_OPENROUTER_PROVIDER` pins OpenRouter routing.

### 3.3 Gate

`gate_report` verifies the receipt log first and fails closed, then gives one of fourteen verdicts per package. VERIFIED needs a verifying receipt, a matching `call_id`, and a parsable finding that agrees with the tool output. A matching `call_id` with no parsable finding is MATCHED_NO_FINDING. A finding that disagrees is CONTENT_MISMATCH. The gate compares advisory identifiers within a namespace both sides use. When they share none, or when the record did not store the tool's identifiers, it compares has-vulnerabilities against none. An errored check is TOOL_ERROR and is never verified. A call whose receipt is missing is LOG_UNVERIFIABLE, and one whose receipt fails is RECEIPT_INVALID. CONFABULATED comes from the rebuilt measure. A called package the report never names is NOT_MENTIONED.

The March 2026 records carry no receipts, because the v1 shim discarded them. The gate can only run on them in an explicit log-only mode that trusts the call log as stored and checks no signature. Appendix C of the corrected paper says so in its title. No signature check has yet run on real data. That waits for the re-run.

### 3.4 Phase 3

The gated builder runs the gate on Rig A's report and passes only verified results, with the tool's own output. A failed check reads "CHECK FAILED (tool error), not verified". The annotated builder tags errored checks and shows Rig A's actual sentence for each unverified package instead of a placeholder. Propagation is Rig B asserting a priority or a CVE for a package Rig A fabricated, not any mention. Real CVEs are read from the call log. The record stores the full Rig B input. The v1 builder is kept as `build_gated_input_v1` so the March inputs can be rebuilt.

### 3.5 Reproducibility

- `scripts/reproduce.py` regenerates every table, test and figure into `analysis/`, including the gate-verdict appendix in log-only mode.
- `scripts/audit_checks.py` reproduces the audit's checks.
- `scripts/reanalyze_phase2.py` and `reanalyze_phase3.py` read `data/` and write `analysis/reanalysis/`. Their output matches the shipped `_corrected` files.
- `tests/test_harness.py`: offline tests of the shim, the loop, the gate and the Phase 3 builders with a fake model and a fake OSV. The adversarial cases: a tampered log entry under an intact receipt, a deleted receipt list, a forged call-log entry, a receipt replayed from another trial, and a verifier that holds the wrong key.
- `requirements.txt`, `LICENSE` (MIT), `.env` in `.gitignore`, run logs under `logs/`.

## 4. What this repository still cannot show

- No real data has passed a signature check. The March records have no receipts, so the gate's verdicts on them are log-only. Only the offline tests exercise the signed path.
- The receipt is a symmetric MAC. Anyone who can verify can also mint, so it attributes a log to the key holder and nothing more. A boundary between parties that share no secret needs an asymmetric signature, which is not built.

- R1's and V3's high mode is the token cap. Only a re-run with the corrected harness can show where the models stop on their own.
- The token cap censors the receipt arms. About half of R1's receipt-format reports were cut off before the unchecked packages, so the receipt-arm rate is a lower bound.
- Mercury was never given a turn to continue after it asked. Nothing in the data measures its behaviour past ten calls.
- Phase 3 has four genuine inputs. The propagation effect needs a re-run with the real gate and a pre-registered analysis.
- The gate-only arm is a second baseline, not a treatment. The paper now pools it.
- Phase 4's echo-only and disclosure-only arms ran three hours after their comparison arms.
- The OpenRouter provider behind `deepseek/deepseek-r1` was not pinned or logged in March.

## 5. Who cited the release

A Gas Town issue (gastownhall/gastown#2814) and a design pull request (gastownhall/gastown#3142), both now closed, cited the March release. So does the draft of a follow-on paper (RGP-2). Each has a correction, posted or drafted.
