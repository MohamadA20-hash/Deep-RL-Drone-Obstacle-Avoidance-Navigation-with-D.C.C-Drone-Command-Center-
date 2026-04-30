# NavRL Capstone — Testing & Metrics Plan

## Context

| Item | Detail |
|------|--------|
| **Original NavRL** | PPO + CNN, trained in Isaac Sim (1.2B frames), evaluated in Gazebo |
| **Our Modified NavRL** | Same PPO model + A* global planner + reactive altitude controller, evaluated in AirSim |
| **Key Difference** | Original = pure reactive (4m LiDAR only). Ours = 3-layer hybrid (global path + local RL + altitude) |
| **Environment** | AirSim CityEnviron (urban buildings, streets, varied heights) |
| **Checkpoint** | `quick-demos/ckpts/navrl_checkpoint.pt` (frozen, same for both modes) |

---

## Test Categories

### TEST 1 — Pure RL Baseline (Original NavRL behavior in AirSim)

**Purpose**: Establish what the *unmodified* NavRL model achieves in AirSim so we have a fair comparison baseline.

**Script**: `navrl_airsim_bridge.py` (pure RL, no altitude controller, no A* planner)

| Scenario | Goal (x, y) | Distance | Trials |
|----------|-------------|----------|--------|
| Short forward | (20, 0) | 20m | 10 |
| Short diagonal | (20, 20) | 28m | 10 |
| Medium forward | (50, 0) | 50m | 10 |
| Medium diagonal | (40, 30) | 50m | 10 |
| Long forward | (80, 0) | 80m | 10 |
| Negative axis | (30, -25) | 39m | 10 |
| Reverse | (-30, 0) | 30m | 10 |
| Long diagonal | (60, 60) | 85m | 10 |

**Metrics collected per trial**:
- `success` (bool) — reached goal within 2m
- `collision` (bool) — hit obstacle
- `time_to_goal` (s)
- `path_length` (m) — actual distance traveled
- `optimal_distance` (m) — straight-line
- `path_efficiency` (%) — optimal / actual × 100
- `min_obstacle_distance` (m)
- `close_calls` (count at < 1.5m)
- `avg_velocity` (m/s)
- `max_velocity` (m/s)
- `altitude_mean`, `altitude_std`, `altitude_min`, `altitude_max` (m)
- `z_velocity_mean`, `z_velocity_std` (m/s) — expect ≈ 0 since model trained 2D

---

### TEST 2 — Hybrid Controller (Our Modified NavRL)

**Purpose**: Same scenarios as Test 1, but using the full 3-layer system (A* + RL + altitude controller).

**Script**: `navrl_city_planner.py` via `navrl_airsim_hybrid_controller.py`

**Same 8 scenarios, same 10 trials each, same metrics** plus:
- `replans` (count) — how many times A* replanned
- `waypoints_generated` (count) — A* waypoints per mission
- `stuck_events` (count) — stuck detection triggers
- `altitude_climbs` (count) — reactive climb activations
- `altitude_state_transitions` (count) — CRUISE→CLIMB→HOLD→DESCEND changes
- `best_effort_used` (bool) — did planner accept imperfect path

---

### TEST 3 — Obstacle Avoidance Comparison

**Purpose**: Compare collision avoidance capability between pure RL and hybrid in obstacle-rich environments.

| Scenario | Goal (x, y) | Obstacle Config | Trials |
|----------|-------------|-----------------|--------|
| Single obstacle direct path | (30, 20) | 1 building blocking LOS | 10 |
| Dense obstacle field | (50, 30) | Multiple buildings in path | 10 |
| Tight corridor | (40, 0) | Narrow street between buildings | 10 |
| Building corner | (25, 25) | Goal behind building corner | 10 |
| Dead-end recovery | (30, 0) | U-shaped obstacle requiring backtrack | 10 |

**Run each with both pure RL and hybrid controller.**

**Metrics**:
- All navigation metrics from Test 1/2
- `collision_point` (x, y, z) — where collision occurred (if any)
- `min_clearance` (m) — minimum distance to any obstacle during flight
- `avoidance_maneuvers` (count) — significant heading changes (> 30°)

---

### TEST 4 — Altitude Dynamics (Hybrid Only)

**Purpose**: Validate the reactive altitude controller's effectiveness for 3D urban navigation.

| Scenario | Description | Trials |
|----------|-------------|--------|
| Low building flyover | Goal behind 5m building | 10 |
| Tall building avoidance | Goal behind 30m building | 10 |
| Mixed height terrain | Buildings of varying height | 10 |
| Hover stability | Hold position for 30s | 5 |
| Altitude recovery | Force low altitude near obstacle | 5 |

