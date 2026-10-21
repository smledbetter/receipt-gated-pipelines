"""Load trial records from data/ and tag them.

Every record gets these extra keys:
  _file    file name
  _phase   1, 2, 3 or 4
  _smoke   True for smoke-test files (Appendix E lists them)
  _model   a short model key that is stable across phases
"""
import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "data"

# Files that hold the production trials the paper reports on. Everything else
# under data/ is a smoke test or a derived _corrected file.
PRODUCTION_FILES = {
    1: {
        "phase1_20260314_031057.jsonl",
        "phase1_haiku_20260314_031920.jsonl",
        "phase1_haiku_20260314_032017.jsonl",
        "phase1_haiku_20260314_032338.jsonl",
        "phase1_haiku_20260314_032639.jsonl",
        "phase1_mercury2_20260314_043201.jsonl",
        "phase1_multi_20260314_034251.jsonl",
        "phase1_multi_20260314_034318.jsonl",
        "phase1_multi_20260314_040629.jsonl",
        "phase1_multi_20260314_043140.jsonl",
        "phase1_sonnet_20260314_032017.jsonl",
    },
    2: {
        "phase2_20260314_061615.jsonl",
        "phase2_deepseek-r1_20260314_080559.jsonl",
        "phase2_mercury_20260314_071636.jsonl",
        "phase2_mercury_20260314_080559.jsonl",
    },
    3: {"phase3_gemini-flash_20260314_103603.jsonl"},
    4: {"phase4_deepseek-r1_20260314_112512.jsonl", "phase4_mercury_20260314_113517.jsonl"},
}

MODEL_KEYS = {
    "mercury-2": "mercury",
    "claude-haiku-4-5-20251001": "haiku-4.5",
    "claude-sonnet-4-6": "sonnet-4.6",
    "deepseek/deepseek-r1": "deepseek-r1",
}


def _deps(name):
    return json.loads((DATA / name).read_text())


DEPS_100 = _deps("deps_100.json")
DEPS_30 = _deps("deps_30.json")


def deps_for(record):
    """Return the dependency list a trial used."""
    if "condition" in record and isinstance(record["condition"], dict):
        size = record["condition"].get("list_size")
    else:
        size = record.get("list_size", record.get("expected_count"))
    if size is None:
        size = record.get("expected_count", 100)
    return DEPS_100 if size == 100 else DEPS_30


def model_key(record):
    raw = record.get("model_key") or record.get("model") or "unknown"
    return MODEL_KEYS.get(raw, raw)


def load_phase(phase, production_only=True, corrected=False):
    """Load the records of one phase.

    corrected=True loads the *_corrected.jsonl files instead of the raw files
    (only Phases 2 and 3 have them).
    """
    out = []
    for path in sorted(glob.glob(str(DATA / f"phase{phase}" / "*.jsonl"))):
        name = Path(path).name
        is_corr = name.endswith("_corrected.jsonl")
        if corrected != is_corr:
            continue
        base = name.replace("_corrected", "")
        smoke = base not in PRODUCTION_FILES[phase]
        if production_only and smoke:
            continue
        for line in open(path):
            if not line.strip():
                continue
            r = json.loads(line)
            r["_file"] = name
            r["_phase"] = phase
            r["_smoke"] = smoke
            r["_model"] = model_key(r)
            out.append(r)
    return out


def tool_condition(record):
    """False for the Phase 1 no-tool control (condition 7)."""
    cond = record.get("condition")
    if isinstance(cond, dict):
        return cond.get("prompt_tier") != "no_tool"
    return True


def prompt_kind(record):
    """loose | standard | precise | receipt | echo_only | disclosure_only | no_tool."""
    cond = record.get("condition")
    if isinstance(cond, dict):
        return cond.get("prompt_tier", "loose")
    ck = record.get("condition_key", "")
    if ck in ("baseline", "gate_only"):
        return "loose"
    if ck in ("receipt_prompt", "receipt_gate"):
        return "receipt"
    return ck or "loose"
