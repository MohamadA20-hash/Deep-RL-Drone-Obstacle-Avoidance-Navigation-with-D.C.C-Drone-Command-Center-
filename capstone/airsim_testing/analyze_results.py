"""
NavRL Capstone — Results Analyzer & Diagram Generator
=====================================================
Reads JSON results from the results/ folder and generates:
  - Comparison tables (console + LaTeX)
  - Bar charts, box plots, trajectories, heatmaps
  - Ablation study plots
  - Statistical significance tests

Usage:
    python analyze_results.py                   # Analyze all available results
    python analyze_results.py --test 1 2        # Specific tests
    python analyze_results.py --latex            # Also generate LaTeX tables
"""

import json
import argparse
import sys
import os
import glob
import numpy as np
from pathlib import Path
from datetime import datetime
from scipy import stats as scipy_stats

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec

# ============================================================================
# PATHS
# ============================================================================
RESULTS_DIR = Path(__file__).parent / "results"
DIAGRAMS_DIR = RESULTS_DIR / "diagrams"
DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)

# Color scheme
COLORS = {
    "pure_rl": "#e74c3c",   # red
    "hybrid": "#2ecc71",     # green
    "RL": "#e74c3c",
    "RL+Alt": "#f39c12",     # orange
    "A*+Alt": "#3498db",     # blue
    "A*+RL+Alt": "#2ecc71",  # green
}

LABELS = {
    "pure_rl": "Pure RL (Original)",
    "hybrid": "Hybrid (A*+RL+Alt)",
}


def load_latest_result(test_name):
    """Load the most recent result file for a test."""
    pattern = str(RESULTS_DIR / test_name / f"{test_name}_*.json")
    files = sorted(glob.glob(pattern))
    if not files:
        return None
    with open(files[-1], 'r') as f:
        return json.load(f)


# ============================================================================
# TEST 1 & 2 — Navigation Comparison
# ============================================================================