**Metrics**:
- `altitude_profile` (time series) — full Z trajectory
- `climb_events` (count, timing, peak rate)
- `max_climb_rate` (m/s)
- `descent_smoothness` — std of descent velocity
- `altitude_overshoot` (m) — above needed clearance
- `time_in_state` — % time in CRUISE/CLIMBING/HOLDING/DESCENDING
- `building_clearance` (m) — min vertical distance to obstacle top

---

### TEST 5 — Domain Robustness

**Purpose**: Test resilience to environmental variations (weather, wind, sensor noise).

| Condition | Settings | Trials |
|-----------|----------|--------|
| Clear (baseline) | Default AirSim | 10 |
| Fog | AirSim fog density 0.3 | 10 |
| Heavy fog | Fog density 0.7 | 10 |
| Light wind | 3 m/s crosswind | 10 |
| Strong wind | 8 m/s gusty | 10 |
| LiDAR noise | Gaussian σ=0.1m added | 10 |
| LiDAR dropout | 20% random ray failures | 10 |

**Fixed scenario**: Medium forward (50, 0) with hybrid controller.

**Metrics**: Same as Test 2 + `position_error_rms` (m) from ideal path.

---

### TEST 6 — Multi-Waypoint Mission

**Purpose**: Test sustained navigation accuracy over long missions with multiple waypoints.

| Mission | Waypoints | Total Distance | Trials |
|---------|-----------|----------------|--------|
| Simple patrol | 5 waypoints, rectangular | ~200m | 5 |
| Complex patrol | 10 waypoints, varied directions | ~400m | 5 |
| Long mission | 15 waypoints, full city | ~600m | 5 |

**Run with both pure RL and hybrid.**

**Metrics**:
- `waypoints_reached` / `waypoints_total`
- `total_mission_time` (s)
- `total_path_length` (m)
- `per_leg_efficiency` (%) — per waypoint segment
- `cumulative_drift` (m) — error accumulation
- `rtb_success` (bool) — return to base
- `landing_accuracy` (m) — distance from home at landing

---

### TEST 7 — Computational Performance

**Purpose**: Measure overhead of the hybrid system vs pure RL.

| Metric | How Measured |
|--------|-------------|
| `inference_time_rl` (ms) | Time for `agent.plan()` call |
| `inference_time_astar` (ms) | Time for A* pathfinding |
| `grid_update_time` (ms) | Time to update occupancy grid from LiDAR |
| `total_loop_time` (ms) | Full control loop iteration |
| `memory_usage` (MB) | Process RSS during operation |
| `control_frequency` (Hz) | Actual achieved loop rate |

**Collect over 1000 loop iterations during a medium-distance flight.**

---

### TEST 8 — Ablation Study (Layer Contribution Analysis)

**Purpose**: Isolate the contribution of each layer in the 3-layer architecture. Proves *why* every component is necessary.

| Configuration | Global Path | Local Avoidance | Altitude Control | Label |
|---------------|:-----------:|:---------------:|:----------------:|-------|
| Pure RL | — | RL | — | `RL` |
| RL + Altitude | — | RL | Reactive Z | `RL+Alt` |
| A* + Altitude (no RL) | A* | PID/direct waypoint | Reactive Z | `A*+Alt` |
| Full Hybrid | A* | RL | Reactive Z | `A*+RL+Alt` |

**A\*+Alt controller (no RL)**: Navigate waypoint-to-waypoint using simple proportional velocity toward next A* waypoint (no learned obstacle avoidance). Altitude controller still reacts to LiDAR.

**Fixed scenarios** (run all 4 configs on each):

| Scenario | Goal (x, y) | Why Chosen |
|----------|-------------|------------|
| Open field | (50, 0) | Baseline — no obstacles |
| Single obstacle | (30, 20) | Tests local avoidance value |
| Dense obstacles | (50, 30) | Stresses local avoidance |
| Tight corridor | (40, 0) | Requires precise maneuvering |
| Long with buildings | (80, 0) | Tests global + local together |

**Trials**: 10 per scenario per configuration (4 × 5 × 10 = 200 runs).

**Metrics**: Same as Test 2 (all navigation + planner + altitude metrics).

**Expected outcome (hypothesis)**:

| Config | Open Field | With Obstacles | Insight |
|--------|-----------|----------------|---------|
| `RL` | ✅ Good | ⚠️ Gets stuck on far goals | RL alone can't plan around buildings beyond 4m LiDAR |
| `RL+Alt` | ✅ Good | ⚠️ Same + better Z | Altitude helps but doesn't fix global planning |
| `A*+Alt` | ✅ Good | ❌ Collides — no local dodge | A* gives path but can't react to close obstacles in time |
| `A*+RL+Alt` | ✅ Best | ✅ Best | All layers needed: plan globally, dodge locally, fly 3D |

