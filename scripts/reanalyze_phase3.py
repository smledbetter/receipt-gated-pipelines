"""
Re-analyze Phase 3 with corrected Rig A confabulation classifications.

Bug 1 from Phase 2 (substring matching) caused 3 Rig A trials to be falsely
classified as confab-input (they had only ini/ms as confab packages).

After correction:
  - baseline_T001 (early): ['ini','ms'] → [] (clean)
  - baseline_T008 (early): ['ms'] → [] (clean)
  - baseline_T019 (early): ['ini'] → [] (clean)

Other trials have ini/ms removed but retain real confab packages.
"""
import json, re
from pathlib import Path
from collections import defaultdict
from scipy.stats import fisher_exact, mannwhitneyu, binomtest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RESULTS_DIR = DATA_DIR  # v1 pointed at a results/ directory that does not exist
OUT_DIR = Path(__file__).resolve().parent.parent / "analysis" / "reanalysis"

# --- Load corrected Phase 2 Rig A data ---

def load_corrected_rig_a():
    """Build lookup: (trial_id, old_confab_pkgs_tuple) → corrected_confab_pkgs."""
    lookup = {}  # (trial_id, frozenset(old_pkgs)) → corrected_pkgs

    for fname in ("phase2_20260314_061615_corrected.jsonl",
                  "phase2_deepseek-r1_20260314_080559_corrected.jsonl"):
        for line in (RESULTS_DIR / "phase2" / fname).read_text().strip().split("\n"):
            rec = json.loads(line)
            if rec["condition_key"] != "baseline":
                continue
            tid = rec["trial_id"]
            old_pkgs = frozenset(rec["claimed_but_not_called"])
            corr_pkgs = rec["confab_corrected_packages"]
            lookup[(tid, old_pkgs)] = corr_pkgs

    return lookup


def match_source(trial, lookup):
    """Match a Phase 3 trial to its corrected Rig A confab packages."""
    rid = trial["rig_a_trial_id"]
    old_pkgs = frozenset(trial["rig_a_confab_packages"])

    if old_pkgs in (frozenset(), ):
        # Clean input — stays clean
        return [], False

    corr = lookup.get((rid, old_pkgs))
    if corr is not None:
        return corr, True

    # Fallback: return original (shouldn't happen)
    return list(old_pkgs), True


