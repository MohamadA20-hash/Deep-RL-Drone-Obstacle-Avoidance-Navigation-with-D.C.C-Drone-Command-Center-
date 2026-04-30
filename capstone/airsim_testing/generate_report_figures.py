"""
Generate the 7 report figures defined in CAPSTONE_REPORT.md.

Inputs (per-leg CSV files written by capstone_test_runner.py):
  results/standard/roam_*_5runs.csv
  results/ablation/roam_ablation_*_5runs.csv
  results/sensor_noise/roam_sensor_noise_*_5runs.csv
  results/domain_randomization/roam_domain_randomization_*_5runs.csv

Outputs (PNGs in results/diagrams/):
  fig1_success_rate_bar.png         - Bar chart: PureRL vs Hybrid (Standard, ±std)
  fig2_collisions_box.png           - Box plot: Collisions/km per controller (Standard)
  fig3_ablation_grouped_bar.png     - Grouped bars: 5 controllers across 4 metrics
  fig4_dr_success_line.png          - Line plot: Success across 5 weather conditions
  fig5_dr_collisions_box.png        - Bar+box: collision rate per weather condition
  fig6_noise_success_collisions.png - Dual-axis: Success + Collision vs noise level
  fig7_noise_collisions_bar.png     - Bar chart: collisions/km per noise condition

Usage:
    python generate_report_figures.py
"""

from __future__ import annotations

from pathlib import Path
import glob
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent / "results"
DIAGRAMS = ROOT / "diagrams"
DIAGRAMS.mkdir(parents=True, exist_ok=True)


def _latest(pattern: str) -> Path:
    matches = sorted(glob.glob(str(ROOT / pattern)))
    if not matches:
        raise FileNotFoundError(pattern)
    return Path(matches[-1])


SUITE = {
    "standard": _latest("standard/roam_*_5runs.csv"),
    "ablation": _latest("ablation/roam_ablation_*_5runs.csv"),
    "noise":    _latest("sensor_noise/roam_sensor_noise_*_5runs.csv"),
    "dr":       _latest("domain_randomization/roam_domain_randomization_*_5runs.csv"),
}

CTRL_LABEL = {
    "pure_rl": "Pure RL", "hybrid": "NavRL + CityPlanner",
    "rl_fixed_alt": "RL + Fixed Alt", "rl_alt": "RL + Alt SM",
    "p_control_alt": "P-Control + Alt SM",
    "PureRL": "Pure RL", "RL+FixedAlt": "RL + Fixed Alt",
    "RL+AltSM": "RL + Alt SM", "PControl+AltSM": "P-Control + Alt SM",
    "NavRL+CityPlanner": "NavRL + CityPlanner",
}
CTRL_COLOR = {
    "pure_rl": "#e74c3c", "hybrid": "#2ecc71",
    "rl_fixed_alt": "#9b59b6", "rl_alt": "#f39c12", "p_control_alt": "#3498db",
    "PureRL": "#e74c3c", "RL+FixedAlt": "#9b59b6", "RL+AltSM": "#f39c12",
    "PControl+AltSM": "#3498db", "NavRL+CityPlanner": "#2ecc71",
}

NOISE_ORDER = ["clean", "lidar_noise_light", "lidar_noise_heavy", "lidar_dropout"]
NOISE_LABEL = {"clean": "Clean", "lidar_noise_light": "Light Noise",
               "lidar_noise_heavy": "Heavy Noise", "lidar_dropout": "Dropout"}

RUN_COLS = [
    "run_success_rate", "run_collisions", "run_collision_rate_per_km",
    "run_avg_efficiency_pct", "run_avg_time_to_goal_s",
    "run_avg_min_obstacle_m", "run_total_close_calls",
    "run_recovery_score_pct",
]

plt.rcParams.update({
    "font.size": 11, "axes.titlesize": 13, "axes.titleweight": "bold",
    "axes.labelsize": 11, "axes.spines.top": False, "axes.spines.right": False,
    "figure.dpi": 110,
})


def _per_run(df: pd.DataFrame, extra_keys=()) -> pd.DataFrame:
    keys = ["controller", *extra_keys, "run"]
    return df[keys + RUN_COLS].drop_duplicates(keys).reset_index(drop=True)


