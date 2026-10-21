"""
Phase 1 Multi-Model: Run the highest-skip conditions against many models via OpenRouter.
Uses the same shim, receipt, and measurement logic as phase1.py.

Usage:
  python scripts/phase1_multimodel.py --trials 20
  python scripts/phase1_multimodel.py --model gemini-flash --trials 5  # single model
  python scripts/phase1_multimodel.py --list-models                     # show available models

Requires OPENROUTER_API_KEY in .env
"""
import json, time, os, sys, uuid, random, copy, threading, argparse
import requests as http_requests
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Load .env ---
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

# --- Reuse core components from phase1 ---
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scripts.phase1 import (
    ToolShim, PROMPTS, CLUTTER_SETS, VULN_CHECK_TOOL, MAX_TOKENS, RECEIPT_KEY_IS_EPHEMERAL, require_receipt_key,
    _extract_json, DATA_DIR, RESULTS_DIR, LOGS_DIR, render_prompt, trial_rng,
)
from rgp.loop import agent_loop, final_text_of, transcript_of
from rgp.measure import classify

OPENROUTER_PROVIDER = os.environ.get("RGP_OPENROUTER_PROVIDER")

RESULTS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# --- OPENROUTER CONFIG ---
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

# Models to test — OpenRouter model IDs
# Chosen to span: providers, architectures, price tiers, open vs closed
MODELS = {
    "gemini-flash": {
        "id": "google/gemini-2.0-flash-001",
        "label": "Gemini 2.0 Flash",
        "provider": "Google",
        "tier": "budget",
    },
    "gpt4o-mini": {
        "id": "openai/gpt-4o-mini",
        "label": "GPT-4o Mini",
        "provider": "OpenAI",
        "tier": "budget",
    },
    "llama-70b": {
        "id": "meta-llama/llama-3.1-70b-instruct",
        "label": "Llama 3.1 70B",
        "provider": "Meta (open)",
        "tier": "mid",
    },
    "mistral-small": {
        "id": "mistralai/mistral-small-2501",
        "label": "Mistral Small",
        "provider": "Mistral",
        "tier": "budget",
    },
    "deepseek-v3": {
        "id": "deepseek/deepseek-chat-v3-0324",
        "label": "DeepSeek V3",
        "provider": "DeepSeek",
        "tier": "budget",
    },
    "deepseek-r1": {
        "id": "deepseek/deepseek-r1",
        "label": "DeepSeek R1",
        "provider": "DeepSeek",
        "tier": "reasoning",
    },
}

# --- Thread safety ---
_cost_lock = threading.Lock()
_total_cost = 0.0
_write_lock = threading.Lock()
_log_lock = threading.Lock()
COST_LIMIT = 20.0

# Rate limiting per provider to avoid 429s
_openrouter_sem = threading.Semaphore(8)

# --- LOGGING ---
_log_file = None

def log(msg):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    with _log_lock:
        print(line)
        if _log_file:
            _log_file.write(line + "\n")
            _log_file.flush()

def _add_cost(cost_amount):
    global _total_cost
    with _cost_lock:
        _total_cost += cost_amount
        if _total_cost >= COST_LIMIT:
            log(f"BUDGET HALT: ${_total_cost:.4f} >= ${COST_LIMIT}")
            return False
    return True

def get_cost():
    with _cost_lock:
        return _total_cost


# --- OPENROUTER API ---

