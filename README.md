# Receipt-Gated Pipelines: Cryptographic Verification of Tool-Call Claims in Multi-Agent LLM Systems

## Abstract

Large language models equipped with tools sometimes skip the tool and fabricate the result. This paper measures silent-skip confabulation across 686 trials spanning 9 models and introduces receipt-gated pipelines — HMAC-SHA256 signed receipts attached to every tool call by a ToolShim, verified post-hoc by a deterministic gate with zero false negatives by construction.

## Key Results

- **3 of 8 models** confabulate tool results at 25–50% rates on a vulnerability-checking task
- **Receipt prompting** reduces Mercury's confabulation from 80% to 13% (p < 0.0000004) and collapses R1's bimodal distribution from 40% low-mode to 2% (p = 0.0000024)
- **Confabulated findings propagate** across agent boundaries in 82% of trials and are elaborated upon in 73%
- **Receipt gate blocks propagation** completely (0%, p = 0.00022)
- **Total cost:** $15.42 across all 4 experimental phases

## For Gas Town / Wasteland Developers

The propagation finding is directly relevant to federated multi-agent architectures like [Gas Town](https://steve-yegge.medium.com/welcome-to-gas-town-4f25ee16dd04) and the [Wasteland](https://steve-yegge.medium.com/welcome-to-the-wasteland-a-thousand-gas-towns-a5eb9bc8dc1f).

**The problem:** When completions cross rig boundaries, confabulated tool results propagate and get elaborated. In a two-rig simulation (DeepSeek R1 → Gemini Flash), the downstream agent reads a fabricated log4j-core finding, assigns it CRITICAL priority, cites CVE-2021-44228, recommends a specific patch version, and passes that downstream. The output looks more authoritative than the input. 82% of confab-input trials propagated; 73% showed elaboration.

**The fix:** A deterministic receipt gate that verifies tool-call claims before completions cross rig boundaries. Zero propagation in the gated condition. The gate integrates naturally with the Wasteland's existing stamp-based trust system — a rig that submits verified completions builds trust; one that submits confabulated claims loses it.

**Key architectural components:**
1. **ToolShim** — wraps tool calls with HMAC-SHA256 signed receipts (UUID + hash of input/output)
2. **Receipt gate** — deterministic verifier that classifies each claimed result as VERIFIED, CONFABULATED, or SELF_REPORTED_UNVERIFIED
3. **Structured receipt prompt** — ~100 tokens added to the system message; reduces confabulation by making gaps visible in the output format

The ToolShim and gate implementations are in [`scripts/phase2.py`](scripts/phase2.py). The receipt prompt texts are in the paper's Appendix G.

## Reading the Paper

The paper is available in three formats:
- [`receipt-gated-pipelines.pdf`](receipt-gated-pipelines.pdf) — 27-page PDF with figures
- [`receipt-gated-pipelines.md`](receipt-gated-pipelines.md) — Markdown source
- [`receipt-gated-pipelines.tex`](receipt-gated-pipelines.tex) — LaTeX source

## Repository Structure

```
├── receipt-gated-pipelines.md   # Paper (markdown)
├── receipt-gated-pipelines.tex  # Paper (LaTeX)
├── receipt-gated-pipelines.pdf  # Paper (compiled)
├── data/
│   ├── deps_30.json             # 30-dependency test list
│   ├── deps_100.json            # 100-dependency test list
│   ├── phase1/                  # 11 JSONL files, 197 trials across 9 models
│   ├── phase2/                  # 13 JSONL files (raw + corrected), 320 trials
│   ├── phase3/                  # 2 JSONL files (raw + corrected), 90 trials
│   └── phase4/                  # 2 JSONL files, 80 trials
├── scripts/
│   ├── phase1.py                # Phase 1 experiment runner
│   ├── phase1_multimodel.py     # Multi-model Phase 1 variant
│   ├── analyze_phase1.py        # Phase 1 analysis
│   ├── phase2.py                # Phase 2 runner (includes ToolShim, receipt gate)
│   ├── phase3.py                # Phase 3 two-rig propagation experiment
│   ├── phase4.py                # Phase 4 disentanglement experiment
│   ├── reanalyze_phase2.py      # Measurement correction script (Bug 1 + Bug 2)
│   └── reanalyze_phase3.py      # Phase 3 Rig A reclassification script
├── figures/
│   ├── fig1_architecture.png
│   ├── fig2_bimodal.png
│   ├── fig3_propagation.png
│   └── fig4_factorial.png
└── README.md
```

## Verifying Claims from Raw Data

The experiment scripts require API keys, but all results can be verified from the included data without re-running experiments.

### Verify Table 2 (R1 Phase 2 confabulation rates)

```python
import json

trials = []
for f in ['data/phase2/phase2_20260314_061615_corrected.jsonl',
          'data/phase2/phase2_deepseek-r1_20260314_080559_corrected.jsonl']:
    with open(f) as fh:
        for line in fh:
            trials.append(json.loads(line))

for cond in ['baseline', 'receipt_prompt', 'gate_only', 'receipt_gate']:
    s = [t for t in trials if t['condition_key'] == cond]
    confab = sum(1 for t in s if t['confab_corrected_count'] > 0)
    print(f"{cond}: {confab}/{len(s)} = {confab/len(s)*100:.1f}%")
```

### Verify Table 4 (Phase 3 propagation rates)

```python
import json

with open('data/phase3/phase3_gemini-flash_20260314_103603_corrected.jsonl') as fh:
    trials = [json.loads(line) for line in fh]

for cond in ['ungated', 'gated', 'annotated']:
    ci = [t for t in trials if t['condition_key'] == cond and t['is_confab_input_corrected']]
    prop = sum(1 for t in ci if t['propagation_count'] > 0)
    elab = sum(1 for t in ci if t['elaboration_count'] > 0)
    print(f"{cond}: propagation {prop}/{len(ci)}, elaboration {elab}/{len(ci)}")
```

### Recompute Fisher exact tests

```python
from scipy.stats import fisher_exact

# Gate blocks propagation: 9/11 ungated vs 0/11 gated
_, p = fisher_exact([[9, 2], [0, 11]])
print(f"Ungated vs gated: p = {p:.6f}")  # 0.000221

# Mercury confab reduction: 24/30 baseline vs 4/30 receipt
_, p = fisher_exact([[24, 6], [4, 26]])
print(f"Mercury baseline vs receipt: p = {p:.8f}")  # 0.00000033
```

## Data Format

Each JSONL file contains one JSON object per trial. Key fields:

| Field | Description |
|---|---|
| `trial_id` | Unique trial identifier |
| `model_key` / `model` | Model identifier |
| `condition_key` | Experimental condition |
| `tool_calls_made` | Number of actual tool invocations |
| `claimed_but_not_called_count` | Packages claimed without tool call (pre-correction) |
| `confab_corrected_count` | Corrected confabulation count (in `_corrected` files) |
| `coverage_rate` | Fraction of expected packages actually checked |
| `gate_summary` | Receipt gate verdict counts (Phase 2+) |
| `self_reported_unverified_count` | Packages honestly reported as unchecked |
| `final_text` | Model's complete output text |
| `call_log` | Full tool call log with timestamps |

### Measurement Corrections

The `_corrected.jsonl` files contain reanalyzed data fixing two measurement bugs documented in the paper (Section 3.4). The correction scripts are included:

1. **`reanalyze_phase2.py`** — Fixes substring matching (Bug 1) and unverified field overcounting (Bug 2)
2. **`reanalyze_phase3.py`** — Reclassifies 3 Rig A trials whose confabulation was solely from substring false positives (`ini`, `ms`)

All numbers in the paper use corrected measurements. Raw files are included for transparency.

## License

MIT

## Citation

```
Ledbetter, S. (2026). Receipt-Gated Pipelines: Cryptographic Verification of
Tool-Call Claims in Multi-Agent LLM Systems.
```
