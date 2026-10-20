#!/usr/bin/env python3
"""Regenerate every number, table and figure in the corrected paper from data/.

    .venv/bin/python scripts/reproduce.py

Writes analysis/numbers.json, analysis/tables/*.md and analysis/figures/*.png.
No API calls. Deterministic.
"""
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from rgp import jsonrecover  # noqa: E402
from rgp.loaders import DEPS_100, load_phase, tool_condition, deps_for as deps_for_record  # noqa: E402
from rgp.measure import classify  # noqa: E402
from rgp.names import DepIndex, called_packages, attempted_packages  # noqa: E402
from rgp.stats import fisher, mannwhitney, mcnemar_exact, rate, wilson  # noqa: E402
from reanalyze_phase2 import recompute_confab  # noqa: E402

OUT = ROOT / "analysis"
TABLES = OUT / "tables"
FIGS = OUT / "figures"
NUMBERS = {}
LOW_MODE = 30

# Adjudicated labels: every production trial that names an unchecked package
# was coded by two blind raters (docs/adjudication/CODEBOOK.md). A trial with
# no such mention has nothing to adjudicate and counts as not confabulating.
_LABELS_PATH = OUT / "adjudication" / "consensus_labels.json"
_CONS_PATH = OUT / "adjudication" / "consensus.json"
LABELS = json.loads(_LABELS_PATH.read_text()) if _LABELS_PATH.exists() else {}
CONSENSUS = json.loads(_CONS_PATH.read_text()) if _CONS_PATH.exists() else {}


def trial_key(r):
    return f"{r['_file'].replace('.jsonl', '')}::{r['trial_id']}"


def adjudicated(r, which="strict"):
    lab = LABELS.get(trial_key(r))
    if lab is None:
        return False
    return lab[which]


def adjudicated_codes(r):
    """{package: (code, parametric)} for the packages both raters agreed on."""
    c = CONSENSUS.get(trial_key(r), {}).get("codes", {})
    return {p: (v["code"], v["parametric"]) for p, v in c.items() if v["status"] == "agreed"}


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def write_table(name, title, headers, rows, notes=""):
    TABLES.mkdir(parents=True, exist_ok=True)
    body = f"# {title}\n\n{md_table(headers, rows)}\n"
    if notes:
        body += f"\n{notes}\n"
    (TABLES / f"{name}.md").write_text(body)


def per_trial(r):
    v = classify(r)
    adj = adjudicated_codes(r)
    attempted = attempted_packages(r, DepIndex(deps_for_record(r)))
    return {
        "adj_R": sorted(p for p, (c, _) in adj.items() if c == "R"),
        "adj_invented_failure": sorted(p for p, (c, _) in adj.items() if c == "F" and p not in attempted),
        "adj_D": sorted(p for p, (c, _) in adj.items() if c == "D"),
        "trial_id": r["trial_id"], "file": r["_file"], "model": r["_model"],
        "calls": r["tool_calls_made"], "coverage": r["coverage_rate"],
        "old_raw": r["claimed_but_not_called_count"] > 0,
        "old_corrected": recompute_confab(r)[0] > 0,
        "strict": v.confab_strict, "lenient": v.confab_lenient,
        "adj_strict": adjudicated(r, "strict"), "adj_lenient": adjudicated(r, "lenient"),
        "adj_undecided": adjudicated(r, "strict") is None,
        "attributed": v.attributed, "parametric": v.parametric,
        "invented_failure": v.invented_failure, "accurate_failure": v.accurate_failure,
        "disclosed": v.disclosed, "censored": v.censored, "truncated": v.truncated,
        "error_reported": v.error_reported_as_result,
        "harness": v.harness_artifact, "json_parsed": v.json_parsed,
        "n_uncalled": len(v.codes), "codes": v.summary()["codes"],
        "low_mode": r["tool_calls_made"] <= LOW_MODE,
    }