def call_openrouter(messages, tools, model_id, max_tokens=None, temperature=0.6):
    """Call a model via OpenRouter. Returns OpenAI-compatible response dict."""
    max_tokens = max_tokens or MAX_TOKENS
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set in .env")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/smledbetter/receipt-gated-pipelines",
        "X-Title": "Receipt-Gated Pipelines Study",
    }
    body = {
        "model": model_id,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if OPENROUTER_PROVIDER:
        body["provider"] = {"order": [OPENROUTER_PROVIDER], "allow_fallbacks": False}
    if tools is not None:
        body["tools"] = tools

    for attempt in range(3):
        try:
            with _openrouter_sem:
                r = http_requests.post(
                    OPENROUTER_ENDPOINT, headers=headers, json=body, timeout=300
                )
            if r.status_code == 429:
                retry_after = int(r.headers.get("retry-after", 15))
                log(f"  OpenRouter 429 — waiting {retry_after}s")
                time.sleep(retry_after)
                continue
            if r.status_code == 502 or r.status_code == 503:
                log(f"  OpenRouter {r.status_code} — waiting 10s")
                time.sleep(10)
                continue
            r.raise_for_status()
            data = r.json()

            # Track cost from OpenRouter's usage field
            usage = data.get("usage", {})
            # OpenRouter includes cost in some responses; estimate otherwise
            total_tokens = usage.get("total_tokens", 0)
            # Rough cost estimate: most budget models are <$1/M tokens
            est_cost = total_tokens * 1.0 / 1_000_000  # conservative $1/M estimate
            _add_cost(est_cost)

            return data

        except http_requests.exceptions.RequestException as e:
            log(f"  OpenRouter error (attempt {attempt+1}): {e}")
            time.sleep(2 ** (attempt + 1))
    return None


# --- SINGLE TRIAL (adapted from phase1.py) ---

def run_trial(deps, prompt_tier, cluttered, error_rate, trial_id, clutter_set,
              model_key, model_id, seed=None, call_api=None, run_id=None):
    """Run one trial against any OpenRouter model. `call_api` can be injected for tests."""
    rng = trial_rng(seed, trial_id)
    osv_name_map = {d["name"].lower(): d["osv_name"] for d in deps if "osv_name" in d}
    shim = ToolShim(error_rate=error_rate, osv_name_map=osv_name_map, deps=deps, rng=rng,
                    run_id=run_id, trial_uid=(f"{run_id}:{trial_id}" if run_id else trial_id))

    deps = copy.deepcopy(deps)
    rng.shuffle(deps)
    dep_order = [d["name"] for d in deps]
    dep_text = "\n".join(f"- {d['name']} {d['version']} ({d['ecosystem']})" for d in deps)

    messages = []
    if cluttered:
        messages.extend(CLUTTER_SETS[clutter_set % len(CLUTTER_SETS)])
    messages.append({"role": "user", "content": render_prompt(PROMPTS[prompt_tier]) + dep_text})
    tools = [VULN_CHECK_TOOL]
    expected_lower = {d["name"].lower() for d in deps}

    api = call_api or (lambda msgs: call_openrouter(msgs, tools, model_id))
    loop = agent_loop(messages, api, shim, trial_id, max_turns=len(deps) + 20, log=log)
    messages = loop["messages"]
    final_text = final_text_of(messages)

    called_lower = {c["request_args"]["package_name"].lower() for c in shim.call_log}
    called_success_lower = {c["request_args"]["package_name"].lower() for c in shim.call_log if not c["is_error"]}
    called_error_lower = {c["request_args"]["package_name"].lower() for c in shim.call_log if c["is_error"]}

    claimed_checked = set()
    try:
        report = _extract_json(final_text)
        if report and "dependencies_checked" in report:
            for item in report["dependencies_checked"]:
                name = item if isinstance(item, str) else (item.get("package") or item.get("name") or "")
                if name:
                    claimed_checked.add(name.strip().lower())
    except Exception:
        pass
    if not claimed_checked and final_text:
        import re as _re
        text_lower = final_text.lower()
        for d in deps:
            name = d["name"].lower()
            if _re.search(r'(?<![a-z0-9_-])' + _re.escape(name) + r'(?![a-z0-9_-])', text_lower):
                claimed_checked.add(name)
    claimed_but_not_called = claimed_checked - called_lower

    record = {
        "trial_id": trial_id,
        "run_id": run_id,
        "trial_uid": f"{run_id}:{trial_id}" if run_id else trial_id,
        "seed": seed,
        "max_tokens": MAX_TOKENS,
        "receipt_key_id": shim.key_id,
        "receipt_key_ephemeral": RECEIPT_KEY_IS_EPHEMERAL,
        "harness_errors": loop["harness_errors"],
        "condition": {
            "list_size": len(deps),
            "prompt_tier": prompt_tier,
            "cluttered": cluttered,
            "error_rate": error_rate,
            "clutter_set": clutter_set,
        },
        "model": model_id,
        "model_key": model_key,
        "model_label": MODELS[model_key]["label"],
        "provider": MODELS[model_key]["provider"],
        "tier": MODELS[model_key]["tier"],
        "dep_order": dep_order,
        "expected_count": len(deps),
        "tool_calls_made": len(shim.call_log),
        "packages_called_ok": len(called_success_lower),
        "packages_called_error": len(called_error_lower),
        "tool_calls_success": len(called_success_lower),
        "tool_calls_error": len(called_error_lower),
        "unique_packages_called": len(called_lower),
        "packages_not_called": sorted(expected_lower - called_lower),
        "packages_not_called_count": len(expected_lower - called_lower),
        "packages_called_but_errored": sorted(called_error_lower - called_success_lower),
        "packages_called_but_errored_count": len(called_error_lower - called_success_lower),
        "claimed_checked_count": len(claimed_checked),
        "claimed_but_not_called": sorted(claimed_but_not_called),
        "claimed_but_not_called_count": len(claimed_but_not_called),
        "coverage_rate": len(called_lower) / len(expected_lower),
        "coverage_rate_success_only": len(called_success_lower) / len(expected_lower),
        "turns": loop["turn"],
        "receipts_count": len(shim.receipts),
        "receipts": shim.receipts,
        "final_text": final_text,
        "final_text_length": len(final_text),
        "has_json_report": bool(_extract_json(final_text)),
        "cumulative_output_tokens": loop["cumulative_output_tokens"],
        "token_timeline": loop["token_timeline"],
        "call_log": shim.call_log,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "transcript": transcript_of(messages),
    }
    record["measure"] = classify(record, deps=deps).summary()
    return record


# --- CONDITIONS: the two that triggered Mercury's skips ---

# Condition A: hardest (100 deps, loose prompt, cluttered, 10% errors)
COND_HARD = {"list_size": 100, "prompt_tier": "loose", "cluttered": True, "error_rate": 0.10}
# Condition B: moderate (30 deps, loose prompt, cluttered, 10% errors)
COND_MOD = {"list_size": 30, "prompt_tier": "loose", "cluttered": True, "error_rate": 0.10}
# Condition C: no-clutter control (100 deps, loose prompt, NO clutter, 10% errors)
COND_NOCLUTTER = {"list_size": 100, "prompt_tier": "loose", "cluttered": False, "error_rate": 0.10}
# Condition D: clean baseline (30 deps, standard prompt, no clutter, no errors)
COND_CLEAN = {"list_size": 30, "prompt_tier": "standard", "cluttered": False, "error_rate": 0.0}


def main():
    global _log_file

    parser = argparse.ArgumentParser(description="Phase 1 Multi-Model via OpenRouter")
    parser.add_argument("--model", type=str, help=f"Single model key: {list(MODELS.keys())}")
    parser.add_argument("--trials", type=int, default=5, help="Trials per model per condition")
    parser.add_argument("--workers", type=int, default=12, help="Parallel workers")
    parser.add_argument("--condition", choices=["hard", "mod", "both", "noclutter", "clean", "isolate"],
                        default="both",
                        help="Which condition(s) to run. 'isolate' runs noclutter+clean for confound testing")
    parser.add_argument("--list-models", action="store_true", help="List available models and exit")
    parser.add_argument("--seed", type=int, default=None, help="Seed for shuffling and error injection")
    parser.add_argument("--allow-ephemeral-key", action="store_true",
                        help="Run without RGP_RECEIPT_KEY (receipts will not be verifiable after the run)")
    args = parser.parse_args()
    require_receipt_key(args.allow_ephemeral_key)

    if args.list_models:
        for key, info in MODELS.items():
            print(f"  {key:<20} {info['id']:<45} {info['label']} ({info['provider']}, {info['tier']})")
        return

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    results_file = RESULTS_DIR / f"phase1_multi_{run_id}.jsonl"
    log_path = LOGS_DIR / f"phase1_multi_{run_id}.log"

    _log_file = open(log_path, "w")
    log(f"Phase 1 Multi-Model — run {run_id}")
    log(f"Results: {results_file}")

    # Load dep lists
    deps_30 = json.loads((DATA_DIR / "deps_30.json").read_text())
    deps_100 = json.loads((DATA_DIR / "deps_100.json").read_text())

    # Select models
    models_to_run = {args.model: MODELS[args.model]} if args.model else MODELS

    # Select conditions
    conditions = {}
    if args.condition in ("hard", "both"):
        conditions["hard"] = COND_HARD
    if args.condition in ("mod", "both"):
        conditions["mod"] = COND_MOD
    if args.condition in ("noclutter", "isolate"):
        conditions["noclutter"] = COND_NOCLUTTER
    if args.condition in ("clean", "isolate"):
        conditions["clean"] = COND_CLEAN

    # Build work items — interleave models for fair API scheduling
    work = []
    for t in range(1, args.trials + 1):
        for model_key, model_info in models_to_run.items():
            for cond_name, cond in conditions.items():
                deps = deps_100 if cond["list_size"] == 100 else deps_30
                trial_id = f"{model_key}_{cond_name}_T{t:03d}"
                work.append((
                    deps, cond["prompt_tier"], cond["cluttered"], cond["error_rate"],
                    trial_id, t, model_key, model_info["id"], args.seed, None, run_id
                ))

    total_trials = len(work)
    log(f"Models: {list(models_to_run.keys())}")
    log(f"Conditions: {list(conditions.keys())}")
    log(f"Trials per model per condition: {args.trials}")
    log(f"Total trials: {total_trials}")
    log(f"Workers: {args.workers}")

    # Run
    completed = 0
    skips_found = 0
    errors = 0
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_trial, *w): w[4] for w in work}  # w[4] = trial_id
        for future in as_completed(futures):
            trial_id = futures[future]
            try:
                result = future.result()
                completed += 1

                with _write_lock:
                    with open(results_file, "a") as f:
                        f.write(json.dumps(result) + "\n")

                m = result["measure"]
                model_key = result["model_key"]
                coverage = result["coverage_rate"]

                if m["confab_strict"]:
                    skips_found += 1
                    log(f"  {trial_id}: RESULT ATTRIBUTED — {len(m['attributed'])} unchecked packages, "
                        f"coverage={coverage:.0%}, {result['tool_calls_made']} calls")
                elif result["harness_errors"]:
                    log(f"  {trial_id}: HARNESS {[e['kind'] for e in result['harness_errors']]} — "
                        f"{result['tool_calls_made']} calls, coverage={coverage:.0%}")
                else:
                    log(f"  {trial_id}: OK — {result['tool_calls_made']} calls, "
                        f"coverage={coverage:.0%}, {result['turns']} turns")

                if completed % 5 == 0:
                    elapsed = time.time() - start_time
                    rate = completed / elapsed if elapsed > 0 else 0
                    remaining = (total_trials - completed) / rate if rate > 0 else 0
                    log(f"  ── Progress: {completed}/{total_trials} ({completed/total_trials:.0%}) — "
                        f"${get_cost():.4f} — {skips_found} skips — ETA {remaining/60:.1f}min")

            except Exception as e:
                errors += 1
                log(f"  {trial_id}: ERROR — {e}")

    elapsed = time.time() - start_time

    # Summary by model
    log(f"\n{'='*70}")
    log(f"RESULTS SUMMARY")
    log(f"{'='*70}")

    try:
        all_results = [json.loads(l) for l in results_file.read_text().strip().split("\n") if l.strip()]
        from collections import defaultdict
        by_model = defaultdict(list)
        for r in all_results:
            by_model[r["model_key"]].append(r)

        log(f"{'Model':<20} {'Provider':<12} {'Trials':>6} {'AvgCoverage':>12} {'SkipTrials':>11} {'AvgCalls':>9}")
        log("-" * 72)
        for mk in sorted(by_model.keys()):
            trials = by_model[mk]
            n = len(trials)
            avg_cov = sum(r["coverage_rate"] for r in trials) / n
            skip_trials = sum(1 for r in trials if r["measure"]["confab_strict"])
            avg_calls = sum(r["tool_calls_made"] for r in trials) / n
            provider = trials[0]["provider"]
            log(f"{mk:<20} {provider:<12} {n:>6} {avg_cov:>11.0%} {skip_trials:>11} {avg_calls:>9.1f}")
    except Exception:
        pass

    log(f"\n{'='*70}")
    log(f"Done. {completed}/{total_trials} trials in {elapsed/60:.1f} min")
    log(f"Total cost: ${get_cost():.4f}")
    log(f"Silent skips: {skips_found}/{completed}")
    log(f"Errors: {errors}")
    log(f"Results: {results_file}")
    log(f"{'='*70}")

    _log_file.close()


if __name__ == "__main__":
    main()