def main():
    lookup = load_corrected_rig_a()

    # Load Phase 3 data
    p3_file = RESULTS_DIR / "phase3" / "phase3_gemini-flash_20260314_103603.jsonl"
    trials = [json.loads(l) for l in p3_file.read_text().strip().split("\n")]

    # --- Step 1: Reclassify and add corrected fields ---
    for t in trials:
        corr_pkgs, was_confab_old = match_source(t, lookup)
        t["rig_a_confab_corrected_count"] = len(corr_pkgs)
        t["rig_a_confab_corrected_packages"] = corr_pkgs
        t["is_confab_input_corrected"] = len(corr_pkgs) > 0

    # --- Step 2: Write corrected file ---
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUT_DIR / "phase3_gemini-flash_20260314_103603_corrected.jsonl"
    with open(out_file, "w") as f:
        for t in trials:
            f.write(json.dumps(t) + "\n")
    print(f"Wrote {out_file.name} ({len(trials)} records)")

    # --- Step 3: Compute Table 4 (old and new) ---
    conditions = ["ungated", "annotated", "gated"]

    def compute_table(trials, confab_key):
        """Compute Table 4 metrics using given confab classification key."""
        rows = {}
        for cond in conditions:
            cond_trials = [t for t in trials if t["condition_key"] == cond]

            if confab_key == "old":
                confab_trials = [t for t in cond_trials if t["rig_a_confab_count"] > 0]
                clean_trials = [t for t in cond_trials if t["rig_a_confab_count"] == 0]
            else:
                confab_trials = [t for t in cond_trials if t["is_confab_input_corrected"]]
                clean_trials = [t for t in cond_trials if not t["is_confab_input_corrected"]]

            n_confab = len(confab_trials)
            n_clean = len(clean_trials)

            prop_count = sum(1 for t in confab_trials if t["propagation_count"] > 0)
            elab_count = sum(1 for t in confab_trials if t["elaboration_count"] > 0)
            fp_count = sum(1 for t in clean_trials if t["propagation_count"] > 0)

            # Propagation package counts for Mann-Whitney
            prop_pkg_counts = [t["propagation_count"] for t in confab_trials]

            rows[cond] = {
                "n_confab": n_confab,
                "n_clean": n_clean,
                "prop_trials": prop_count,
                "prop_rate": prop_count / max(n_confab, 1),
                "elab_trials": elab_count,
                "elab_rate": elab_count / max(n_confab, 1),
                "fp_count": fp_count,
                "fp_rate": fp_count / max(n_clean, 1),
                "prop_pkg_counts": prop_pkg_counts,
            }
        return rows

    old_table = compute_table(trials, "old")
    new_table = compute_table(trials, "new")

    # --- Step 4: Print comparison ---
    print("\n" + "=" * 90)
    print("TABLE 4 COMPARISON: OLD vs CORRECTED")
    print("=" * 90)

    header = f"{'Condition':<12} {'N_conf':>6} {'Prop':>12} {'Elab':>12} {'N_clean':>7} {'FP':>8}"
    print(f"\n  OLD (pre-correction):")
    print(f"  {header}")
    print("  " + "-" * 62)
    for cond in conditions:
        r = old_table[cond]
        print(f"  {cond:<12} {r['n_confab']:>6} {r['prop_trials']:>5}/{r['n_confab']:<3} "
              f"({r['prop_rate']:.0%})  {r['elab_trials']:>5}/{r['n_confab']:<3} "
              f"({r['elab_rate']:.0%})  {r['n_clean']:>5}  {r['fp_count']:>3}/{r['n_clean']}")

    print(f"\n  CORRECTED:")
    print(f"  {header}")
    print("  " + "-" * 62)
    for cond in conditions:
        r = new_table[cond]
        print(f"  {cond:<12} {r['n_confab']:>6} {r['prop_trials']:>5}/{r['n_confab']:<3} "
              f"({r['prop_rate']:.0%})  {r['elab_trials']:>5}/{r['n_confab']:<3} "
              f"({r['elab_rate']:.0%})  {r['n_clean']:>5}  {r['fp_count']:>3}/{r['n_clean']}")

    # --- Step 5: Fisher exact tests ---
    print("\n" + "=" * 90)
    print("STATISTICAL TESTS (corrected)")
    print("=" * 90)

    # Ungated vs gated propagation
    u = new_table["ungated"]
    g = new_table["gated"]
    a = new_table["annotated"]

    # Fisher: ungated vs gated
    table_ug = [[u["prop_trials"], u["n_confab"] - u["prop_trials"]],
                [g["prop_trials"], g["n_confab"] - g["prop_trials"]]]
    or_ug, p_ug = fisher_exact(table_ug)
    print(f"\n  Fisher exact: ungated vs gated propagation")
    print(f"    Ungated: {u['prop_trials']}/{u['n_confab']}, Gated: {g['prop_trials']}/{g['n_confab']}")
    print(f"    OR = {or_ug:.3f}, p = {p_ug:.4f}")

    # Fisher: ungated vs annotated
    table_ua = [[u["prop_trials"], u["n_confab"] - u["prop_trials"]],
                [a["prop_trials"], a["n_confab"] - a["prop_trials"]]]
    or_ua, p_ua = fisher_exact(table_ua)
    print(f"\n  Fisher exact: ungated vs annotated propagation")
    print(f"    Ungated: {u['prop_trials']}/{u['n_confab']}, Annotated: {a['prop_trials']}/{a['n_confab']}")
    print(f"    OR = {or_ua:.3f}, p = {p_ua:.4f}")

    # Paired: the same 11 inputs feed every condition, so an exact McNemar test
    # on discordant pairs is the right test; Fisher treats them as independent.
    def mcnemar(c1, c2):
        b = c = 0
        by_idx = {}
        for t in trials:
            if t["is_confab_input_corrected"]:
                by_idx.setdefault(t["trial_id"].split("_A")[1], {})[t["condition_key"]] = t["propagation_count"] > 0
        for idx, d in by_idx.items():
            if c1 in d and c2 in d:
                b += d[c1] and not d[c2]
                c += d[c2] and not d[c1]
        return b, c, (binomtest(min(b, c), b + c, 0.5).pvalue if b + c else 1.0)
    for c1, c2 in (("ungated", "gated"), ("ungated", "annotated")):
        b, c, p = mcnemar(c1, c2)
        print(f"\n  Exact McNemar: {c1} vs {c2} propagation: discordant {b}/{c}, p = {p:.4f}")

    # Mann-Whitney: ungated vs annotated propagation counts (two-sided)
    u_counts = u["prop_pkg_counts"]
    a_counts = a["prop_pkg_counts"]
    try:
        stat, p_mw = mannwhitneyu(u_counts, a_counts, alternative="two-sided")
        print(f"\n  Mann-Whitney U: ungated vs annotated propagation counts (two-sided)")
        print(f"    Ungated counts: {sorted(u_counts, reverse=True)}")
        print(f"    Annotated counts: {sorted(a_counts, reverse=True)}")
        print(f"    U = {stat:.1f}, p = {p_mw:.4f}")
    except ValueError as e:
        print(f"\n  Mann-Whitney U: {e}")

    # --- Step 6: Check reclassified trials ---
    print("\n" + "=" * 90)
    print("RECLASSIFIED TRIALS (confab → clean)")
    print("=" * 90)

    reclassified_ids = {"baseline_T001", "baseline_T008", "baseline_T019"}
    for t in trials:
        rid = t["rig_a_trial_id"]
        old_confab = t["rig_a_confab_count"] > 0
        new_confab = t["is_confab_input_corrected"]
        if rid in reclassified_ids and old_confab and not new_confab:
            had_prop = t["propagation_count"] > 0
            flag = " *** FALSE POSITIVE ***" if had_prop else ""
            print(f"  {t['trial_id']} ({t['condition_key']}): "
                  f"old_confab={t['rig_a_confab_packages']} → clean, "
                  f"prop={t['propagation_count']}, elab={t['elaboration_count']}{flag}")

    print("\n" + "=" * 90)


if __name__ == "__main__":
    main()