def summarise(rows):
    n = len(rows)
    return {
        "n": n,
        "old_raw": sum(x["old_raw"] for x in rows),
        "old_corrected": sum(x["old_corrected"] for x in rows),
        "strict": sum(x["strict"] for x in rows),
        "lenient": sum(x["lenient"] for x in rows),
        "adj_strict": sum(1 for x in rows if x["adj_strict"] is True),
        "adj_lenient": sum(1 for x in rows if x["adj_lenient"] is True),
        "adj_undecided": sum(1 for x in rows if x["adj_strict"] is None),
        "adj_strict_ci": wilson(sum(1 for x in rows if x["adj_strict"] is True), n),
        "adj_invented_failure": sum(1 for x in rows if x["adj_invented_failure"]),
        "adj_disclosed": sum(1 for x in rows if x["adj_D"]),
        "error_reported_as_result": sum(1 for x in rows if x["error_reported"]),
        "invented_failure": sum(bool(x["invented_failure"]) for x in rows),
        "disclosed": sum(bool(x["disclosed"]) for x in rows),
        "censored": sum(x["censored"] for x in rows),
        "harness": sum(x["harness"] for x in rows),
        "low_mode": sum(x["low_mode"] for x in rows),
        "mean_coverage": sum(x["coverage"] for x in rows) / n if n else float("nan"),
        "strict_ci": wilson(sum(x["strict"] for x in rows), n),
    }


# ----------------------------------------------------------------- Phase 1
def phase1():
    recs = [r for r in load_phase(1) if tool_condition(r)]
    rows = [per_trial(r) for r in recs]
    by_model = defaultdict(list)
    for x in rows:
        by_model[x["model"]].append(x)
    order = ["deepseek-r1", "deepseek-v3", "mercury", "gemini-flash", "haiku-4.5", "sonnet-4.6",
             "gpt4o-mini", "llama-70b", "mistral-small"]
    table = []
    NUMBERS["phase1"] = {}
    for m in order:
        if m not in by_model:
            continue
        s = summarise(by_model[m])
        NUMBERS["phase1"][m] = s
        table.append([m, s["n"], f"{s['old_raw']} ({s['old_raw'] / s['n']:.1%})",
                      f"{s['old_corrected']} ({s['old_corrected'] / s['n']:.1%})",
                      rate(s["adj_strict"], s["n"]), s["adj_lenient"], s["adj_invented_failure"],
                      s["error_reported_as_result"], s["strict"], s["harness"]])
    write_table("table1_phase1", "Table 1. Phase 1 confabulation rates by model",
                ["Model", "Trials", "v1 paper (raw substring)", "v1 corrected method", "Adjudicated: result attributed",
                 "Adjudicated: lenient", "Invented tool failure", "Errored check reported as result", "Detector (strict)", "Harness artifact"], table,
                "Adjudicated = two blind raters agreed the report attributes a scan result to a package the tool never checked "
                "(docs/adjudication/CODEBOOK.md). Lenient adds packages for which the report claims a failed check or a disclosure "
                "but asserts a specific vulnerability anyway. Invented tool failure = the report says a check failed for a package the "
                "model never asked the tool about. Errored check reported as result = the tool only ever errored on the package and the "
                "report gives it a result anyway. Detector = the rebuilt automatic measure (scripts/rgp/measure.py). "
                "Mistral's 20 trials are API failures and are listed for completeness only.")
    # R1 primary and V3 primary
    r1p = [x for x in by_model["deepseek-r1"] if "noclutter" in x["trial_id"]]
    v3p = [x for x in by_model["deepseek-v3"] if "noclutter" in x["trial_id"]]
    mc = [x for x in by_model["mercury"] if x["trial_id"].startswith("C6_")]
    NUMBERS["phase1"]["r1_primary"] = summarise(r1p)
    NUMBERS["phase1"]["v3_primary"] = summarise(v3p)
    NUMBERS["phase1"]["mercury_easiest"] = summarise(mc)
    r1c = [x for x in by_model["deepseek-r1"] if "hard" in x["trial_id"]]
    NUMBERS["phase1"]["r1_clutter"] = summarise(r1c)
    NUMBERS["phase1"]["rows"] = rows
    return rows


