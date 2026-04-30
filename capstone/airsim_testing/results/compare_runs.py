"""
compare_runs.py  —  NavRL results aggregator
=============================================
Reads results from the suite-organised folder structure:

    results/
        standard/             roam_*.json
        ablation/             roam_ablation_*.json  (+ dev_runs/ sub-folder)
        domain_randomization/ roam_domain_randomization_*.json
        sensor_noise/         roam_sensor_noise_*.json
        imu_noise/            roam_imu_noise_*.json
        compare_runs.py       ← this script
        comparison.csv        ← written by --save

Usage (run from the results/ directory):
    python compare_runs.py                          # all suites, all runs
    python compare_runs.py --suite ablation         # one suite only
    python compare_runs.py --suite ablation --dev   # include dev_runs/
    python compare_runs.py --save                   # write comparison.csv
"""

import argparse
import csv
import glob
import json
from pathlib import Path

# ── Known suites ──────────────────────────────────────────────────────────────
SUITES = ["standard", "ablation", "domain_randomization", "sensor_noise", "imu_noise"]

# ── Metrics to display ────────────────────────────────────────────────────────
METRICS = [
    ("success_rate",            "Success %",        ".1f"),
    ("collisions",              "Collisions",       ".0f"),
    ("collision_rate_per_km",   "Coll/km",          ".3f"),
    ("collision_rate_per_goal", "Coll/goal",        ".3f"),
    ("stucks",                  "Stucks",           ".0f"),
    ("timeouts",                "Timeouts",         ".0f"),
    ("avg_efficiency_pct",      "Path eff %",       ".1f"),
    ("avg_time_to_goal_s",      "Avg t2g (s)",      ".1f"),
    ("time_efficiency_mps",     "Speed m/s",        ".3f"),
    ("avg_min_obstacle_m",      "Min obs (m)",      ".3f"),
    ("total_close_calls",       "Close calls",      ".0f"),
    ("recovery_score_pct",      "Recovery %",       ".1f"),
    ("altitude_mean_m",         "Alt mean (m)",     ".2f"),
    ("altitude_std_m",          "Alt std (m)",      ".3f"),
    ("total_path_m",            "Total path (m)",   ".1f"),
    ("total_time_s",            "Total time (s)",   ".1f"),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt(val, spec):
    if val is None:
        return "—"
    try:
        return format(val, spec)
    except (TypeError, ValueError):
        return str(val)


def _leg_outcome(leg: dict) -> str:
    if leg.get("success"):   return "SUCCESS"
    if leg.get("collision"): return "COLLISION"
    if leg.get("stuck"):     return "STUCK"
    if leg.get("timeout"):   return "TIMEOUT"
    return "?"


# ── File discovery ────────────────────────────────────────────────────────────

def discover_files(results_dir: Path, suites: list[str], include_dev: bool) -> list[tuple[str, Path]]:
    """Return [(suite, path), ...] sorted by suite then timestamp."""
    found = []
    for suite in suites:
        suite_dir = results_dir / suite
        if not suite_dir.exists():
            continue
        prefix = "roam" if suite == "standard" else f"roam_{suite}"
        for p in sorted(suite_dir.glob(f"{prefix}_*.json")):
            found.append((suite, p))
        if include_dev:
            dev_dir = suite_dir / "dev_runs"
            for p in sorted(dev_dir.glob(f"{prefix}_*.json")):
                found.append((suite + "/dev", p))
    return found


# ── Loaders ───────────────────────────────────────────────────────────────────

def _extract_stats_row(suite: str, source: str, filename: str, timestamp: str,
                        n_runs: int, label: str, stats: dict, legs: list) -> dict:
    row = {
        "suite":      suite,
        "source":     source,
        "file":       filename,
        "timestamp":  timestamp,
        "controller": label,
        "n_runs":     n_runs,
        "legs":       legs,
    }
    for key, _, _ in METRICS:
        s = stats.get(key, {})
        row[key]          = s.get("mean")
        row[key + "_std"] = s.get("std")
    return row


def load_standard_or_ablation(suite: str, source: str, path: Path) -> list[dict]:
    """Handles standard + ablation JSON shape: top-level 'configs' list."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    ts = path.stem
    for pfx in ("roam_ablation_", "roam_"):
        ts = ts.replace(pfx, "")
    rows = []
    for cfg in data.get("configs", []):
        label = cfg["label"]
        res   = cfg["results"]
        stats = res["stats"]
        legs  = []
        for run in res.get("runs", []):
            legs.extend(run.get("legs", []))
        rows.append(_extract_stats_row(suite, source, path.name, ts,
                                        res["n_runs"], label, stats, legs))
    return rows


def load_condition_suite(suite: str, source: str, path: Path) -> list[dict]:
    """Handles domain_randomization / sensor_noise / imu_noise JSON shape:
       top-level 'controller_summary' dict keyed by controller name."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    ts = path.stem
    for pfx in (f"roam_{suite}_",):
        ts = ts.replace(pfx, "")
    n_runs   = data.get("num_runs", 1)
    summary  = data.get("controller_summary", {})
    rows = []
    for ctrl_key, bundle in summary.items():
        stats = bundle.get("stats", {})
        legs  = []
        for run in bundle.get("runs", []):
            legs.extend(run.get("legs", []))
        rows.append(_extract_stats_row(suite, source, path.name, ts,
                                        n_runs, ctrl_key, stats, legs))
    return rows


def load_all(results_dir: Path, suites: list[str], include_dev: bool) -> list[dict]:
    condition_suites = {"domain_randomization", "sensor_noise", "imu_noise"}
    files = discover_files(results_dir, suites, include_dev)
    rows = []
    for suite, path in files:
        bare_suite = suite.replace("/dev", "")
        source = "dev" if suite.endswith("/dev") else "final"
        if bare_suite in condition_suites:
            rows.extend(load_condition_suite(bare_suite, source, path))
        else:
            rows.extend(load_standard_or_ablation(bare_suite, source, path))
    return rows


# ── Display ───────────────────────────────────────────────────────────────────

def print_suite_summary(suite: str, rows: list[dict]) -> None:
    controllers = sorted({r["controller"] for r in rows})
    print(f"\n{'#'*72}")
    print(f"  SUITE: {suite.upper().replace('_', ' ')}  "
          f"({sum(r['n_runs'] for r in rows if r['controller'] == controllers[0])} total runs × {len(controllers)} controller(s))")
    print(f"{'#'*72}")

    for ctrl in controllers:
        ctrl_rows = [r for r in rows if r["controller"] == ctrl]
        print(f"\n{'='*70}")
        print(f"  Controller: {ctrl}")
        print(f"{'='*70}")

        col_w = 16
        hdr = f"{'Metric':<22}" + "".join(
            f"{r['timestamp'][-13:]:>{col_w}}" for r in ctrl_rows
        )
        print(hdr)
        print("-" * len(hdr))

        for key, label, spec in METRICS:
            row_str = f"{label:<22}"
            for r in ctrl_rows:
                v = r.get(key)
                row_str += f"{fmt(v, spec):>{col_w}}"
            print(row_str)

        # Per-leg table for the most recent run
        latest = ctrl_rows[-1]
        if latest.get("legs"):
            print(f"\n  Per-leg outcomes  ({latest['timestamp'][-13:]}):")
            print(f"  {'Leg':<24} {'Dist':>6} {'Time':>7} {'Path':>7} "
                  f"{'Eff%':>6} {'MinObs':>7} {'CC':>4}  Outcome")
            print(f"  {'-'*24} {'-'*6} {'-'*7} {'-'*7} {'-'*6} {'-'*7} {'-'*4}  {'-'*10}")
            for leg in latest["legs"]:
                print(
                    f"  {leg['name']:<24} "
                    f"{leg.get('start_dist', 0):>6.1f} "
                    f"{leg.get('time', 0):>7.1f} "
                    f"{leg.get('path_length', 0):>7.1f} "
                    f"{leg.get('efficiency', 0):>6.1f} "
                    f"{leg.get('min_obstacle_dist', 0):>7.3f} "
                    f"{leg.get('close_calls', 0):>4}  "
                    f"{_leg_outcome(leg)}"
                )

        # Δ first → last if more than one file
        if len(ctrl_rows) > 1:
            _print_delta(ctrl_rows)


def _print_delta(ctrl_rows: list[dict]) -> None:
    key_metrics = [
        ("success_rate",          "Success %",   ".1f", True),
        ("collision_rate_per_km", "Coll/km",     ".3f", False),
        ("timeouts",              "Timeouts",    ".0f", False),
        ("avg_min_obstacle_m",    "Min obs (m)", ".3f", True),
        ("time_efficiency_mps",   "Speed m/s",  ".3f", True),
    ]
    print(f"\n  Δ first → latest:")
    for key, label, spec, hb in key_metrics:
        v0 = ctrl_rows[0].get(key)
        v1 = ctrl_rows[-1].get(key)
        if v0 is None or v1 is None:
            continue
        delta = v1 - v0
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "=")
        sign  = "+" if delta >= 0 else ""
        print(f"    {label:<22} {fmt(v0, spec)} → {fmt(v1, spec)}  ({sign}{fmt(delta, spec)}{arrow})")