# ---------------------------------------------------------------------------
# FIGURE 1
# ---------------------------------------------------------------------------
def fig1_standard_success_bar():
    df = _per_run(pd.read_csv(SUITE["standard"]))
    ctrls = ["pure_rl", "hybrid"]
    means = [df[df.controller == c]["run_success_rate"].mean() for c in ctrls]
    stds  = [df[df.controller == c]["run_success_rate"].std(ddof=0) for c in ctrls]

    fig, ax = plt.subplots(figsize=(7, 5.5))
    x = np.arange(len(ctrls))
    bars = ax.bar(x, means, yerr=stds, capsize=8,
                  color=[CTRL_COLOR[c] for c in ctrls], alpha=0.9,
                  edgecolor="black", linewidth=0.8)

    for i, c in enumerate(ctrls):
        vals = df[df.controller == c]["run_success_rate"].values
        ax.scatter(np.full_like(vals, i, dtype=float) + np.random.uniform(-0.08, 0.08, len(vals)),
                   vals, color="black", s=28, zorder=3, alpha=0.7)

    ax.set_xticks(x)
    ax.set_xticklabels([CTRL_LABEL[c] for c in ctrls], fontsize=11)
    ax.set_ylabel("Success Rate (%)")
    ax.set_title("Figure 1 — Success Rate: Pure RL vs NavRL+CityPlanner\n(Standard Suite, n=5 runs × 12 goals)")
    ax.set_ylim(0, 110)
    ax.grid(axis="y", alpha=0.3)
    for bar, m in zip(bars, means):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 2,
                f"{m:.1f}%", ha="center", va="bottom", fontsize=11, fontweight="bold")

    delta = means[1] - means[0]
    ax.annotate(f"+{delta:.1f} pp",
                xy=(0.5, max(means) + 8), xytext=(0.5, max(means) + 16),
                ha="center", fontsize=12, fontweight="bold", color="#2c3e50",
                arrowprops=dict(arrowstyle="-[,widthB=3.5", color="#2c3e50", lw=1.5))

    plt.tight_layout()
    plt.savefig(DIAGRAMS / "fig1_success_rate_bar.png"); plt.close()
    print("  saved fig1_success_rate_bar.png")


# ---------------------------------------------------------------------------
# FIGURE 2
# ---------------------------------------------------------------------------
def fig2_standard_collisions_box():
    df = _per_run(pd.read_csv(SUITE["standard"]))
    ctrls = ["pure_rl", "hybrid"]
    data = [df[df.controller == c]["run_collision_rate_per_km"].values for c in ctrls]

    fig, ax = plt.subplots(figsize=(7, 5.5))
    bp = ax.boxplot(data, positions=[0, 1], widths=0.55, patch_artist=True,
                    medianprops=dict(color="black", linewidth=1.6))
    for patch, c in zip(bp["boxes"], ctrls):
        patch.set_facecolor(CTRL_COLOR[c]); patch.set_alpha(0.75)

    for i, vals in enumerate(data):
        jitter = np.random.uniform(-0.1, 0.1, len(vals))
        ax.scatter(np.full_like(vals, i, dtype=float) + jitter, vals,
                   color="black", s=30, zorder=3, alpha=0.75)
        ax.text(i, max(vals) + 0.5, f"μ={np.mean(vals):.2f}",
                ha="center", fontsize=10, fontweight="bold")

    ax.set_xticks([0, 1])
    ax.set_xticklabels([CTRL_LABEL[c] for c in ctrls], fontsize=11)
    ax.set_ylabel("Collisions per km")
    ax.set_title("Figure 2 — Collision Rate Distribution\n(Standard Suite, 5 runs per controller)")
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(DIAGRAMS / "fig2_collisions_box.png"); plt.close()
    print("  saved fig2_collisions_box.png")


