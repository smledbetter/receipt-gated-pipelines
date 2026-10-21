#!/usr/bin/env python3
"""Build blind adjudication packets.

A packet holds, for each trial, the report text, the packages the tool really
checked, and the candidate packages (named in the report, never checked). It
holds no verdict from any detector and no reference to the audit.

Usage:
    .venv/bin/python scripts/adjudicate/build_packets.py --stats
    .venv/bin/python scripts/adjudicate/build_packets.py --out analysis/adjudication/packets --batch-size 12 --seed 7
"""
import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from rgp.loaders import load_phase, deps_for, tool_condition, prompt_kind  # noqa: E402
from rgp.names import DepIndex, called_packages, attempted_packages, tool_summaries  # noqa: E402
from reanalyze_phase2 import recompute_confab  # noqa: E402


def trials():
    out = []
    for phase in (1, 2, 4):
        for r in load_phase(phase):
            if phase == 1 and not tool_condition(r):
                continue
            out.append(r)
    return out


def describe(r):
    deps = deps_for(r)
    idx = DepIndex(deps)
    called = called_packages(r) & set(idx.names)
    attempted = attempted_packages(r, idx) - called
    mentions = idx.mentions(r["final_text"])
    candidates = sorted(n for n in mentions if n not in called)
    corrected = recompute_confab(r)[0]
    return {
        "trial_id": r["trial_id"],
        "file": r["_file"],
        "phase": r["_phase"],
        "model": r["_model"],
        "prompt": prompt_kind(r),
        "n_called": len(called),
        "called": sorted(called),
        "attempted_not_logged": sorted(attempted),
        "candidates": candidates,
        "corrected_flag": corrected > 0,
        "report_len": len(r["final_text"]),
        "final_text": r["final_text"],
        "summaries": tool_summaries(r),
    }