# ----------------------------------------------------------------- Token cap
def token_cap():
    recs = [r for r in load_phase(1) + load_phase(2) + load_phase(4) if tool_condition(r)]
    out = {}
    for m in ("deepseek-r1", "deepseek-v3"):
        rs = [r for r in recs if r["_model"] == m]
        first = [(r["token_timeline"] or [{}])[0] for r in rs]
        calls = Counter(t.get("tool_calls_this_turn", 0) for t in first)
        big = [(r, t) for r, t in zip(rs, first) if t.get("tool_calls_this_turn", 0) >= 70]
        at_cap = sum(1 for _, t in big if t.get("turn_output_tokens") == 4096)
        cut = 0
        prefix = 0
        for r, t in big:
            for msg in r["transcript"]:
                if msg.get("role") == "assistant" and msg.get("tool_calls"):
                    args = (msg["tool_calls"][-1].get("function") or {}).get("arguments")
                    if isinstance(args, str):
                        try:
                            json.loads(args)
                        except json.JSONDecodeError:
                            cut += 1
                    break
            n = t["tool_calls_this_turn"]
            called = [c["request_args"]["package_name"].lower() for c in r["call_log"][:n]]
            if called == [d.lower() for d in r["dep_order"]][:len(called)]:
                prefix += 1
        out[m] = {"trials": len(rs), "first_turn_76_77": calls[76] + calls[77], "big_batches": len(big),
                  "big_at_exactly_4096": at_cap, "big_cut_off": cut, "big_prefix_of_prompt_order": prefix,
                  "first_turn_dist": dict(sorted(calls.items()))}
    NUMBERS["token_cap"] = out
    write_table("table_token_cap", "Table 7. The 4,096-token output cap in the first tool-call batch",
                ["Model", "Production trials", "First turn at 76 or 77 calls", "Batches of 70+ calls",
                 "Exactly 4,096 output tokens", "Last call cut off mid-JSON", "Calls = prompt-order prefix"],
                [[m, o["trials"], o["first_turn_76_77"], o["big_batches"], o["big_at_exactly_4096"], o["big_cut_off"],
                  o["big_prefix_of_prompt_order"]] for m, o in out.items()],
                "R1's reported output tokens include reasoning tokens, so its batches never read exactly 4,096. "
                "The 76/77 stopping point at V3's tokens-per-call rate is the evidence for R1.")


# ----------------------------------------------------------------- Phase 2
ARMS = ["baseline", "gate_only", "receipt_prompt", "receipt_gate"]