**Report table structure**:
```
┌──────────────────┬────────┬────────┬─────────┬───────────┐
│ Metric           │ RL     │ RL+Alt │ A*+Alt  │ A*+RL+Alt │
├──────────────────┼────────┼────────┼─────────┼───────────┤
│ Success Rate     │        │        │         │           │
│ Collision Rate   │        │        │         │           │
│ Time to Goal     │        │        │         │           │
│ Path Efficiency  │        │        │         │           │
│ Min Obstacle Dist│        │        │         │           │
│ Altitude Std     │  N/A   │        │         │           │
└──────────────────┴────────┴────────┴─────────┴───────────┘
```

---

## Summary Metrics Table (for report)

| Metric | Category | Unit | How Presented |
|--------|----------|------|---------------|
| Success Rate | **Primary** | % | Mean with 95% CI |
| Collision Rate | **Primary** | % | Mean with 95% CI |
| Time to Goal | **Primary** | seconds | Mean ± σ |
| Path Efficiency | **Primary** | % | Mean ± σ |
| Min Obstacle Distance | Safety | meters | Min / Mean / Max |
| Close Calls (< 1.5m) | Safety | count | Mean per mission |
| Altitude Stability | 3D Control | meters (σ) | Std deviation |
| Replan Count | Planning | count | Mean per mission |
| Avg Velocity | Performance | m/s | Mean ± σ |
| Inference Latency | Compute | ms | Mean / P95 / Max |
| Control Frequency | Compute | Hz | Mean |

---

## Statistical Requirements

| Requirement | Target |
|-------------|--------|
| Trials per scenario | **10 minimum** (5 acceptable for complex missions) |
| Confidence intervals | **95% CI** on all primary metrics |
| Significance test | **Paired t-test** (pure RL vs hybrid, same goals) |
| Effect size | **Cohen's d** for key comparisons |
| Variance reporting | Standard deviation on all numeric metrics |

---

## Comparison Matrix (Report Table Structure)

```
┌──────────────────────┬────────────┬────────────┬────────────┐
│ Metric               │ Pure RL    │ Hybrid     │ Δ (p-value)│
├──────────────────────┼────────────┼────────────┼────────────┤
│ Success Rate         │ ??%        │ ??%        │            │
│ Collision Rate       │ ??%        │ ??%        │            │
│ Avg Time to Goal     │ ??s        │ ??s        │            │
│ Path Efficiency      │ ??%        │ ??%        │            │
│ Min Obstacle Dist    │ ??m        │ ??m        │            │
│ Close Calls/Mission  │ ??         │ ??         │            │
│ Altitude Stability σ │ N/A        │ ??m        │            │
│ Avg Velocity         │ ??m/s      │ ??m/s      │            │
│ Inference Latency    │ ??ms       │ ??ms       │            │
└──────────────────────┴────────────┴────────────┴────────────┘
```

---

## Test Execution Order

1. **TEST 1** — Pure RL Baseline (establishes the "before" numbers)
2. **TEST 2** — Hybrid Controller (establishes the "after" numbers)
3. **TEST 8** — Ablation Study (proves each layer's contribution — strongest evidence)
4. **TEST 3** — Obstacle Avoidance Comparison (safety story)
5. **TEST 4** — Altitude Dynamics (validates the novel Z controller)
6. **TEST 6** — Multi-Waypoint Mission (real-world applicability)
7. **TEST 5** — Domain Robustness (edge cases)
8. **TEST 7** — Computational Performance (overhead analysis)

---

## Pre-Test Checklist

- [ ] AirSim CityEnviron loaded and running
- [ ] NavRL checkpoint loads correctly (`navrl_checkpoint.pt`)
- [ ] Pure RL bridge works (`navrl_airsim_bridge.py`)
- [ ] Hybrid controller works (`navrl_city_planner.py`)
- [ ] Results directory exists and writable
- [ ] Investigate diagonal/negative-Y failures before formal testing
- [ ] Verify efficiency calculation (>100% issue)
- [ ] Confirm LiDAR frame transforms for all goal directions

---

## Known Issues to Resolve Before Testing

| Issue | Impact | Priority |
|-------|--------|----------|
| Diagonal goals (40,30) fail at 0% | Skews comparison unfairly | **HIGH** |
| Negative-Y goals (30,-25) fail at 0% | Same as above | **HIGH** |
| Efficiency > 100% on some trials | Makes metrics unreliable | **MEDIUM** |
| Only 2 trials in existing data | Statistically insufficient | **MEDIUM** |
