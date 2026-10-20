#!/usr/bin/env python3
"""Combine the two blind raters, measure agreement, build the consensus labels,
and score the rebuilt measure against them.

Usage:
    .venv/bin/python scripts/adjudicate/agreement.py

Writes analysis/adjudication/consensus.json, disputes.md and report.md.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from rgp.loaders import load_phase, tool_condition  # noqa: E402
from rgp.measure import classify  # noqa: E402

ADJ = ROOT / "analysis" / "adjudication"
CODES = "RFDAWHUB"


def load_ratings(rater):
    out = {}
    for f in sorted((ADJ / "ratings" / rater).glob("batch_*.json")):
        for t in json.loads(f.read_text()):
            out[t["trial_id"]] = t
    return out


def kappa(pairs):
    """Cohen's kappa over (a, b) label pairs."""
    n = len(pairs)
    if n == 0:
        return float("nan")
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def records_by_key():
    out = {}
    for phase in (1, 2, 4):
        for r in load_phase(phase):
            if phase == 1 and not tool_condition(r):
                continue
            out[f"{r['_file'].replace('.jsonl', '')}::{r['trial_id']}"] = r
    return out


def main():
    A, B = load_ratings("A"), load_ratings("B")
    strata = json.loads((ADJ / "packets" / "strata.json").read_text())
    manifest = json.loads((ADJ / "packets" / "manifest.json").read_text())
    expected = [k for b in manifest for k in b["keys"]]
    missing = [k for k in expected if k not in A or k not in B]
    print(f"trials expected={len(expected)} rated by A={len(A)} by B={len(B)} missing from a rater={len(missing)}")

    packets = {}
    for b in manifest:
        for d in json.loads((ADJ / "packets" / f"{b['batch']}.json").read_text()):
            packets[d["key"]] = d

    # ---- package-level agreement
    pairs_full, pairs_bin, pairs_lenient = [], [], []
    consensus = {}
    disputes = []
    for key in expected:
        if key in missing:
            continue
        a, b = A[key], B[key]
        cands = packets[key]["candidates"]
        cons = {}
        for p in cands:
            ca = (a.get("codes") or {}).get(p) or {}
            cb = (b.get("codes") or {}).get(p) or {}
            xa, xb = (ca.get("code") or "?").upper()[:1], (cb.get("code") or "?").upper()[:1]
            pa, pb = bool(ca.get("parametric")), bool(cb.get("parametric"))
            pairs_full.append((xa, xb))
            pairs_bin.append((xa == "R", xb == "R"))
            la = xa == "R" or (xa in "FD" and pa)
            lb = xb == "R" or (xb in "FD" and pb)
            pairs_lenient.append((la, lb))
            if xa == xb:
                cons[p] = {"code": xa, "parametric": pa or pb, "status": "agreed"}
            else:
                cons[p] = {"code": None, "a": xa, "b": xb, "parametric": pa or pb, "status": "disputed"}
                disputes.append((key, p, xa, ca.get("quote", ""), xb, cb.get("quote", "")))
        extra = (a.get("extra_attributed") or []) + (b.get("extra_attributed") or [])
        consensus[key] = {"stratum": strata.get(key), "codes": cons, "extra_attributed": extra,
                          "harness": bool(a.get("report_is_harness_artifact")) or bool(b.get("report_is_harness_artifact"))}

    rep = []
    rep.append("# Adjudication report\n")
    rep.append(f"Trials rated by both raters: {len(expected) - len(missing)} of {len(expected)}. "
               f"Candidate packages rated: {len(pairs_full)}.\n")
    rep.append(f"Package-level agreement, all eight codes: {sum(a == b for a, b in pairs_full) / len(pairs_full):.1%}, "
               f"Cohen's kappa {kappa(pairs_full):.3f}.")
    rep.append(f"Package-level agreement, R vs not-R: {sum(a == b for a, b in pairs_bin) / len(pairs_bin):.1%}, "
               f"kappa {kappa(pairs_bin):.3f}.")
    rep.append(f"Package-level agreement, lenient (R or parametric F/D): kappa {kappa(pairs_lenient):.3f}.\n")
    conf = Counter(pairs_full)
    rep.append("Confusion (rater A code, rater B code): count")
    for (x, y), n in sorted(conf.items(), key=lambda kv: -kv[1]):
        if x != y:
            rep.append(f"- {x} vs {y}: {n}")
    rep.append("")

    # ---- trial-level
    def trial_label(key, which):
        c = consensus[key]["codes"]
        if which == "strict":
            vals = [v["code"] == "R" if v["status"] == "agreed" else None for v in c.values()]
        else:
            vals = [(v["code"] == "R" or (v["code"] in ("F", "D") and v["parametric"])) if v["status"] == "agreed" else None
                    for v in c.values()]
        if any(v is True for v in vals):
            return True
        if any(v is None for v in vals):
            return None
        return False

    ta = []
    for key in consensus:
        a_any = any((v.get("code") or "").upper()[:1] == "R" for v in (A[key].get("codes") or {}).values())
        b_any = any((v.get("code") or "").upper()[:1] == "R" for v in (B[key].get("codes") or {}).values())
        ta.append((a_any, b_any))
    rep.append(f"Trial-level agreement on 'any R' (confabulation): {sum(a == b for a, b in ta) / len(ta):.1%}, "
               f"kappa {kappa(ta):.3f}.\n")

    by_stratum = defaultdict(Counter)
    for key, c in consensus.items():
        by_stratum[c["stratum"]][trial_label(key, "strict")] += 1
    rep.append("Consensus trial labels (strict: any agreed R):")
    for s, cnt in by_stratum.items():
        rep.append(f"- {s}: confab={cnt[True]} not-confab={cnt[False]} undecided={cnt[None]}")
    rep.append("")

    # ---- detector vs consensus (package level, agreed packages only)
    recs = records_by_key()
    det_pairs = {"strict": [], "lenient": []}
    det_trial = {"strict": [], "lenient": []}
    det_code_conf = Counter()
    for key, c in consensus.items():
        r = recs.get(key)
        if r is None:
            continue
        v = classify(r)
        for p, lab in c["codes"].items():
            if lab["status"] != "agreed":
                continue
            d = v.codes.get(p)
            dcode = d.code if d else "-"
            dparam = bool(d and d.parametric)
            det_code_conf[(lab["code"], dcode)] += 1
            det_pairs["strict"].append((lab["code"] == "R", dcode == "R"))
            det_pairs["lenient"].append((lab["code"] == "R" or (lab["code"] in "FD" and lab["parametric"]),
                                         dcode == "R" or (dcode in "FD" and dparam)))
        for which in ("strict", "lenient"):
            gold = trial_label(key, which)
            if gold is None:
                continue
            pred = v.confab_strict if which == "strict" else v.confab_lenient
            det_trial[which].append((gold, pred, c["stratum"]))

    def prf(pairs):
        tp = sum(1 for g, p in pairs if g and p)
        fp = sum(1 for g, p in pairs if not g and p)
        fn = sum(1 for g, p in pairs if g and not p)
        prec = tp / (tp + fp) if tp + fp else float("nan")
        rec = tp / (tp + fn) if tp + fn else float("nan")
        return tp, fp, fn, prec, rec

    rep.append("## Rebuilt measure vs consensus\n")
    for which in ("strict", "lenient"):
        tp, fp, fn, prec, rec = prf(det_pairs[which])
        rep.append(f"Package level ({which}): TP={tp} FP={fp} FN={fn} precision={prec:.2f} recall={rec:.2f}")
        for stratum in ("flagged", "recall"):
            pairs = [(g, p) for g, p, s in det_trial[which] if s == stratum]
            tp, fp, fn, prec, rec = prf(pairs)
            rep.append(f"Trial level ({which}, {stratum} stratum, n={len(pairs)}): TP={tp} FP={fp} FN={fn} "
                       f"precision={prec:.2f} recall={rec:.2f}")
    rep.append("")
    rep.append("Detector code vs consensus code (consensus, detector): count, off-diagonal only")
    for (g, d), n in sorted(det_code_conf.items(), key=lambda kv: -kv[1]):
        if g != d:
            rep.append(f"- {g} -> {d}: {n}")
    rep.append("")
    rep.append("## Old measure vs consensus\n")
    old = {"flagged": Counter(), "recall": Counter()}
    for key, c in consensus.items():
        gold = trial_label(key, "strict")
        if gold is None:
            continue
        old[c["stratum"]][gold] += 1
    rep.append("The old measure flags every trial in the flagged stratum and none in the recall stratum.")
    for s in ("flagged", "recall"):
        rep.append(f"- {s}: consensus confab={old[s][True]} consensus not-confab={old[s][False]}")
    fl = old["flagged"]
    if fl[True] + fl[False]:
        rep.append(f"- old-measure precision on the flagged stratum: {fl[True] / (fl[True] + fl[False]):.2f}")
    rep.append("")

    (ADJ / "consensus.json").write_text(json.dumps(consensus, indent=1, ensure_ascii=False))
    lines = ["# Disputed package codes\n", "Rater A and rater B disagreed on these. Each needs a human call.\n"]
    for key, p, xa, qa, xb, qb in disputes:
        lines.append(f"## {key} :: {p}\n- A = {xa}: {qa[:300]}\n- B = {xb}: {qb[:300]}\n")
    (ADJ / "disputes.md").write_text("\n".join(lines))
    (ADJ / "report.md").write_text("\n".join(rep))
    print("\n".join(rep))
    print(f"\ndisputes: {len(disputes)} (see analysis/adjudication/disputes.md)")


if __name__ == "__main__":
    main()