def analyze_navigation_comparison():
    """Compare Pure RL (Test 1) vs Hybrid (Test 2)."""
    t1 = load_latest_result("test1_pure_rl_baseline")
    t2 = load_latest_result("test2_hybrid_controller")
    if not t1 or not t2:
        print("Missing Test 1 or Test 2 results.")
        return

    scenarios = list(t1["scenarios"].keys())

    # --- Figure 1: Success Rate Bar Chart ---
    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(len(scenarios))
    w = 0.35

    sr_rl = [t1["scenarios"][s]["aggregate"]["success_rate"] for s in scenarios]
    sr_hy = [t2["scenarios"][s]["aggregate"]["success_rate"] for s in scenarios]

    bars1 = ax.bar(x - w/2, sr_rl, w, label=LABELS["pure_rl"], color=COLORS["pure_rl"], alpha=0.85)
    bars2 = ax.bar(x + w/2, sr_hy, w, label=LABELS["hybrid"], color=COLORS["hybrid"], alpha=0.85)

    # Add CI whiskers
    for i, s in enumerate(scenarios):
        ci_rl = t1["scenarios"][s]["aggregate"].get("success_rate_ci95", [0, 100])
        ci_hy = t2["scenarios"][s]["aggregate"].get("success_rate_ci95", [0, 100])
        ax.errorbar(i - w/2, sr_rl[i], yerr=[[sr_rl[i]-ci_rl[0]], [ci_rl[1]-sr_rl[i]]],
                     fmt='none', color='black', capsize=3)
        ax.errorbar(i + w/2, sr_hy[i], yerr=[[sr_hy[i]-ci_hy[0]], [ci_hy[1]-sr_hy[i]]],
                     fmt='none', color='black', capsize=3)

    ax.set_ylabel('Success Rate (%)', fontsize=12)
    ax.set_title('Navigation Success Rate: Pure RL vs Hybrid Controller', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([s.replace('_', '\n') for s in scenarios], fontsize=9)
    ax.legend(fontsize=11)
    ax.set_ylim(0, 110)
    ax.grid(axis='y', alpha=0.3)

    # Add value labels
    for bars in [bars1, bars2]:
        for bar in bars:
            h = bar.get_height()
            if h > 0:
                ax.text(bar.get_x() + bar.get_width()/2, h + 2, f'{h:.0f}%',
                        ha='center', va='bottom', fontsize=8)

    plt.tight_layout()
    plt.savefig(DIAGRAMS_DIR / "fig1_success_rate_comparison.png", dpi=150)
    plt.close()
    print("  Saved: fig1_success_rate_comparison.png")

    # --- Figure 2: Path Efficiency Box Plot ---
    fig, ax = plt.subplots(figsize=(12, 6))
    rl_effs = []
    hy_effs = []
    scenario_labels = []

    for s in scenarios:
        rl_trials = t1["scenarios"][s]["trials"]
        hy_trials = t2["scenarios"][s]["trials"]
        rl_e = [t["summary"]["path_efficiency"] for t in rl_trials
                if t.get("summary", {}).get("success")]
        hy_e = [t["summary"]["path_efficiency"] for t in hy_trials
                if t.get("summary", {}).get("success")]
        rl_effs.append(rl_e if rl_e else [0])
        hy_effs.append(hy_e if hy_e else [0])
        scenario_labels.append(s.replace('_', '\n'))

    positions_rl = np.arange(len(scenarios)) * 2.5
    positions_hy = positions_rl + 0.7

    bp1 = ax.boxplot(rl_effs, positions=positions_rl, widths=0.6,
                     patch_artist=True, boxprops=dict(facecolor=COLORS["pure_rl"], alpha=0.6))
    bp2 = ax.boxplot(hy_effs, positions=positions_hy, widths=0.6,
                     patch_artist=True, boxprops=dict(facecolor=COLORS["hybrid"], alpha=0.6))

    ax.set_xticks(positions_rl + 0.35)
    ax.set_xticklabels(scenario_labels, fontsize=9)
    ax.set_ylabel('Path Efficiency (%)', fontsize=12)
    ax.set_title('Path Efficiency Distribution: Pure RL vs Hybrid', fontsize=14, fontweight='bold')
    ax.legend([bp1["boxes"][0], bp2["boxes"][0]], [LABELS["pure_rl"], LABELS["hybrid"]], fontsize=11)
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    plt.savefig(DIAGRAMS_DIR / "fig2_path_efficiency_boxplot.png", dpi=150)
    plt.close()
    print("  Saved: fig2_path_efficiency_boxplot.png")

    # --- Figure 3: Time to Goal ---
    fig, ax = plt.subplots(figsize=(12, 6))
    rl_times = [t1["scenarios"][s]["aggregate"]["time_to_goal"]["mean"] for s in scenarios]
    hy_times = [t2["scenarios"][s]["aggregate"]["time_to_goal"]["mean"] for s in scenarios]
    rl_std = [t1["scenarios"][s]["aggregate"]["time_to_goal"]["std"] for s in scenarios]
    hy_std = [t2["scenarios"][s]["aggregate"]["time_to_goal"]["std"] for s in scenarios]

    ax.bar(x - w/2, rl_times, w, yerr=rl_std, label=LABELS["pure_rl"],
           color=COLORS["pure_rl"], alpha=0.85, capsize=3)
    ax.bar(x + w/2, hy_times, w, yerr=hy_std, label=LABELS["hybrid"],
           color=COLORS["hybrid"], alpha=0.85, capsize=3)

    ax.set_ylabel('Time to Goal (s)', fontsize=12)
    ax.set_title('Average Time to Goal: Pure RL vs Hybrid', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([s.replace('_', '\n') for s in scenarios], fontsize=9)
    ax.legend(fontsize=11)
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    plt.savefig(DIAGRAMS_DIR / "fig3_time_to_goal.png", dpi=150)
    plt.close()
    print("  Saved: fig3_time_to_goal.png")

    # --- Print comparison table ---
    _print_comparison_table(t1, t2, scenarios)


def _print_comparison_table(t1, t2, scenarios):
    """Print a formatted comparison table."""
    print("\n" + "=" * 100)
    print("NAVIGATION COMPARISON TABLE")
    print("=" * 100)
    header = f"{'Scenario':<20} {'SR-RL':>6} {'SR-HY':>6} {'Eff-RL':>7} {'Eff-HY':>7} {'T-RL':>6} {'T-HY':>6} {'Col-RL':>7} {'Col-HY':>7}"
    print(header)
    print("-" * 100)

    for s in scenarios:
        r1 = t1["scenarios"][s]["aggregate"]
        r2 = t2["scenarios"][s]["aggregate"]
        print(f"{s:<20} "
              f"{r1['success_rate']:>5.0f}% "
              f"{r2['success_rate']:>5.0f}% "
              f"{r1['path_efficiency']['mean']:>6.1f}% "
              f"{r2['path_efficiency']['mean']:>6.1f}% "
              f"{r1['time_to_goal']['mean']:>5.1f}s "
              f"{r2['time_to_goal']['mean']:>5.1f}s "
              f"{r1['collision_rate']:>6.0f}% "
              f"{r2['collision_rate']:>6.0f}%")


# ============================================================================
# TEST 3 — Obstacle Avoidance
# ============================================================================

def analyze_obstacle_avoidance():
    """Analyze obstacle avoidance results."""
    data = load_latest_result("test3_obstacle_avoidance")
    if not data:
        print("Missing Test 3 results.")
        return

    scenarios = [s for s in (data["controllers"].get("pure_rl", {}).keys())]
    if not scenarios:
        return

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    # Success rate
    ax = axes[0]
    x = np.arange(len(scenarios))
    w = 0.35
    for i, ctrl in enumerate(["pure_rl", "hybrid"]):
        if ctrl not in data["controllers"]:
            continue
        srs = [data["controllers"][ctrl][s]["aggregate"]["success_rate"] for s in scenarios]
        ax.bar(x + i*w - w/2, srs, w, label=LABELS[ctrl], color=COLORS[ctrl], alpha=0.85)
    ax.set_title('Success Rate', fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([s.replace('_', '\n') for s in scenarios], fontsize=8)
    ax.set_ylabel('%')
    ax.legend(fontsize=9)
    ax.set_ylim(0, 110)

    # Min obstacle distance
    ax = axes[1]
    for i, ctrl in enumerate(["pure_rl", "hybrid"]):
        if ctrl not in data["controllers"]:
            continue
        dists = [data["controllers"][ctrl][s]["aggregate"]["min_obstacle_distance"]["mean"] for s in scenarios]
        ax.bar(x + i*w - w/2, dists, w, label=LABELS[ctrl], color=COLORS[ctrl], alpha=0.85)
    ax.set_title('Min Obstacle Distance', fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([s.replace('_', '\n') for s in scenarios], fontsize=8)
    ax.set_ylabel('Distance (m)')
    ax.legend(fontsize=9)

    # Close calls
    ax = axes[2]
    for i, ctrl in enumerate(["pure_rl", "hybrid"]):
        if ctrl not in data["controllers"]:
            continue
        cc = [data["controllers"][ctrl][s]["aggregate"]["close_calls"]["mean"] for s in scenarios]
        ax.bar(x + i*w - w/2, cc, w, label=LABELS[ctrl], color=COLORS[ctrl], alpha=0.85)
    ax.set_title('Close Calls (< 1.5m)', fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([s.replace('_', '\n') for s in scenarios], fontsize=8)
    ax.set_ylabel('Count')
    ax.legend(fontsize=9)

    plt.suptitle('Obstacle Avoidance: Pure RL vs Hybrid', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(DIAGRAMS_DIR / "fig4_obstacle_avoidance.png", dpi=150)
    plt.close()
    print("  Saved: fig4_obstacle_avoidance.png")


# ============================================================================
# TEST 4 — Altitude Dynamics
# ============================================================================

def analyze_altitude():
    """Analyze altitude dynamics results."""
    data = load_latest_result("test4_altitude_dynamics")
    if not data:
        print("Missing Test 4 results.")
        return

    scenarios = list(data["scenarios"].keys())

    # Altitude time series from first successful trial
    fig, axes = plt.subplots(len(scenarios), 1, figsize=(12, 3*len(scenarios)), sharex=False)
    if len(scenarios) == 1:
        axes = [axes]

    for idx, s in enumerate(scenarios):
        ax = axes[idx]
        trials = data["scenarios"][s]["trials"]
        for i, trial in enumerate(trials[:3]):  # Plot first 3 trials
            traj = trial.get("trajectory", {})
            alts = traj.get("altitudes", [])
            if alts:
                t = np.arange(len(alts)) / 20.0  # 20Hz control
                ax.plot(t, alts, alpha=0.6, label=f'Trial {i+1}')

        ax.set_ylabel('Altitude (m)')
        ax.set_title(f'{s} (target: {data["scenarios"][s].get("altitude", -3.0)}m NED)', fontsize=10)
        ax.legend(fontsize=8, loc='upper right')
        ax.grid(alpha=0.3)

    axes[-1].set_xlabel('Time (s)')
    plt.suptitle('Altitude Dynamics Over Time', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(DIAGRAMS_DIR / "fig5_altitude_dynamics.png", dpi=150)
    plt.close()
    print("  Saved: fig5_altitude_dynamics.png")

    # Altitude stability summary
    fig, ax = plt.subplots(figsize=(10, 5))
    means = [data["scenarios"][s]["aggregate"]["altitude_mean"]["mean"] for s in scenarios]
    stds = [data["scenarios"][s]["aggregate"]["altitude_std"]["mean"] for s in scenarios]
    ax.bar(scenarios, means, yerr=stds, capsize=5, color=COLORS["hybrid"], alpha=0.8)
    ax.set_ylabel('Mean Altitude (m)')
    ax.set_title('Altitude Stability Summary', fontsize=14, fontweight='bold')
    ax.grid(axis='y', alpha=0.3)
    plt.xticks(rotation=30, ha='right')
    plt.tight_layout()
    plt.savefig(DIAGRAMS_DIR / "fig6_altitude_stability.png", dpi=150)
    plt.close()
    print("  Saved: fig6_altitude_stability.png")


# ============================================================================
# TEST 5 — Domain Robustness
# ============================================================================

def analyze_domain_robustness():
    """Analyze domain robustness results."""
    data = load_latest_result("test5_domain_robustness")
    if not data:
        print("Missing Test 5 results.")
        return

    conds = data["conditions"]

    # Split by category
    weather = {k: v for k, v in conds.items() if k.startswith("weather_")}
    wind = {k: v for k, v in conds.items() if k.startswith("wind_")}
    lidar = {k: v for k, v in conds.items() if k.startswith("lidar_")}

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    for idx, (category, items, title) in enumerate([
        (weather, list(weather.keys()), "Weather"),
        (wind, list(wind.keys()), "Wind"),
        (lidar, list(lidar.keys()), "LiDAR Noise"),
    ]):
        ax = axes[idx]
        names = [k.split('_', 1)[1] for k in items]
        srs = [category[k]["aggregate"]["success_rate"] for k in items]
        colors_list = plt.cm.RdYlGn_r(np.linspace(0.2, 0.8, len(items)))
        ax.bar(names, srs, color=colors_list, alpha=0.85, edgecolor='black', linewidth=0.5)
        ax.set_title(title, fontweight='bold', fontsize=12)
        ax.set_ylabel('Success Rate (%)')
        ax.set_ylim(0, 110)
        ax.grid(axis='y', alpha=0.3)
        for i, v in enumerate(srs):
            ax.text(i, v + 2, f'{v:.0f}%', ha='center', fontsize=9)

    plt.suptitle('Domain Robustness: Success Rate Under Perturbations', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(DIAGRAMS_DIR / "fig7_domain_robustness.png", dpi=150)
    plt.close()
    print("  Saved: fig7_domain_robustness.png")


# ============================================================================
# TEST 6 — Multi-Waypoint
# ============================================================================

def analyze_missions():
    """Analyze multi-waypoint mission results."""
    data = load_latest_result("test6_multi_waypoint")
    if not data:
        print("Missing Test 6 results.")
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    missions = []
    for ctrl in ["pure_rl", "hybrid"]:
        if ctrl in data["controllers"]:
            missions = list(data["controllers"][ctrl].keys())
            break

    # Waypoint completion
    ax = axes[0]
    x = np.arange(len(missions))
    w = 0.35
    for i, ctrl in enumerate(["pure_rl", "hybrid"]):
        if ctrl not in data["controllers"]:
            continue
        reached = [data["controllers"][ctrl][m]["aggregate"]["avg_waypoints_reached"] for m in missions]
        totals = [data["controllers"][ctrl][m]["aggregate"]["max_waypoints"] for m in missions]
        pcts = [r/t*100 for r, t in zip(reached, totals)]
        ax.bar(x + i*w - w/2, pcts, w, label=LABELS[ctrl], color=COLORS[ctrl], alpha=0.85)
    ax.set_title('Waypoint Completion Rate', fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([m.replace('_', '\n') for m in missions])
    ax.set_ylabel('%')
    ax.set_ylim(0, 110)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)

    # RTB success
    ax = axes[1]
    for i, ctrl in enumerate(["pure_rl", "hybrid"]):
        if ctrl not in data["controllers"]:
            continue
        rtb = [data["controllers"][ctrl][m]["aggregate"]["rtb_success_rate"] for m in missions]
        ax.bar(x + i*w - w/2, rtb, w, label=LABELS[ctrl], color=COLORS[ctrl], alpha=0.85)
    ax.set_title('RTB Success Rate', fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([m.replace('_', '\n') for m in missions])
    ax.set_ylabel('%')
    ax.set_ylim(0, 110)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)

    plt.suptitle('Multi-Waypoint Mission Performance', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(DIAGRAMS_DIR / "fig8_mission_performance.png", dpi=150)
    plt.close()
    print("  Saved: fig8_mission_performance.png")


# ============================================================================
# TEST 7 — Computational Performance
# ============================================================================

def analyze_computational():
    """Analyze computational performance results."""
    data = load_latest_result("test7_computational_perf")
    if not data:
        print("Missing Test 7 results.")
        return

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    ctrls = list(data["controllers"].keys())

    # Loop time comparison
    ax = axes[0]
    metrics = ["loop_time_mean_ms", "loop_time_p95_ms", "loop_time_max_ms"]
    labels_m = ["Mean", "P95", "Max"]
    x = np.arange(len(metrics))
    w = 0.35
    for i, ctrl in enumerate(ctrls):
        vals = [data["controllers"][ctrl].get(m, 0) for m in metrics]
        ax.bar(x + i*w - w/2, vals, w, label=LABELS.get(ctrl, ctrl),
               color=COLORS.get(ctrl, '#999'), alpha=0.85)
    ax.set_title('Control Loop Time (ms)', fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(labels_m)
    ax.set_ylabel('ms')
    ax.legend()
    ax.grid(axis='y', alpha=0.3)

    # 50ms budget line
    ax.axhline(y=50, color='red', linestyle='--', alpha=0.5, label='50ms budget (20Hz)')

    # Inference time
    ax = axes[1]
    metrics_i = ["inference_mean_ms", "inference_p95_ms"]
    labels_i = ["Mean", "P95"]
    x = np.arange(len(metrics_i))
    for i, ctrl in enumerate(ctrls):
        vals = [data["controllers"][ctrl].get(m, 0) for m in metrics_i]
        ax.bar(x + i*w - w/2, vals, w, label=LABELS.get(ctrl, ctrl),
               color=COLORS.get(ctrl, '#999'), alpha=0.85)
    ax.set_title('NN Inference Time (ms)', fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(labels_i)
    ax.set_ylabel('ms')
    ax.legend()
    ax.grid(axis='y', alpha=0.3)

    plt.suptitle('Computational Performance', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(DIAGRAMS_DIR / "fig9_computational_perf.png", dpi=150)
    plt.close()
    print("  Saved: fig9_computational_perf.png")

    # Print table
    print("\n  COMPUTATIONAL PERFORMANCE TABLE")
    print("  " + "-"*60)
    for ctrl in ctrls:
        d = data["controllers"][ctrl]
        print(f"  {LABELS.get(ctrl, ctrl):<25} | Loop: {d['loop_time_mean_ms']:.1f}ms | "
              f"Infer: {d['inference_mean_ms']:.1f}ms | "
              f"Freq: {d['control_frequency_hz']:.0f}Hz | "
              f"Mem: {d['memory_avg_mb']:.0f}MB")


# ============================================================================
# TEST 8 — Ablation Study
# ============================================================================

def analyze_ablation():
    """Analyze ablation study results."""
    data = load_latest_result("test8_ablation_study")
    if not data:
        print("Missing Test 8 results.")
        return

    configs = list(data["configs"].keys())
    scenarios = list(data["configs"][configs[0]].keys())

    # --- Figure: Grouped bar chart per scenario ---
    fig, ax = plt.subplots(figsize=(14, 6))
    x = np.arange(len(scenarios))
    n = len(configs)
    w = 0.8 / n

    for i, cfg in enumerate(configs):
        srs = [data["configs"][cfg][s]["aggregate"]["success_rate"] for s in scenarios]
        ax.bar(x + i*w - (n-1)*w/2, srs, w, label=cfg,
               color=COLORS.get(cfg, f'C{i}'), alpha=0.85)

    ax.set_ylabel('Success Rate (%)', fontsize=12)
    ax.set_title('Ablation Study: Layer Contribution to Success Rate', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([s.replace('_', '\n') for s in scenarios], fontsize=9)
    ax.legend(fontsize=10, ncol=len(configs))
    ax.set_ylim(0, 110)
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    plt.savefig(DIAGRAMS_DIR / "fig10_ablation_success.png", dpi=150)
    plt.close()
    print("  Saved: fig10_ablation_success.png")

    # --- Heatmap ---
    fig, ax = plt.subplots(figsize=(10, 5))
    matrix = np.array([
        [data["configs"][cfg][s]["aggregate"]["success_rate"] for s in scenarios]
        for cfg in configs
    ])
    im = ax.imshow(matrix, cmap='RdYlGn', vmin=0, vmax=100, aspect='auto')

    ax.set_xticks(np.arange(len(scenarios)))
    ax.set_yticks(np.arange(len(configs)))
    ax.set_xticklabels([s.replace('_', ' ') for s in scenarios], fontsize=9)
    ax.set_yticklabels(configs, fontsize=10)

    for i in range(len(configs)):
        for j in range(len(scenarios)):
            v = matrix[i, j]
            color = 'white' if v < 50 else 'black'
            ax.text(j, i, f'{v:.0f}%', ha='center', va='center', color=color, fontweight='bold')

    plt.colorbar(im, ax=ax, label='Success Rate (%)')
    ax.set_title('Ablation Study Heatmap', fontsize=14, fontweight='bold')

    plt.tight_layout()
    plt.savefig(DIAGRAMS_DIR / "fig11_ablation_heatmap.png", dpi=150)
    plt.close()
    print("  Saved: fig11_ablation_heatmap.png")

    # --- Statistical testing: paired comparisons ---
    print("\n  ABLATION STATISTICAL COMPARISON")
    print("  " + "-"*70)

    # Compare each config pair using success counts across scenarios
    for i, c1 in enumerate(configs):
        for c2 in configs[i+1:]:
            s1 = [data["configs"][c1][s]["aggregate"]["success_rate"] for s in scenarios]
            s2 = [data["configs"][c2][s]["aggregate"]["success_rate"] for s in scenarios]
            if len(s1) >= 2:
                t_stat, p_val = scipy_stats.ttest_rel(s1, s2)
                diff = np.mean(s2) - np.mean(s1)
                std_pool = np.std(np.array(s2) - np.array(s1))
                cohens_d = diff / std_pool if std_pool > 0 else 0
                sig = "***" if p_val < 0.001 else ("**" if p_val < 0.01 else ("*" if p_val < 0.05 else "ns"))
                print(f"  {c1:<12} vs {c2:<12} | Diff: {diff:+.1f}% | "
                      f"t={t_stat:.2f} p={p_val:.4f} {sig} | d={cohens_d:.2f}")

    # Print summary table
    print("\n  ABLATION SUMMARY")
    print("  " + "-"*80)
    print(f"  {'Config':<12}", end="")
    for s in scenarios:
        print(f" {s[:12]:>12}", end="")
    print(f" {'Mean':>8}")
    print("  " + "-"*80)
    for cfg in configs:
        print(f"  {cfg:<12}", end="")
        srs = []
        for s in scenarios:
            sr = data["configs"][cfg][s]["aggregate"]["success_rate"]
            srs.append(sr)
            print(f" {sr:>11.0f}%", end="")
        print(f" {np.mean(srs):>7.1f}%")


# ============================================================================
# SUMMARY REPORT
# ============================================================================

def generate_summary_report():
    """Generate an overall text summary of all tests."""
    report_lines = [
        "=" * 80,
        "NAVRL CAPSTONE — TEST RESULTS SUMMARY",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 80, ""
    ]

    # Test 1 & 2 summary
    t1 = load_latest_result("test1_pure_rl_baseline")
    t2 = load_latest_result("test2_hybrid_controller")
    if t1 and t2:
        rl_avg = np.mean([t1["scenarios"][s]["aggregate"]["success_rate"]
                          for s in t1["scenarios"]])
        hy_avg = np.mean([t2["scenarios"][s]["aggregate"]["success_rate"]
                          for s in t2["scenarios"]])
        report_lines += [
            "1. NAVIGATION (Tests 1 & 2)",
            f"   Pure RL avg success: {rl_avg:.1f}%",
            f"   Hybrid avg success:  {hy_avg:.1f}%",
            f"   Improvement:         {hy_avg - rl_avg:+.1f}%", ""
        ]

    # Test 3 summary
    t3 = load_latest_result("test3_obstacle_avoidance")
    if t3:
        for ctrl in ["pure_rl", "hybrid"]:
            if ctrl in t3["controllers"]:
                avg_sr = np.mean([t3["controllers"][ctrl][s]["aggregate"]["success_rate"]
                                  for s in t3["controllers"][ctrl]])
                report_lines.append(f"   {LABELS.get(ctrl, ctrl)}: {avg_sr:.0f}% obstacle success")
        report_lines.append("")

    # Test 8 summary
    t8 = load_latest_result("test8_ablation_study")
    if t8:
        report_lines.append("2. ABLATION STUDY (Test 8)")
        for cfg in t8["configs"]:
            avg = np.mean([t8["configs"][cfg][s]["aggregate"]["success_rate"]
                           for s in t8["configs"][cfg]])
            report_lines.append(f"   {cfg:<12}: {avg:.1f}% avg success")
        report_lines.append("")

    report = "\n".join(report_lines)
    summary_path = RESULTS_DIR / "SUMMARY_REPORT.txt"
    with open(summary_path, 'w') as f:
        f.write(report)
    print(f"\n  Summary saved: {summary_path}")
    print(report)


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="NavRL Results Analyzer")
    parser.add_argument("--test", nargs="+", default=["all"])
    parser.add_argument("--latex", action="store_true", help="Generate LaTeX tables")
    args = parser.parse_args()

    tests = set()
    for t in args.test:
        if t == "all":
            tests = {1, 2, 3, 4, 5, 6, 7, 8}
            break
        tests.add(int(t))

    print("\n" + "#" * 60)
    print("NAVRL CAPSTONE — RESULTS ANALYZER")
    print("#" * 60)

    analyzers = {
        1: ("Navigation Comparison (T1 vs T2)", analyze_navigation_comparison),
        3: ("Obstacle Avoidance (T3)", analyze_obstacle_avoidance),
        4: ("Altitude Dynamics (T4)", analyze_altitude),
        5: ("Domain Robustness (T5)", analyze_domain_robustness),
        6: ("Multi-Waypoint (T6)", analyze_missions),
        7: ("Computational Perf (T7)", analyze_computational),
        8: ("Ablation Study (T8)", analyze_ablation),
    }

    # Tests 1 and 2 are analyzed together
    if 1 in tests or 2 in tests:
        print("\n--- Navigation Comparison (T1 & T2) ---")
        analyze_navigation_comparison()

    for num in sorted(tests):
        if num in (1, 2):
            continue
        if num in analyzers:
            name, func = analyzers[num]
            print(f"\n--- {name} ---")
            try:
                func()
            except Exception as e:
                print(f"  Error: {e}")

    generate_summary_report()
    print(f"\nAll diagrams saved to: {DIAGRAMS_DIR}")


if __name__ == "__main__":
    main()