def phase2():
    recs = load_phase(2)
    rows = [dict(per_trial(r), arm=r["condition_key"]) for r in recs]
    NUMBERS["phase2"] = {"rows": rows}
    for model, tname, title in (("deepseek-r1", "table2_phase2_r1", "Table 2. Phase 2, DeepSeek R1 (N=50 per arm)"),
                                ("mercury", "table3_phase2_mercury", "Table 3. Phase 2, Mercury 2 (N=30 per arm)")):
        by_arm = {a: [x for x in rows if x["model"] == model and x["arm"] == a] for a in ARMS}
        table = []
        NUMBERS["phase2"][model] = {}
        for a in ARMS:
            s = summarise(by_arm[a])
            NUMBERS["phase2"][model][a] = s
            table.append([a, s["n"], s["old_corrected"], rate(s["adj_strict"], s["n"]), s["adj_lenient"], s["adj_invented_failure"],
                          s["error_reported_as_result"], s["adj_disclosed"], s["censored"], s["strict"],
                          f"{s['low_mode']} ({s['low_mode'] / s['n']:.0%})", f"{s['mean_coverage']:.1%}"])
        loose = by_arm["baseline"] + by_arm["gate_only"]
        rec = by_arm["receipt_prompt"] + by_arm["receipt_gate"]
        adj = lambda xs: sum(1 for x in xs if x["adj_strict"] is True)  # noqa: E731
        adjl = lambda xs: sum(1 for x in xs if x["adj_lenient"] is True)  # noqa: E731
        tests = {
            "adj_pooled_loose_vs_receipt": fisher(adj(loose), len(loose), adj(rec), len(rec)),
            "adj_pooled_loose_vs_receipt_lenient": fisher(adjl(loose), len(loose), adjl(rec), len(rec)),
            "adj_baseline_vs_receipt_prompt": fisher(adj(by_arm["baseline"]), 50 if model == "deepseek-r1" else 30, adj(by_arm["receipt_prompt"]), 50 if model == "deepseek-r1" else 30),
            "adj_aa_baseline_vs_gate_only": fisher(adj(by_arm["baseline"]), len(by_arm["baseline"]), adj(by_arm["gate_only"]), len(by_arm["gate_only"])),
            "adj_loose": (adj(loose), len(loose)), "adj_receipt": (adj(rec), len(rec)),
            "adj_loose_lenient": (adjl(loose), len(loose)), "adj_receipt_lenient": (adjl(rec), len(rec)),
            "adj_invented_loose": (sum(1 for x in loose if x["adj_invented_failure"]), len(loose)),
            "adj_invented_receipt": (sum(1 for x in rec if x["adj_invented_failure"]), len(rec)),
            "pooled_loose_vs_receipt_strict": fisher(sum(x["strict"] for x in loose), len(loose), sum(x["strict"] for x in rec), len(rec)),
            "pooled_loose_vs_receipt_lenient": fisher(sum(x["lenient"] for x in loose), len(loose), sum(x["lenient"] for x in rec), len(rec)),
            "pooled_loose_vs_receipt_old_corrected": fisher(sum(x["old_corrected"] for x in loose), len(loose), sum(x["old_corrected"] for x in rec), len(rec)),
            "baseline_vs_receipt_prompt_strict": fisher(sum(x["strict"] for x in by_arm["baseline"]), len(by_arm["baseline"]),
                                                        sum(x["strict"] for x in by_arm["receipt_prompt"]), len(by_arm["receipt_prompt"])),
            "aa_low_mode_baseline_vs_gate_only": fisher(sum(x["low_mode"] for x in by_arm["baseline"]), len(by_arm["baseline"]),
                                                        sum(x["low_mode"] for x in by_arm["gate_only"]), len(by_arm["gate_only"])),
            "aa_strict_baseline_vs_gate_only": fisher(sum(x["strict"] for x in by_arm["baseline"]), len(by_arm["baseline"]),
                                                      sum(x["strict"] for x in by_arm["gate_only"]), len(by_arm["gate_only"])),
            "low_mode_loose_vs_receipt": fisher(sum(x["low_mode"] for x in loose), len(loose), sum(x["low_mode"] for x in rec), len(rec)),
            "coverage_loose_vs_receipt_mw": mannwhitney([x["coverage"] for x in loose], [x["coverage"] for x in rec]),
            "loose_strict": (sum(x["strict"] for x in loose), len(loose)),
            "receipt_strict": (sum(x["strict"] for x in rec), len(rec)),
            "loose_lenient": (sum(x["lenient"] for x in loose), len(loose)),
            "receipt_lenient": (sum(x["lenient"] for x in rec), len(rec)),
            "loose_low_mode": (sum(x["low_mode"] for x in loose), len(loose)),
            "receipt_low_mode": (sum(x["low_mode"] for x in rec), len(rec)),
            "loose_invented_failure": (sum(bool(x["invented_failure"]) for x in loose), len(loose)),
            "receipt_invented_failure": (sum(bool(x["invented_failure"]) for x in rec), len(rec)),
        }
        NUMBERS["phase2"][model]["tests"] = tests
        notes = (f"Adjudicated, pooled loose arms vs pooled receipt arms: {tests['adj_loose'][0]}/{tests['adj_loose'][1]} vs "
                 f"{tests['adj_receipt'][0]}/{tests['adj_receipt'][1]}, Fisher p = {tests['adj_pooled_loose_vs_receipt']:.3f}. "
                 f"Lenient: {tests['adj_loose_lenient'][0]} vs {tests['adj_receipt_lenient'][0]}, p = {tests['adj_pooled_loose_vs_receipt_lenient']:.3f}. "
                 f"Invented tool failures, loose vs receipt: {tests['adj_invented_loose'][0]} vs {tests['adj_invented_receipt'][0]}. "
                 f"A/A check (baseline vs gate-only, identical treatment): low mode p = {tests['aa_low_mode_baseline_vs_gate_only']:.3f}, "
                 f"adjudicated confab p = {tests['adj_aa_baseline_vs_gate_only']:.3f}. "
                 f"Low mode, loose vs receipt: {tests['loose_low_mode'][0]}/{tests['loose_low_mode'][1]} vs "
                 f"{tests['receipt_low_mode'][0]}/{tests['receipt_low_mode'][1]}, p = {tests['low_mode_loose_vs_receipt']:.2e}. "
                 "Censored = the report was cut off by the output cap before every unchecked package was reached, so the strict count is a lower bound for that arm.")
        write_table(tname, title,
                    ["Arm", "N", "v1 corrected", "Adjudicated: result attributed", "Adjudicated: lenient", "Invented failure",
                     "Errored check reported as result", "Disclosed", "Censored", "Detector (strict)", "Low mode (<=30 calls)", "Mean coverage"], table, notes)
    # Phase 1 vs Phase 2 "instability"
    p1 = NUMBERS["phase1"]["r1_primary"]
    p2 = NUMBERS["phase2"]["deepseek-r1"]["baseline"]
    NUMBERS["phase2"]["instability"] = {
        "v1_paper": "15/25 vs 11/50, p=0.002 (raw substring vs corrected)",
        "old_corrected_p": fisher(p1["old_corrected"], p1["n"], p2["old_corrected"], p2["n"]),
        "strict_p": fisher(p1["strict"], p1["n"], p2["strict"], p2["n"]),
        "adj_p": fisher(p1["adj_strict"], p1["n"], p2["adj_strict"], p2["n"]),
        "p1_adj": (p1["adj_strict"], p1["n"]), "p2_adj": (p2["adj_strict"], p2["n"]),
        "p1_strict": (p1["strict"], p1["n"]), "p2_strict": (p2["strict"], p2["n"]),
        "p1_old_corrected": (p1["old_corrected"], p1["n"]), "p2_old_corrected": (p2["old_corrected"], p2["n"]),
    }
    return rows