# ---------------------------------------------------------------------------
# FIGURE 3
# ---------------------------------------------------------------------------
def fig3_ablation_grouped():
    df = pd.read_csv(SUITE["ablation"])
    ctrl_col = "config" if "config" in df.columns else "controller"
    keys = [ctrl_col, "run"]
    runs = df[keys + RUN_COLS].drop_duplicates(keys).reset_index(drop=True)

    order_pref = ["PureRL", "RL+FixedAlt", "RL+AltSM", "PControl+AltSM", "NavRL+CityPlanner"]
    order = [o for o in order_pref if o in runs[ctrl_col].unique()]

    metrics = [
        ("run_success_rate",          "Success Rate (%)",    True),
        ("run_collision_rate_per_km", "Collisions / km",     False),
        ("run_avg_efficiency_pct",    "Path Efficiency (%)", True),
        ("run_recovery_score_pct",    "Recovery Score (%)",  True),
    ]

    fig, axes = plt.subplots(1, 4, figsize=(20, 5.5))
    x = np.arange(len(order))

    for ax, (col, ylabel, pct) in zip(axes, metrics):
        means = [runs[runs[ctrl_col] == c][col].mean() for c in order]
        stds  = [runs[runs[ctrl_col] == c][col].std(ddof=0) for c in order]
        colors = [CTRL_COLOR[c] for c in order]
        bars = ax.bar(x, means, yerr=stds, capsize=4, color=colors,
                      alpha=0.9, edgecolor="black", linewidth=0.6)
        ax.set_xticks(x)
        ax.set_xticklabels([CTRL_LABEL[c] for c in order],
                           rotation=20, ha="right", fontsize=9)
        ax.set_ylabel(ylabel)
        ax.set_title(ylabel.split(" (")[0])
        ax.grid(axis="y", alpha=0.3)
        if pct:
            ax.set_ylim(0, 115)
        for bar, m in zip(bars, means):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    f"{m:.1f}", ha="center", va="bottom", fontsize=8)

    fig.suptitle("Figure 3 — Ablation Study: Component Contribution Across 4 Key Metrics\n(Ablation Suite, 5 runs × 12 goals each)",
                 fontsize=14, fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.92])
    plt.savefig(DIAGRAMS / "fig3_ablation_grouped_bar.png"); plt.close()
    print("  saved fig3_ablation_grouped_bar.png")


# ---------------------------------------------------------------------------
# FIGURE 4
# ---------------------------------------------------------------------------
def fig4_dr_success_line():
    df = pd.read_csv(SUITE["dr"])
    runs = _per_run(df, extra_keys=("condition",))
    conditions = ["randomized_01", "randomized_02", "randomized_03", "randomized_04", "randomized_05"]
    cond_labels = [f"W{i+1}" for i in range(len(conditions))]

    fig, ax = plt.subplots(figsize=(11, 6.2))
    for ctrl in ["pure_rl", "hybrid"]:
        ys = [runs[(runs.controller == ctrl) & (runs.condition == c)]["run_success_rate"].mean()
              for c in conditions]
        ax.plot(cond_labels, ys, marker="o", markersize=11, linewidth=2.4,
                color=CTRL_COLOR[ctrl], label=CTRL_LABEL[ctrl],
                markeredgecolor="black", markeredgewidth=0.6)
        for x_lab, y in zip(cond_labels, ys):
            ax.text(x_lab, y + 2.5, f"{y:.0f}%", ha="center",
                    fontsize=9, color=CTRL_COLOR[ctrl], fontweight="bold")

    cond_meta = (df.drop_duplicates("condition")
                   .set_index("condition")[["fog", "rain", "wind_speed"]])
    sub_labels = []
    for c in conditions:
        if c in cond_meta.index:
            r = cond_meta.loc[c]
            sub_labels.append(f"fog={r.fog:.2f}\nrain={r.rain:.2f}\nwind={r.wind_speed:.1f}m/s")
        else:
            sub_labels.append("")
    for i, txt in enumerate(sub_labels):
        ax.text(i, -8, txt, ha="center", va="top", fontsize=8, color="#555")

    ax.set_ylabel("Success Rate (%)")
    ax.set_title("Figure 4 — Success Rate Across Randomized Weather Conditions\n(Domain Randomization Suite)")
    ax.set_ylim(-15, 110)
    ax.set_yticks(np.arange(0, 110, 20))
    ax.grid(axis="y", alpha=0.3)
    ax.legend(loc="lower left", frameon=False)
    plt.tight_layout()
    plt.savefig(DIAGRAMS / "fig4_dr_success_line.png"); plt.close()
    print("  saved fig4_dr_success_line.png")