def print_cross_suite_summary(all_rows: list[dict]) -> None:
    """One-line-per-controller table across all suites."""
    suites      = []
    seen        = set()
    for r in all_rows:
        if r["suite"] not in seen:
            seen.add(r["suite"])
            suites.append(r["suite"])

    controllers = sorted({r["controller"] for r in all_rows})
    metric_key, metric_label, metric_spec = "success_rate", "Success %", ".1f"
    coll_key,   coll_label,   coll_spec   = "collision_rate_per_km", "Coll/km", ".3f"

    col_w = 22
    print(f"\n{'#'*72}")
    print("  CROSS-SUITE OVERVIEW  (latest run per suite, mean ± std)")
    print(f"{'#'*72}")
    header = f"{'Controller':<26}"
    for s in suites:
        header += f"  {s[:col_w]:^{col_w}}"
    print(header)
    print(f"  {'':24}" + "".join(f"  {'Succ% / Coll/km':^{col_w}}" for _ in suites))
    print("-" * len(header))

    for ctrl in controllers:
        row = f"  {ctrl:<24}"
        for s in suites:
            # pick the latest final run for this suite+controller
            candidates = [r for r in all_rows
                          if r["suite"] == s and r["controller"] == ctrl and r["source"] == "final"]
            if not candidates:
                row += f"  {'—':^{col_w}}"
                continue
            latest = candidates[-1]
            sv = latest.get(metric_key)
            cv = latest.get(coll_key)
            sv_std = latest.get(metric_key + "_std")
            cell = f"{fmt(sv, metric_spec)}% / {fmt(cv, coll_spec)}"
            if sv_std and sv_std > 0:
                cell += f" (±{fmt(sv_std, '.1f')})"
            row += f"  {cell:^{col_w}}"
        print(row)


