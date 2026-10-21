#!/usr/bin/env python3
"""List where the rebuilt measure disagrees with the consensus labels.

    .venv/bin/python scripts/adjudicate/errors.py --split dev   # odd batches
    .venv/bin/python scripts/adjudicate/errors.py --split test  # even batches
    .venv/bin/python scripts/adjudicate/errors.py --split all

The detector is tuned on the dev split only. The test split is reported once.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from rgp.measure import classify  # noqa: E402
from agreement import records_by_key  # noqa: E402

ADJ = ROOT / "analysis" / "adjudication"


def split_of(key, manifest):
    for b in manifest:
        if key in b["keys"]:
            return "dev" if int(b["batch"].split("_")[1]) % 2 == 1 else "test"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev", choices=["dev", "test", "all"])
    ap.add_argument("--only", default="", help="filter to a consensus->detector pair like D->R")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    cons = json.loads((ADJ / "consensus.json").read_text())
    manifest = json.loads((ADJ / "packets" / "manifest.json").read_text())
    A = {}
    for f in sorted((ADJ / "ratings" / "A").glob("batch_*.json")):
        for t in json.loads(f.read_text()):
            A[t["trial_id"]] = t
    recs = records_by_key()
    conf = Counter()
    trial_conf = Counter()
    for key, c in cons.items():
        sp = split_of(key, manifest)
        if args.split != "all" and sp != args.split:
            continue
        r = recs[key]
        v = classify(r)
        gold_any = any(x["status"] == "agreed" and x["code"] == "R" for x in c["codes"].values())
        trial_conf[(gold_any, v.confab_strict)] += 1
        for p, lab in c["codes"].items():
            if lab["status"] != "agreed":
                continue
            d = v.codes.get(p)
            dcode = d.code if d else "-"
            conf[(lab["code"], dcode)] += 1
            if lab["code"] != dcode and (not args.only or f"{lab['code']}->{dcode}" == args.only) and not args.quiet:
                q = (A[key].get("codes") or {}).get(p, {}).get("quote", "")
                print(f"[{sp}] {key} :: {p}  consensus={lab['code']} detector={dcode} ({d.source if d else ''})")
                print(f"    detector evidence: {(d.evidence if d else '')[:160]}")
                print(f"    rater quote:       {q[:160]}")
    print("\nconfusion (consensus, detector):", {f"{a}->{b}": n for (a, b), n in sorted(conf.items(), key=lambda kv: -kv[1])})
    print("trial level (gold_any_R, detector_strict):", dict(trial_conf))


if __name__ == "__main__":
    main()