# ---------------------------------------------------------------------------
# FIGURE 5
# ---------------------------------------------------------------------------
def fig5_dr_collisions_box():
    df = pd.read_csv(SUITE["dr"])
    runs = _per_run(df, extra_keys=("condition",))
    conditions = ["randomized_01", "randomized_02", "randomized_03", "randomized_04", "randomized_05"]
    cond_labels = [f"W{i+1}" for i in range(len(conditions))]

    fig, ax = plt.subplots(figsize=(11, 5.8))
    width = 0.36
    x = np.arange(len(conditions))

    for i, ctrl in enumerate(["pure_rl", "hybrid"]):
        vals = []
        for c in conditions:
            sub = runs[(runs.controller == ctrl) & (runs.condition == c)]["run_collision_rate_per_km"]
            vals.append(float(sub.values[0]) if len(sub) else np.nan)
        offset = (i - 0.5) * width
        bars = ax.bar(x + offset, vals, width, color=CTRL_COLOR[ctrl], alpha=0.9,
                      edgecolor="black", linewidth=0.6, label=CTRL_LABEL[ctrl])
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    f"{v:.1f}", ha="center", va="bottom", fontsize=8)

    inset = ax.inset_axes([0.74, 0.55, 0.23, 0.40])
    box_data = [runs[runs.controller == c]["run_collision_rate_per_km"].astype(float).values
                for c in ["pure_rl", "hybrid"]]
    bp = inset.boxplot(box_data, positions=[0, 1], widths=0.55, patch_artist=True,
                       medianprops=dict(color="black", linewidth=1.4))
    for p, c in zip(bp["boxes"], ["pure_rl", "hybrid"]):
        p.set_facecolor(CTRL_COLOR[c]); p.set_alpha(0.8)
    inset.set_xticks([0, 1])
    inset.set_xticklabels(["RL", "Hybrid"], fontsize=8)
    inset.set_title("Distribution\n(across 5 conditions)", fontsize=8)
    inset.tick_params(axis="y", labelsize=7)
    inset.grid(axis="y", alpha=0.3)

    ax.set_xticks(x)
    ax.set_xticklabels(cond_labels)
    ax.set_ylabel("Collisions per km")
    ax.set_title("Figure 5 — Collision Rate by Weather Condition\n(Domain Randomization Suite)")
    ax.grid(axis="y", alpha=0.3)
    ax.legend(loc="upper left", frameon=False)
    plt.tight_layout()
    plt.savefig(DIAGRAMS / "fig5_dr_collisions_box.png"); plt.close()
    print("  saved fig5_dr_collisions_box.png")


# ---------------------------------------------------------------------------
# FIGURE 6
# ---------------------------------------------------------------------------
def fig6_noise_dual_axis():
    df = pd.read_csv(SUITE["noise"])
    runs = _per_run(df, extra_keys=("condition",))
    conditions = NOISE_ORDER
    cond_labels = [NOISE_LABEL[c] for c in conditions]

    fig, ax1 = plt.subplots(figsize=(11, 5.8))
    ax2 = ax1.twinx()
    ax2.spines["right"].set_visible(True)

    for ctrl in ["pure_rl", "hybrid"]:
        sr_mean = [runs[(runs.controller == ctrl) & (runs.condition == c)]["run_success_rate"].mean() for c in conditions]
        sr_std  = [runs[(runs.controller == ctrl) & (runs.condition == c)]["run_success_rate"].std(ddof=0) for c in conditions]
        cr_mean = [runs[(runs.controller == ctrl) & (runs.condition == c)]["run_collision_rate_per_km"].mean() for c in conditions]
        cr_std  = [runs[(runs.controller == ctrl) & (runs.condition == c)]["run_collision_rate_per_km"].std(ddof=0) for c in conditions]

        ax1.errorbar(cond_labels, sr_mean, yerr=sr_std, fmt="-o", linewidth=2.2, markersize=9,
                     color=CTRL_COLOR[ctrl], label=f"{CTRL_LABEL[ctrl]} — Success",
                     capsize=4, markeredgecolor="black", markeredgewidth=0.6)
        ax2.errorbar(cond_labels, cr_mean, yerr=cr_std, fmt="--s", linewidth=1.8, markersize=8,
                     color=CTRL_COLOR[ctrl], alpha=0.7,
                     label=f"{CTRL_LABEL[ctrl]} — Collisions/km",
                     capsize=4, markeredgecolor="black", markeredgewidth=0.4)

    ax1.set_ylabel("Success Rate (%)", fontweight="bold")
    ax1.set_ylim(0, 110)
    ax2.set_ylabel("Collisions per km", fontweight="bold", color="#444")
    ax1.set_title("Figure 6 — Robustness vs LiDAR Degradation\n(Sensor Noise Suite — solid: success, dashed: collisions)")
    ax1.grid(axis="y", alpha=0.3)

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="center left", fontsize=9, frameon=False,
               bbox_to_anchor=(1.10, 0.5))
    plt.tight_layout()
    plt.savefig(DIAGRAMS / "fig6_noise_success_collisions.png", bbox_inches="tight")
    plt.close()
    print("  saved fig6_noise_success_collisions.png")


