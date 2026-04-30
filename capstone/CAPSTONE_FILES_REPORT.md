# Capstone Files Report

Key files inside `capstone/` and their connected dependencies used by the Drone Command Center application.

---

## 1. Core Production Files (Used at Runtime)

These are the files actively executed when the application runs.

### `airsim_testing/airsim_auto_bridge.py` — **MAIN ENTRY POINT**

The primary bridge script launched by the Spring Boot backend as a managed subprocess.

| What it does |
|---|
| Connects to AirSim (port 41451), authenticates with the backend, streams telemetry at 1 Hz via REST, serves FPV camera frames on an HTTP server (port 8766), and runs the NavRL planner in a background thread. |

**Direct dependencies:**
| File | Role |
|---|---|
| `airsim_testing/command_center_bridge.py` | Auth, telemetry POST, drone auto-discovery |
| `airsim_testing/navrl_city_planner.py` | Global A* path planning + NavRL local navigation |

**Indirect dependencies (loaded through the chain):**
| File | Role |
|---|---|
| `airsim_testing/navrl_airsim_hybrid_controller.py` | Hybrid controller — NavRL model for X/Y + reactive altitude for Z |
| `airsim_testing/navrl_airsim_bridge.py` | Minimal/pure RL bridge — baseline controller (imported by hybrid) |
| `quick-demos/agent.py` | Loads the trained PPO policy and exposes `agent.plan()` |
| `quick-demos/ppo.py` | PPO network architecture (feature extractor, actor, critic) |
| `quick-demos/utils.py` | Helper classes: `ValueNorm`, `make_mlp`, `GAE`, `BetaActor`, `vec_to_world` |
| `quick-demos/ckpts/navrl_checkpoint.pt` | **The trained model weights** — this is the RL brain |

---

### `airsim_testing/command_center_bridge.py` — Backend Communication

| What it does |
|---|
| Authenticates as `navrl_bridge` user (JWT), auto-discovers the target drone ID from `/api/drones`, converts NED ↔ GPS coordinates, POSTs telemetry to the backend, listens for remote commands (SET_GOAL, STOP, PAUSE, RESUME, REPLAN) via WebSocket or HTTP polling fallback. |

**No further file dependencies** (standalone module using `requests` + `websocket-client`).

---

### `airsim_testing/navrl_city_planner.py` — Global Path Planner

| What it does |
|---|
| Builds a 2D occupancy grid from live LiDAR data, runs A* to find collision-free paths around buildings, generates intermediate waypoints, detects stuck conditions and triggers replans, manages a reactive altitude controller (climb when obstacles detected, descend when clear). |

**Direct dependencies:**
| File | Role |
|---|---|
| `navrl_airsim_hybrid_controller.py` | Underlying NavRL model execution + AirSim client control |

---

### `airsim_testing/navrl_airsim_hybrid_controller.py` — Hybrid Controller

| What it does |
|---|
| Runs the trained NavRL PPO model for X/Y velocity control while using an independent reactive P-controller for altitude (Z). Handles LiDAR processing (36 horizontal bins × 4 vertical bins), frame transformation to goal-relative coordinates, yaw alignment, and AirSim API calls. |

**Direct dependencies:**
| File | Role |
|---|---|
| `quick-demos/agent.py` | Model loader — `Agent.plan()` runs the policy forward pass |

**Critical training parameters preserved here:**
- `MAX_RAY_LENGTH = 4.0m`, `HRES_DEG = 10.0` (36 bins), `VFOV = [-10°, 0°, 10°, 20°]`
- `MAX_VELOCITY = 2.0 m/s`, `GOAL_THRESHOLD = 2.0m`

---

### `airsim_testing/navrl_airsim_bridge.py` — Pure RL Controller (Baseline)

| What it does |
|---|
| Minimal RL deployment — model controls X/Y/Z directly with no altitude state machine, no recovery logic, no smoothing. Used as the academic baseline for comparison and as the import root for the hybrid controller. |

---

## 2. Trained Model Files (quick-demos/)

These files define and load the neural network that drives navigation.

| File | Role |
|---|---|
| `quick-demos/agent.py` | `Agent` class — loads checkpoint, builds TensorDict observation, calls `policy.plan()` |
| `quick-demos/ppo.py` | `PPO` class — full network: LiDAR CNN feature extractor → MLP actor (BetaActor) → MLP critic |
| `quick-demos/utils.py` | `ValueNorm`, `make_mlp`, `GAE`, `IndependentBeta`, `BetaActor`, `vec_to_world` — building blocks for the PPO architecture |
| `quick-demos/ckpts/navrl_checkpoint.pt` | **Trained weights** — the actual model checkpoint loaded at runtime |
| `quick-demos/env.py` | Training environment definition (obstacles, goals) — **NOT used at runtime**, only used during training |