# ----------------------------------------------------------------- Phase 3
def _rig_a_lookup():
    """Match each Phase 3 input index to its Rig A record by rebuilding the gated input."""
    from scripts.phase3 import build_gated_input_v1 as build_gated_input  # noqa: E402
    rig_a = [r for r in load_phase(2) if r["_model"] == "deepseek-r1" and r["condition_key"] == "baseline"]
    p3 = load_phase(3, corrected=True)
    by_idx = {}
    for t in p3:
        if t["condition_key"] != "gated":
            continue
        idx = t["trial_id"].split("_A")[1]
        cands = [r for r in rig_a if r["trial_id"] == t["rig_a_trial_id"]]
        best = None
        for r in cands:
            if build_gated_input(r, DEPS_100)[:3000] == t["report_content"]:
                best = r
                break
        if best is None and cands:
            # fall back to the old confab list
            for r in cands:
                if sorted(r["claimed_but_not_called"]) == sorted(t["rig_a_confab_packages"]):
                    best = r
                    break
        by_idx[idx] = best
    return p3, by_idx


def _rig_b_entries(text):
    obj, _ = jsonrecover.parse(text)
    entries = {}
    if isinstance(obj, dict):
        for e in obj.get("remediation_plan") or []:
            if isinstance(e, dict) and e.get("package"):
                entries[str(e["package"]).lower()] = e
    return entries