# ── CSV export ────────────────────────────────────────────────────────────────

def save_csv(rows: list[dict], out_path: Path) -> None:
    fieldnames = ["suite", "source", "file", "timestamp", "controller", "n_runs"]
    for key, _, _ in METRICS:
        fieldnames += [key, key + "_std"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nSaved → {out_path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="NavRL results aggregator")
    parser.add_argument("--suite", choices=SUITES,
                        help="Show only one suite (default: all)")
    parser.add_argument("--dev", action="store_true",
                        help="Also include runs from dev_runs/ sub-folders")
    parser.add_argument("--save", action="store_true",
                        help="Write comparison.csv")
    args = parser.parse_args()

    results_dir = Path(__file__).parent
    suites_to_load = [args.suite] if args.suite else SUITES

    all_rows = load_all(results_dir, suites_to_load, args.dev)

    if not all_rows:
        print("No result JSON files found.")
        return

    # Report what was loaded
    files_seen = sorted({r["file"] for r in all_rows})
    print(f"Loaded {len(files_seen)} file(s) across "
          f"{len({r['suite'] for r in all_rows})} suite(s):")
    for suite in suites_to_load:
        suite_files = [r["file"] for r in all_rows if r["suite"] == suite]
        if suite_files:
            unique = sorted(set(suite_files))
            print(f"  {suite:<24} {len(unique)} file(s): {', '.join(unique)}")

    # Per-suite detail
    for suite in suites_to_load:
        suite_rows = [r for r in all_rows if r["suite"] == suite]
        if suite_rows:
            print_suite_summary(suite, suite_rows)

    # Cross-suite overview (only when showing multiple suites)
    if not args.suite and len({r["suite"] for r in all_rows}) > 1:
        print_cross_suite_summary(all_rows)

    if args.save:
        save_csv(all_rows, results_dir / "comparison.csv")


if __name__ == "__main__":
    main()
