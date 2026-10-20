# Receipt-Gated Pipelines

**Tool-call verification for multi-agent LLM systems, and what a bad measure did to the first version of this study**

Steven M. Ledbetter (Independent Researcher). First release March 2026. Corrected release October 2026.

**Read:** [CORRECTIONS.md](CORRECTIONS.md) first, then the corrected paper: [Markdown](receipt-gated-pipelines.md) | [PDF](receipt-gated-pipelines.pdf). The March 2026 paper is kept as [receipt-gated-pipelines-v1.md](receipt-gated-pipelines-v1.md) and [v1 PDF](receipt-gated-pipelines-v1.pdf).

## What changed

The March 2026 release reported that three of eight models fabricate tool results at rates near 50%, that a receipt prompt cut Mercury 2's rate from 80% to 13%, and that fabricated findings propagate across an agent boundary 82% of the time. An external audit in October 2026 showed that the measurement code counted honest disclosure as fabrication, that the harness's 4,096-token output cap set the "76-call ceiling" the paper attributed to the model, that the HMAC receipts were never verified, and that the Phase 3 gated condition never ran the gate. [CORRECTIONS.md](CORRECTIONS.md) has the full list.

Every trial that names an unchecked package was re-coded by two blind raters. The corrected numbers:

| | v1 paper | Adjudicated |
|---|---|---|
| DeepSeek R1 fabricates a result (Phase 1, all conditions) | 47.5% (19/40) | 12.5% (5/40) |
| DeepSeek V3 (Phase 1) | 45% (9/20) | 5% (1/20) |
| Mercury 2 (Phase 1) | 50% (11/22) | 0% (0/22) |
| Mercury 2, baseline to receipt prompt (Phase 2) | 80% to 13% | 0% to 0% |
| R1, loose prompt vs receipt prompt (Phase 2, pooled) | not reported | 8/100 vs 1/100, p = 0.035 |
| R1 low-mode trials, loose vs receipt prompt | 40% to 2% | 52/100 vs 2/100, p = 3e-17 |
| Propagation, ungated vs annotated (Phase 3, genuine inputs) | 82% vs 18% | 4/4 vs 0/4 |
| Trials with a fabricated result, all phases | 118 of 589 | 19 of 589 |

What survives: R1 sometimes writes a scan result for a package it never checked, and sometimes invents a tool failure for one. A structured output format stops R1 from quitting early. In the few genuine cases, a fabricated finding propagated to a downstream agent every time it was passed through untagged and never when it was tagged. What does not survive: the headline rates, Mercury's confabulation, the "diligent receipt-keeper" claim, and "zero false negatives by construction".

## Reproduce

```bash
uv venv --python 3.13 .venv && uv pip install -r requirements.txt
.venv/bin/python scripts/reproduce.py       # every table, test and figure -> analysis/
.venv/bin/python scripts/audit_checks.py    # the audit's own checks, from the shipped data
.venv/bin/python -m pytest tests            # 62 offline tests
```

No step above calls an API. The raw trial records are in `data/phase1/` to `data/phase4/` (28 JSONL files, 589 production trials plus smoke tests). The adjudication is in `analysis/adjudication/`: the codebook, the packets both raters saw, both raters' codes, the consensus, the disputes and the agreement report.

## Layout

| Path | What |
|---|---|
| `scripts/phase1.py` to `phase4.py` | Experiment runners. ToolShim, receipts, gate, agent loop. Corrected, see CORRECTIONS.md section 3. |
| `scripts/rgp/` | Shared analysis code: loaders, name normalisation, tolerant JSON recovery, the rebuilt measure, statistics. |
| `scripts/reproduce.py` | One command regenerates `analysis/numbers.json`, `analysis/tables/`, `analysis/figures/`. |
| `scripts/audit_checks.py` | Reproduces the October 2026 audit's quantitative claims. |
| `scripts/adjudicate/` | Builds blind-rater packets and scores agreement. |
| `scripts/reanalyze_phase2.py`, `reanalyze_phase3.py` | The v1 "corrected method", kept for comparison. Reads `data/`, writes `analysis/reanalysis/`. |
| `tests/` | `test_measure.py` (fixtures for every false-positive class) and `test_harness.py` (shim, loop, gate, Phase 3 builders, offline). |
| `docs/adjudication/CODEBOOK.md` | The rater codebook. |
| `data/` | Dependency lists and the 28 trial files. |
| `logs/` | The March 2026 run logs. |
| `figures/` | v1 figures. Corrected figures are in `analysis/figures/`. |

## Running new trials

The runners need `OPENROUTER_API_KEY`, `INCEPTION_API_KEY` and `ANTHROPIC_API_KEY` in a `.env` file at the repo root (`.env` is git-ignored). Set `RGP_RECEIPT_KEY` to sign receipts with a fixed key, `RGP_MAX_TOKENS` to change the output cap (default 16,384), and `RGP_OPENROUTER_PROVIDER` to pin OpenRouter routing. Pass `--seed` to make the dependency shuffle and the error injection reproducible.

```bash
.venv/bin/python scripts/phase2.py --model deepseek-r1 --trials 25 --seed 1
```

Every record now carries `run_id`, `seed`, `max_tokens`, `harness_errors`, the receipts with their signatures, the full tool results, `finish_reason` and provider per turn, and the rebuilt measure's verdict under `measure`.

## License

MIT. See [LICENSE](LICENSE).