def phase3():
    p3, by_idx = _rig_a_lookup()
    dep_idx = DepIndex(DEPS_100)
    rows = []
    for t in p3:
        idx = t["trial_id"].split("_A")[1]
        src = by_idx.get(idx)
        if src is None:
            continue
        v = classify(src)
        adj = adjudicated_codes(src)
        if adj:
            genuine = {p for p, (c, _) in adj.items() if c == "R"}
            lenient = genuine | {p for p, (c, par) in adj.items() if c in ("F", "D") and par}
        else:
            genuine = set(v.attributed)
            lenient = genuine | set(v.parametric)
        entries = _rig_b_entries(t["rig_b_output"])
        low = t["rig_b_output"].lower()

        def asserted(pkgs):
            hit = set()
            for p in pkgs:
                e = entries.get(p)
                real_ids = [c for c in (e.get("cves") or []) if re.match(r"(?:CVE|GHSA|PYSEC)-", str(c), re.I)] if e else []
                if e and (str(e.get("priority", "")).upper() in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "SAFE") or real_ids):
                    hit.add(p)
                elif not entries and dep_idx.mentioned(t["rig_b_output"], p):
                    hit.add(p)
            return hit

        prop_s, prop_l = asserted(genuine), asserted(lenient)
        hedged = {p for p in prop_l if (entries.get(p) or {}).get("confidence", "").lower() == "low"
                  or any(w in str((entries.get(p) or {}).get("action", "")).lower() for w in ("unverified", "not verified", "verify", "could not", "not scanned"))}
        rows.append({
            "trial_id": t["trial_id"], "cond": t["condition_key"], "idx": idx, "rig_a": src["trial_id"] + "@" + src["_file"],
            "old_confab_input": t["is_confab_input_corrected"], "old_propagated": t["propagation_count"] > 0,
            "old_elaborated": t["elaboration_count"] > 0,
            "strict_input": bool(genuine), "lenient_input": bool(lenient),
            "strict_propagated": bool(prop_s), "lenient_propagated": bool(prop_l),
            "propagated_pkgs": sorted(prop_l), "hedged_pkgs": sorted(hedged),
            "rig_b_json": bool(entries), "rig_a_codes": v.summary()["codes"],
        })
    NUMBERS["phase3"] = {"rows": rows}
    table = []
    for which in ("old", "strict", "lenient"):
        key_in = {"old": "old_confab_input", "strict": "strict_input", "lenient": "lenient_input"}[which]
        key_p = {"old": "old_propagated", "strict": "strict_propagated", "lenient": "lenient_propagated"}[which]
        per_cond = {}
        for cond in ("ungated", "annotated", "gated"):
            rs = [x for x in rows if x["cond"] == cond and x[key_in]]
            per_cond[cond] = (sum(x[key_p] for x in rs), len(rs))
            table.append([which, cond, len(rs), rate(sum(x[key_p] for x in rs), len(rs))])
        # paired McNemar by input index
        def paired(c1, c2):
            b = c = 0
            for i in {x["idx"] for x in rows if x[key_in]}:
                a = next((x[key_p] for x in rows if x["idx"] == i and x["cond"] == c1), None)
                g = next((x[key_p] for x in rows if x["idx"] == i and x["cond"] == c2), None)
                if a is None or g is None:
                    continue
                b += a and not g
                c += g and not a
            return b, c, mcnemar_exact(b, c)
        NUMBERS["phase3"][which] = {
            "per_condition": per_cond,
            "ungated_vs_gated_mcnemar": paired("ungated", "gated"),
            "ungated_vs_annotated_mcnemar": paired("ungated", "annotated"),
            "ungated_vs_gated_fisher": fisher(*per_cond["ungated"], *per_cond["gated"]),
            "ungated_vs_annotated_fisher": fisher(*per_cond["ungated"], *per_cond["annotated"]),
        }
    write_table("table4_phase3", "Table 4. Phase 3 propagation under three definitions of a confabulated input",
                ["Input definition", "Condition", "Confab-input trials", "Propagated"], table,
                "old = v1 corrected list and mention-based propagation (any word-boundary mention by Rig B). "
                "strict = Rig A attributed a result to an unchecked package, and Rig B asserted a priority or CVE for that package. "
                "lenient adds the parametric-claim cases. The gated condition never shows Rig B the package names, so 0 is by construction. "
                "Paired exact McNemar tests are in numbers.json.")
    # gated-input defect
    from scripts.phase3 import build_gated_input_v1 as build_gated_input  # noqa: E402
    err_lines = inputs_hit = log4j = 0
    safe_calls = []
    for t in p3:
        if t["condition_key"] != "gated":
            continue
        src = by_idx.get(t["trial_id"].split("_A")[1])
        if src is None:
            continue
        rebuilt = build_gated_input(src, DEPS_100)
        errored = {c["request_args"]["package_name"].lower() for c in src["call_log"] if c["is_error"]}
        ok = {c["request_args"]["package_name"].lower() for c in src["call_log"] if not c["is_error"]}
        hit = False
        for line in rebuilt.splitlines():
            m = re.match(r"- (\S+) .*: No known vulnerabilities", line)
            if m and m.group(1).lower() in errored and m.group(1).lower() not in ok:
                err_lines += 1
                hit = True
                if m.group(1).lower() == "log4j-core":
                    log4j += 1
        inputs_hit += hit
        for p, e in _rig_b_entries(t["rig_b_output"]).items():
            if p in errored and p not in ok and str(e.get("priority", "")).upper() == "SAFE":
                safe_calls.append((t["trial_id"], p))
    NUMBERS["phase3"]["gated_input_defect"] = {"error_only_lines_rendered_clean": err_lines, "inputs_affected": inputs_hit,
                                               "log4j_core_rendered_clean": log4j, "rig_b_marked_error_only_safe": safe_calls}
    # annotated_A028 CVEs
    a028 = next((t for t in p3 if t["trial_id"] == "annotated_A028"), None)
    if a028:
        NUMBERS["phase3"]["annotated_A028_novel_cves"] = a028["novel_cves_by_rig_b"]
    NUMBERS["phase3"]["real_cves_echoed_always_zero"] = all(t["real_cves_echoed"] == 0 for t in p3)


