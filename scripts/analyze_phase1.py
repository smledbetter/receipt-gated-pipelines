"""
Analyze Phase 1 results.
Usage: python scripts/analyze_phase1.py results/phase1_*.jsonl
"""
import json, sys
from collections import defaultdict
from pathlib import Path

def main():
    if len(sys.argv) < 2:
        # Find most recent results file
        results_dir = Path(__file__).resolve().parent.parent / "results"
        files = sorted(results_dir.glob("phase1_*.jsonl"))
        if not files:
            print("No results found.")
            return
        path = files[-1]
    else:
        path = Path(sys.argv[1])

    results = [json.loads(line) for line in path.read_text().strip().split("\n") if line.strip()]
    print(f"Loaded {len(results)} results from {path.name}\n")

    # Group by condition
    by_cond = defaultdict(list)
    for r in results:
        c = r["condition"]
        key = f"L{c['list_size']}_P{c['prompt_tier']}_{'clutter' if c['cluttered'] else 'clean'}_E{c['error_rate']}"
        by_cond[key].append(r)

    print(f"{'Condition':<45} {'N':>4} {'ToolCalls':>10} {'Coverage':>9} {'Skips':>6} {'SkipRate':>9}")
    print("-" * 90)

    total_skips = 0
    total_trials = 0

    for key in sorted(by_cond.keys()):
        trials = by_cond[key]
        n = len(trials)
        total_trials += n

        avg_calls = sum(r["tool_calls_made"] for r in trials) / n
        avg_coverage = sum(r["coverage_rate"] for r in trials) / n
        skip_trials = sum(1 for r in trials if r["claimed_but_not_called_count"] > 0)
        total_skips += skip_trials
        total_claimed_skips = sum(r["claimed_but_not_called_count"] for r in trials)
        skip_rate = total_claimed_skips / sum(r["claimed_checked_count"] for r in trials) if sum(r["claimed_checked_count"] for r in trials) > 0 else 0

        print(f"{key:<45} {n:>4} {avg_calls:>10.1f} {avg_coverage:>8.1%} {skip_trials:>6} {skip_rate:>8.1%}")

    print("-" * 90)
    print(f"Total: {total_trials} trials, {total_skips} with silent skips")

    # Package-level analysis
    print(f"\n--- Packages most frequently skipped ---")
    skip_counts = defaultdict(int)
    for r in results:
        for pkg in r.get("packages_not_called", []):
            skip_counts[pkg] += 1

    if skip_counts:
        for pkg, count in sorted(skip_counts.items(), key=lambda x: -x[1])[:20]:
            print(f"  {pkg}: {count} skips")
    else:
        print("  No skips detected.")

    # Position analysis (for 100-dep lists)
    print(f"\n--- Skip position analysis (100-dep lists) ---")
    position_skips = defaultdict(int)
    position_total = defaultdict(int)
    for r in results:
        if r["condition"]["list_size"] == 100:
            deps_100 = json.loads((Path(__file__).resolve().parent.parent / "data" / "deps_100.json").read_text())
            for i, d in enumerate(deps_100):
                bucket = "first_30" if i < 30 else ("mid_30_70" if i < 70 else "last_30")
                position_total[bucket] += 1
                if d["name"].lower() in [p.lower() for p in r.get("packages_not_called", [])]:
                    position_skips[bucket] += 1

    for bucket in ["first_30", "mid_30_70", "last_30"]:
        total = position_total.get(bucket, 0)
        skips = position_skips.get(bucket, 0)
        rate = skips / total if total else 0
        print(f"  {bucket}: {skips}/{total} ({rate:.1%})")


if __name__ == "__main__":
    main()