def packet_md(items):
    lines = ["# Adjudication packet", "",
             "Read docs/adjudication/CODEBOOK.md first. Rate every candidate package of every trial.", ""]
    for d in items:
        lines += [f"## TRIAL {d['key']}", "",
                  f"Phase {d['phase']}, model {d['model']}, prompt style: {d['prompt']}.",
                  f"Packages the tool really checked ({d['n_called']}): " + (", ".join(d["called"]) or "(none)"),
                  ]
        if d["attempted_not_logged"]:
            lines.append("Packages the model asked the tool for, but the request failed before the tool ran: "
                         + ", ".join(d["attempted_not_logged"]))
        lines.append("Candidate packages (named in the report, never checked): " + ", ".join(d["candidates"]))
        adv = []
        for pkg, texts in d["summaries"].items():
            for t in texts:
                if any(c in t.lower() for c in d["candidates"]):
                    adv.append(f"  - for {pkg}: \"{t}\"")
        if adv:
            lines.append("Advisory text the tool returned for checked packages, which the report may have copied:")
            lines += adv
        lines += ["", "--- REPORT START ---", d["final_text"], "--- REPORT END ---", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--out", default="analysis/adjudication/packets")
    ap.add_argument("--batch-size", type=int, default=12)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--recall-sample", type=int, default=40,
                    help="unflagged trials with candidates to include, sampled at random")
    ap.add_argument("--supplement", default="",
                    help="name of a supplementary packet holding only candidates missing from the existing packets")
    ap.add_argument("--recall-rest", default="",
                    help="name of a packet holding every unflagged trial with candidates that no packet has yet")
    args = ap.parse_args()

    described = [describe(r) for r in trials()]
    for d in described:
        d["key"] = f"{d['file'].replace('.jsonl', '')}::{d['trial_id']}"

    if args.recall_rest:
        out = ROOT / args.out
        have = set()
        for f in sorted(out.glob("*.json")):
            if f.name in ("manifest.json", "strata.json"):
                continue
            for d in json.loads(f.read_text()):
                have.add(d["key"])
        rest = [d for d in described if not d["corrected_flag"] and d["candidates"] and d["key"] not in have]
        (out / f"{args.recall_rest}.md").write_text(packet_md(rest))
        (out / f"{args.recall_rest}.json").write_text(json.dumps(
            [{k: v for k, v in d.items() if k not in ("final_text", "summaries")} for d in rest], indent=1))
        manifest = json.loads((out / "manifest.json").read_text())
        manifest = [m for m in manifest if m["batch"] != args.recall_rest]
        manifest.append({"batch": args.recall_rest, "n": len(rest), "keys": [d["key"] for d in rest]})
        (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
        strata = json.loads((out / "strata.json").read_text())
        for d in rest:
            strata[d["key"]] = "recall"
        (out / "strata.json").write_text(json.dumps(strata, indent=1))
        print(f"wrote {args.recall_rest}: {len(rest)} trials, {sum(len(d['candidates']) for d in rest)} candidates")
        return

    if args.supplement:
        out = ROOT / args.out
        existing = {}
        for f in sorted(out.glob("batch_*.json")):
            for d in json.loads(f.read_text()):
                existing[d["key"]] = set(d["candidates"])
        supp = []
        for d in described:
            if d["key"] not in existing:
                continue
            extra = sorted(set(d["candidates"]) - existing[d["key"]])
            if extra:
                s = dict(d, candidates=extra)
                supp.append(s)
        (out / f"{args.supplement}.md").write_text(packet_md(supp))
        (out / f"{args.supplement}.json").write_text(json.dumps(
            [{k: v for k, v in d.items() if k not in ("final_text", "summaries")} for d in supp], indent=1))
        manifest = json.loads((out / "manifest.json").read_text())
        manifest = [m for m in manifest if m["batch"] != args.supplement]
        manifest.append({"batch": args.supplement, "n": len(supp), "keys": [d["key"] for d in supp], "supplement": True})
        (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
        print(f"wrote {args.supplement}: {len(supp)} trials, {sum(len(d['candidates']) for d in supp)} extra candidates")
        return

    flagged = [d for d in described if d["corrected_flag"]]
    unflagged_with = [d for d in described if not d["corrected_flag"] and d["candidates"]]
    unflagged_none = [d for d in described if not d["corrected_flag"] and not d["candidates"]]

    if args.stats:
        print(f"trials={len(described)} flagged={len(flagged)} unflagged-with-candidates={len(unflagged_with)} "
              f"unflagged-no-candidates={len(unflagged_none)}")
        print("flagged by (phase, model):", Counter((d["phase"], d["model"]) for d in flagged))
        print("unflagged-with-candidates by (phase, model):", Counter((d["phase"], d["model"]) for d in unflagged_with))
        lens = sorted(d["report_len"] for d in flagged)
        print(f"flagged report length: median={lens[len(lens)//2]} max={lens[-1]} "
              f"total={sum(lens)} chars")
        print("candidates per flagged trial:", Counter(min(len(d["candidates"]), 25) for d in flagged))
        return

    rng = random.Random(args.seed)
    recall = rng.sample(unflagged_with, min(args.recall_sample, len(unflagged_with)))
    selected = flagged + recall
    rng.shuffle(selected)

    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for i in range(0, len(selected), args.batch_size):
        batch = selected[i:i + args.batch_size]
        bid = f"batch_{i // args.batch_size + 1:02d}"
        (out / f"{bid}.md").write_text(packet_md(batch))
        (out / f"{bid}.json").write_text(json.dumps(
            [{k: v for k, v in d.items() if k not in ("final_text", "summaries")} for d in batch], indent=1))
        manifest.append({"batch": bid, "n": len(batch), "keys": [d["key"] for d in batch]})
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    strata = {d["key"]: ("flagged" if d["corrected_flag"] else "recall") for d in selected}
    (out / "strata.json").write_text(json.dumps(strata, indent=1))
    print(f"wrote {len(manifest)} batches, {len(selected)} trials "
          f"({len(flagged)} flagged, {len(recall)} recall sample) to {out}")


if __name__ == "__main__":
    main()