# ----------------------------------------------------------------- Phase 4
def phase4():
    recs = load_phase(4)
    rows = [dict(per_trial(r), arm=r["condition_key"],
                 echo_rate=r["receipt_echo_rate"],
                 unverified_in_text='"unverified"' in r["final_text"]) for r in recs]
    p2rows = NUMBERS["phase2"]["rows"]
    NUMBERS["phase4"] = {"rows": rows}
    for model, tname, title in (("deepseek-r1", "table5_phase4_r1", "Table 5. Phase 4, DeepSeek R1"),
                                ("mercury", "table6_phase4_mercury", "Table 6. Phase 4, Mercury 2")):
        arms = {
            "baseline (Phase 2)": [x for x in p2rows if x["model"] == model and x["arm"] == "baseline"],
            "echo_only": [x for x in rows if x["model"] == model and x["arm"] == "echo_only"],
            "disclosure_only": [x for x in rows if x["model"] == model and x["arm"] == "disclosure_only"],
            "both (Phase 2 receipt prompt)": [x for x in p2rows if x["model"] == model and x["arm"] == "receipt_prompt"],
        }
        table = []
        NUMBERS["phase4"][model] = {}
        for a, rs in arms.items():
            s = summarise(rs)
            NUMBERS["phase4"][model][a] = s
            unv = sum(1 for x in rs if x.get("unverified_in_text")) if "unverified_in_text" in (rs[0] if rs else {}) else "n/a"
            table.append([a, s["n"], s["old_corrected"], rate(s["adj_strict"], s["n"]), s["adj_lenient"], s["adj_invented_failure"],
                          s["error_reported_as_result"], s["adj_disclosed"], s["censored"], s["strict"],
                          f"{s['low_mode']} ({s['low_mode'] / s['n']:.0%})", f"{s['mean_coverage']:.1%}"])
        b, e, d = arms["baseline (Phase 2)"], arms["echo_only"], arms["disclosure_only"]
        adj = lambda xs: sum(1 for x in xs if x["adj_strict"] is True)  # noqa: E731
        NUMBERS["phase4"][model]["tests"] = {
            "adj_baseline_vs_echo": fisher(adj(b), len(b), adj(e), len(e)),
            "adj_baseline_vs_disclosure": fisher(adj(b), len(b), adj(d), len(d)),
            "adj_echo_vs_disclosure": fisher(adj(e), len(e), adj(d), len(d)),
            "adj_counts": {"baseline": (adj(b), len(b)), "echo": (adj(e), len(e)), "disclosure": (adj(d), len(d))},
            "low_mode_baseline_vs_echo": fisher(sum(x["low_mode"] for x in b), len(b), sum(x["low_mode"] for x in e), len(e)),
            "low_mode_baseline_vs_disclosure": fisher(sum(x["low_mode"] for x in b), len(b), sum(x["low_mode"] for x in d), len(d)),
            "strict_baseline_vs_echo": fisher(sum(x["strict"] for x in b), len(b), sum(x["strict"] for x in e), len(e)),
            "strict_baseline_vs_disclosure": fisher(sum(x["strict"] for x in b), len(b), sum(x["strict"] for x in d), len(d)),
            "strict_echo_vs_disclosure": fisher(sum(x["strict"] for x in e), len(e), sum(x["strict"] for x in d), len(d)),
        }
        # disclosure-only: did R1 fill the unverified field?
        if model == "deepseek-r1":
            filled = [(x["trial_id"], x["adj_strict"], bool(x["adj_D"] or x["disclosed"]), x["json_parsed"]) for x in d]
            NUMBERS["phase4"][model]["disclosure_only_detail"] = filled
        write_table(tname, title,
                    ["Arm", "N", "v1 corrected", "Adjudicated: result attributed", "Adjudicated: lenient", "Invented failure",
                     "Errored check reported as result", "Disclosed", "Censored", "Detector (strict)", "Low mode (<=30 calls)", "Mean coverage"], table,
                    "Baseline and 'both' are the Phase 2 arms the v1 paper reused. Echo-only and disclosure-only ran about three hours later, so this is a historical comparison, not a concurrent one.")