---

## 3. Optional / Secondary Files

### `airsim_testing/mavlink_qgc_bridge.py` — QGroundControl Integration

Translates AirSim telemetry into MAVLink v2 UDP messages so QGroundControl can display the drone. Optional — only needed if using QGC alongside the Flutter app.

### `airsim_testing/simulate_airsim_feed.py` — Fake Telemetry Generator

Sends simulated drone telemetry through the full pipeline (Bridge → REST API → Backend → DB → WebSocket → Frontend) **without needing AirSim running**. Useful for testing the app when AirSim is unavailable.

### `airsim_testing/diagnose_model.py` — Model Diagnostic Tool

Tests the NavRL model in isolation with synthetic inputs (clear path, obstacle ahead, goal at angle) to verify the policy produces expected velocity outputs.

### `airsim_testing/navrl_city_planner_old.py` — Previous Planner Version

Earlier version of the city planner. Kept for reference. Not used by any active code.

### `airsim_testing/navrl_utils.py` — Empty

Currently empty placeholder file.

---

## 4. Test & Validation Files

### Standalone Tests

| File | Purpose |
|---|---|
| `airsim_testing/integration_test.py` | Full pipeline test (Auth → CRUD → Telemetry → NavRL commands) — no AirSim needed |
| `airsim_testing/real_airsim_test.py` | Live AirSim test (monitor/hover/navigate modes) with backend telemetry push |
| `airsim_testing/test_city_planner.py` | Compares city planner vs pure hybrid controller in AirSim |
| `airsim_testing/test_mission_mavlink.py` | Mission API + MAVLink bridge integration test |
| `airsim_testing/ws_test.py` | Quick WebSocket broadcast verification |

### Test Suite (`airsim_testing/tests/`)

| File | Purpose |
|---|---|
| `tests/run_all_tests.py` | Master test runner with comparison dashboard |
| `tests/run_hybrid_tests.py` | Runs tests specifically for the hybrid controller |
| `tests/test_simple_navigation.py` | Basic point-to-point navigation |
| `tests/test_obstacle_avoidance.py` | Obstacle avoidance scenarios |
| `tests/test_altitude_dynamics.py` | Altitude control behavior |
| `tests/test_lidar.py` | LiDAR processing validation |
| `tests/test_mission_rtb.py` | Mission execution + return-to-base |
| `tests/test_domain_randomization.py` | Domain randomization robustness |
| `tests/test_config.py` | Shared test configuration |
| `tests/dashboard.py` | Results visualization dashboard |

---

## 5. Dependency Graph

```
Backend (Spring Boot)
  │ launches subprocess
  ▼
airsim_auto_bridge.py ─────────────────────────────┐
  ├── command_center_bridge.py  (auth + telemetry)  │
  └── navrl_city_planner.py     (A* + orchestrator) │
        └── navrl_airsim_hybrid_controller.py       │
              └── navrl_airsim_bridge.py (baseline)  │
                    └── quick-demos/agent.py         │
                          ├── quick-demos/ppo.py     │
                          ├── quick-demos/utils.py   │
                          └── quick-demos/ckpts/     │
                                navrl_checkpoint.pt  │
                                                     │
AirSim Simulator (port 41451) ◄────────────────────┘
  │                                     │
  │ LiDAR + pose + camera              │ FPV (port 8766)
  ▼                                     ▼
NavRL Model ────► velocities ────► AirSim movement
                                        │
                                   telemetry POST
                                        ▼
                                Backend REST API
                                        │
                                   WebSocket broadcast
                                        ▼
                                Flutter Frontend
```

---

## 6. Files to Focus On

**Must-have for the application to function:**

1. `airsim_testing/airsim_auto_bridge.py` — entry point
2. `airsim_testing/command_center_bridge.py` — backend auth & telemetry
3. `airsim_testing/navrl_city_planner.py` — global planner
4. `airsim_testing/navrl_airsim_hybrid_controller.py` — hybrid controller
5. `airsim_testing/navrl_airsim_bridge.py` — base controller (imported by hybrid)
6. `quick-demos/agent.py` — model loader
7. `quick-demos/ppo.py` — network architecture
8. `quick-demos/utils.py` — network building blocks
9. `quick-demos/ckpts/navrl_checkpoint.pt` — trained weights

**Useful but not required for core operation:**

- `simulate_airsim_feed.py` — testing without AirSim
- `integration_test.py` — pipeline validation
- `diagnose_model.py` — debugging model outputs
- `mavlink_qgc_bridge.py` — QGroundControl support