# ---------------------------------------------------------------------------
# FIGURE 7
# ---------------------------------------------------------------------------
def fig7_noise_collisions_bar():
    df = pd.read_csv(SUITE["noise"])
    runs = _per_run(df, extra_keys=("condition",))
    conditions = NOISE_ORDER
    cond_labels = [NOISE_LABEL[c] for c in conditions]

    fig, ax = plt.subplots(figsize=(11, 5.8))
    width = 0.36
    x = np.arange(len(conditions))

    for i, ctrl in enumerate(["pure_rl", "hybrid"]):
        means = [runs[(runs.controller == ctrl) & (runs.condition == c)]["run_collision_rate_per_km"].mean() for c in conditions]
        stds  = [runs[(runs.controller == ctrl) & (runs.condition == c)]["run_collision_rate_per_km"].std(ddof=0) for c in conditions]
        offset = (i - 0.5) * width
        bars = ax.bar(x + offset, means, width, yerr=stds, capsize=4,
                      color=CTRL_COLOR[ctrl], alpha=0.9, edgecolor="black", linewidth=0.6,
                      label=CTRL_LABEL[ctrl])
        for bar, m in zip(bars, means):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    f"{m:.1f}", ha="center", va="bottom", fontsize=9, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(cond_labels)
    ax.set_ylabel("Collisions per km")
    ax.set_title("Figure 7 — Absolute Collision Rate per LiDAR Noise Condition\n(Sensor Noise Suite, 5 runs per condition)")
    ax.legend(loc="upper left", frameon=False)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(DIAGRAMS / "fig7_noise_collisions_bar.png"); plt.close()
    print("  saved fig7_noise_collisions_bar.png")


# ---------------------------------------------------------------------------
def write_summary_table():
    rows = []
    for suite_name, path in SUITE.items():
        df = pd.read_csv(path)
        if "config" in df.columns and suite_name == "ablation":
            keys = ["config", "run"]; ctrl_col = "config"
        elif "condition" in df.columns:
            keys = ["controller", "condition", "run"]; ctrl_col = "controller"
        else:
            keys = ["controller", "run"]; ctrl_col = "controller"
        runs = df[keys + RUN_COLS].drop_duplicates(keys).reset_index(drop=True)
        group_keys = [ctrl_col] + (["condition"] if "condition" in keys else [])
        agg = runs.groupby(group_keys)[RUN_COLS].agg(["mean", "std"]).round(2)
        agg.insert(0, "suite", suite_name)
        rows.append(agg.reset_index())
    pd.concat(rows, ignore_index=True).to_csv(DIAGRAMS / "summary_table.csv", index=False)
    print("  saved summary_table.csv")


def main():
    np.random.seed(0)
    print(f"Writing figures to: {DIAGRAMS}")
    fig1_standard_success_bar()
    fig2_standard_collisions_box()
    fig3_ablation_grouped()
    fig4_dr_success_line()
    fig5_dr_collisions_box()
    fig6_noise_dual_axis()
    fig7_noise_collisions_bar()
    write_summary_table()
    print("Done.")


if __name__ == "__main__":
    main()