# ----------------------------------------------------------------- Figures
def figures():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed; skipping figures")
        return
    FIGS.mkdir(parents=True, exist_ok=True)
    rows = NUMBERS["phase2"]["rows"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True)
    for ax, (arm, title) in zip(axes, (("baseline", "R1 baseline (loose prompt)"), ("receipt_prompt", "R1 receipt prompt"))):
        calls = [x["calls"] for x in rows if x["model"] == "deepseek-r1" and x["arm"] == arm]
        ax.hist(calls, bins=range(0, 105, 5), color="#4C72B0")
        ax.axvline(76, color="#C44E52", linestyle="--", label="76 calls = 4,096-token cap")
        ax.set_title(title)
        ax.set_xlabel("tool calls per trial")
        ax.legend(loc="upper left", fontsize=8)
    axes[0].set_ylabel("trials")
    fig.suptitle("Figure 1. R1 call counts: the high mode is the harness output cap")
    fig.tight_layout()
    fig.savefig(FIGS / "fig2_bimodal_corrected.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6))
    for ax, model, title in zip(axes, ("deepseek-r1", "mercury"), ("DeepSeek R1 (N=50/arm)", "Mercury 2 (N=30/arm)")):
        s = NUMBERS["phase2"][model]
        xs = range(len(ARMS))
        ax.bar([x - 0.2 for x in xs], [s[a]["old_corrected"] / s[a]["n"] for a in ARMS], width=0.4, label="v1 corrected method", color="#C44E52")
        ax.bar([x + 0.2 for x in xs], [s[a]["adj_strict"] / s[a]["n"] for a in ARMS], width=0.4, label="adjudicated (result attributed)", color="#4C72B0")
        ax.set_xticks(list(xs))
        ax.set_xticklabels(ARMS, rotation=20)
        ax.set_ylim(0, 1)
        ax.set_title(title)
        ax.legend(fontsize=8)
    axes[0].set_ylabel("confabulation trial rate")
    fig.suptitle("Figure 2. Phase 2 rates under the v1 measure and the adjudicated measure")
    fig.tight_layout()
    fig.savefig(FIGS / "fig4_factorial_corrected.png", dpi=150)
    plt.close(fig)

    p3 = NUMBERS["phase3"]
    fig, ax = plt.subplots(figsize=(6, 3.4))
    conds = ["ungated", "annotated", "gated"]
    for off, which, color in ((-0.2, "old", "#C44E52"), (0.2, "strict", "#4C72B0")):
        vals = [p3[which]["per_condition"][c] for c in conds]
        ax.bar([i + off for i in range(3)], [k / n if n else 0 for k, n in vals], width=0.4, color=color,
               label=f"{which} definition")
        for i, (k, n) in enumerate(vals):
            ax.text(i + off, (k / n if n else 0) + 0.02, f"{k}/{n}", ha="center", fontsize=8)
    ax.set_xticks(range(3))
    ax.set_xticklabels(conds)
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("propagation rate")
    ax.legend(fontsize=8)
    ax.set_title("Figure 3. Phase 3 propagation, v1 vs strict definition")
    fig.tight_layout()
    fig.savefig(FIGS / "fig3_propagation_corrected.png", dpi=150)
    plt.close(fig)


def content_check():
    """Do parsed report entries for packages the tool did check agree with the
    tool on whether the package has vulnerabilities? Placeholder arrays
    ("[...]", "[/* 47 vulnerabilities */]") and entries cut off by the output
    cap are not claims and are excluded."""
    from scripts.phase2 import _report_entries  # noqa: E402
    tot = Counter()
    for phase in (1, 2, 4):
        for r in load_phase(phase):
            if phase == 1 and not tool_condition(r):
                continue
            deps = deps_for_record(r)
            idx = DepIndex(deps)
            ok = {idx.canonical(c["request_args"]["package_name"]): (c.get("result_summary") or {}).get("vulnerability_count")
                  for c in r["call_log"] if not c["is_error"] and idx.canonical(c["request_args"]["package_name"])}
            for p, e in _report_entries(r["final_text"], idx).items():
                v = e.get("vulnerabilities")
                if p in ok and ok[p] is not None and isinstance(v, list) and not jsonrecover.is_placeholder(v):
                    tot["entries"] += 1
                    if (len(v) > 0) != (ok[p] > 0):
                        tot["mismatch"] += 1
                        tot["reported_clean_but_vulnerable" if ok[p] > 0 else "reported_vulnerable_but_clean"] += 1
    NUMBERS["content_check"] = dict(tot)


def main():
    OUT.mkdir(exist_ok=True)
    phase1()
    token_cap()
    phase2()
    phase3()
    phase4()
    content_check()
    figures()
    slim = json.loads(json.dumps(NUMBERS, default=str))
    for k in ("phase1", "phase2", "phase3", "phase4"):
        slim[k].pop("rows", None)
    (OUT / "numbers.json").write_text(json.dumps(slim, indent=1, default=str))
    (OUT / "per_trial.json").write_text(json.dumps(
        {k: NUMBERS[k]["rows"] for k in ("phase1", "phase2", "phase3", "phase4")}, indent=1, default=str))
    print("wrote", OUT / "numbers.json", "and", len(list(TABLES.glob("*.md"))), "tables")


if __name__ == "__main__":
    main()
