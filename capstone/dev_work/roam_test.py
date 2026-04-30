"""
Roam Test — Continuous Multi-Goal Navigation & Capstone Evaluation
===================================================================
Primary evaluation script for the capstone project.
Drone gets a sequence of goals covering the whole map.
NO respawn between goals — it continues from where it ended.

Supports multi-run execution for statistical validity (mean ± std).

Collected Metrics:
  Core:     success_rate, collision_rate_per_dist, collision_rate_per_goal,
            path_efficiency, avg_time_to_goal, time_efficiency
  Safety:   avg_min_obstacle, close_calls, recovery_score
  Altitude: alt_mean, alt_std, alt_min, alt_max
  Planner:  replans, proactive_replans, rl_fallback, obstacles_mapped

Usage:
    python roam_test.py --controller hybrid --runs 5
    python roam_test.py --controller pure_rl --runs 10
    python roam_test.py --controller both --runs 5
    python roam_test.py --suite domain_randomization --controller both --runs 5
    python roam_test.py --suite sensor_noise --controller both --runs 3
    python roam_test.py --suite imu_noise --controller both --runs 3
    python roam_test.py --suite ablation --runs 3
"""

import airsim
import numpy as np
import pandas as pd
import torch
import time
import json
import argparse
import sys
import os
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'navrl_model'))

from navrl_utils import MAX_RAY_LENGTH, MAX_VELOCITY, DEFAULT_FLIGHT_HEIGHT, GOAL_THRESHOLD, CONTROL_FREQ

# ============================================================================
# GOALS — spread across the entire map, behind/on top of buildings
# ============================================================================
# Building reference:
#   BG_Building      (0.3, 29)      — 29m north
#   Building_C       (0 to -20, -78 to -105) — south cluster
#   OrnateWall       (50-100, -45 to -87)    — SE compound
#   Building_9       (97, 26)       — NE
#   Apartment        (93, -69)      — ESE
#   Building_4       (-95, 67)      — NW
#   Apartment towers (57,112) (-60,119) — far north

ROAM_GOALS = [
    # 1. Easy warmup — open field east
    {"name": "open_east",               "goal": [40, 0]},
    # 2. Behind north building (building at y=29, goal past it)
    {"name": "behind_north_bldg",       "goal": [0, 55]},
    # 3. Swing west — open area
    {"name": "west_open",               "goal": [-50, 30]},
    # 4. Northwest building area
    {"name": "near_bldg4_NW",           "goal": [-90, 65]},
    # 5. Back southeast through city center
    {"name": "SE_wall_compound",        "goal": [75, -60]},
    # 6. South building cluster — dense
    {"name": "south_cluster",           "goal": [-10, -95]},
    # 7. East to apartment building
    {"name": "apartment_ESE",           "goal": [90, -70]},
    # 8. Northeast — Building_9
    {"name": "building9_NE",            "goal": [97, 26]},
    # 9. Far north tower
    {"name": "north_tower",             "goal": [55, 110]},
    # 10. Far NW tower
    {"name": "NW_tower",                "goal": [-60, 115]},
    # 11. Back to center — right on top of north building
    {"name": "on_north_bldg",           "goal": [0, 29]},
    # 12. Home — return to origin
    {"name": "return_home",             "goal": [0, 0]},
]

STUCK_SPEED_THRESHOLD = 0.3   # m/s — below this for stuck_time = stuck
STUCK_TIME_LIMIT = 8.0        # seconds of low speed before declaring stuck
DEFAULT_ALTITUDE = -3.0
CLOSE_CALL_THRESHOLD = 1.5    # m — obstacle distance counted as a close call

LIDAR_NOISE_CONDITIONS = [
    {"name": "clean", "noise_std": 0.0, "dropout": 0.0},
    {"name": "lidar_noise_light", "noise_std": 0.05, "dropout": 0.0},
    {"name": "lidar_noise_heavy", "noise_std": 0.10, "dropout": 0.0},
    {"name": "lidar_dropout", "noise_std": 0.0, "dropout": 0.20},
]

IMU_NOISE_CONDITIONS = [
    {"name": "clean", "position_std": 0.0, "velocity_std": 0.0, "yaw_std_deg": 0.0, "altitude_std": 0.0},
    {"name": "imu_noise_light", "position_std": 0.05, "velocity_std": 0.05, "yaw_std_deg": 1.0, "altitude_std": 0.03},
    {"name": "imu_noise_medium", "position_std": 0.10, "velocity_std": 0.10, "yaw_std_deg": 2.5, "altitude_std": 0.06},
    {"name": "imu_noise_heavy", "position_std": 0.20, "velocity_std": 0.15, "yaw_std_deg": 5.0, "altitude_std": 0.10},
]

ABLATION_CONFIGS = [
    # Build-up order: each entry adds one component so the contribution of each
    # can be isolated in the capstone analysis.
    #
    #  1. PureRL          — RL policy only, no altitude assistance, no global planner
    #  2. RL+FixedAlt     — RL policy + static altitude hold (no obstacle-reactive altitude)
    #  3. RL+AltSM        — RL policy + reactive altitude state machine (no A* planner)
    #  4. PControl+AltSM  — P-controller + reactive altitude SM (shows RL policy's contribution)
    #  5. NavRL+CityPlanner — full system: RL + reactive altitude + A* global planner
    {"label": "PureRL",             "controller_type": "pure_rl"},
    {"label": "RL+FixedAlt",        "controller_type": "rl_fixed_alt"},
    {"label": "RL+AltSM",           "controller_type": "rl_alt"},
    {"label": "PControl+AltSM",     "controller_type": "p_control_alt"},
    {"label": "NavRL+CityPlanner",  "controller_type": "hybrid"},
]


def _controller_label(controller_type: str) -> str:
    labels = {
        "pure_rl": "Pure RL",
        "hybrid": "Hybrid Planner",
        "rl_fixed_alt": "RL+FixedAlt",
        "rl_alt": "RL+AltSM",
        "p_control_alt": "PControl+AltSM",
    }
    return labels.get(controller_type, controller_type)


def _proportional_waypoint_follow(position: np.ndarray, goal: np.ndarray,
                                  altitude: float, current_z: float) -> np.ndarray:
    """Simple XY proportional waypoint follower for ablation testing."""
    dx = goal[0] - position[0]
    dy = goal[1] - position[1]
    dist = np.sqrt(dx**2 + dy**2)

    if dist < 0.5:
        return np.array([0.0, 0.0, 0.0])

    speed = min(MAX_VELOCITY, dist * 0.3)
    vx = (dx / dist) * speed
    vy = (dy / dist) * speed
    alt_error = altitude - current_z
    vz = float(np.clip(alt_error * 0.5, -1.5, 1.5))
    return np.array([vx, vy, vz])


def _apply_environment(bridge, weather=None, wind=None):
    """Apply weather and wind conditions to AirSim for a robustness run."""
    if weather:
        bridge.client.simEnableWeather(True)
        bridge.client.simSetWeatherParameter(airsim.WeatherParameter.Fog, weather["fog"])
        bridge.client.simSetWeatherParameter(airsim.WeatherParameter.Rain, weather["rain"])

    if wind:
        direction = np.array(wind["direction"], dtype=float)
        norm = np.linalg.norm(direction)
        if norm > 0:
            direction = direction / norm
        wind_vec = direction * wind["speed"]
        bridge.client.simSetWind(airsim.Vector3r(float(wind_vec[0]), float(wind_vec[1]), float(wind_vec[2])))


def _reset_environment(bridge, weather=None, wind=None):
    """Reset weather and wind back to clean defaults."""
    if weather:
        try:
            bridge.client.simEnableWeather(False)
        except Exception:
            pass
    if wind:
        try:
            bridge.client.simSetWind(airsim.Vector3r(0, 0, 0))
        except Exception:
            pass


def _apply_imu_noise(state: tuple, imu_noise: Optional[dict]) -> tuple:
    """Inject IMU-like noise into the state returned to the controller."""
    if not imu_noise:
        return state

    position, velocity, yaw, z, orientation = state
    noisy_position = position.copy()
    noisy_velocity = velocity.copy()
    noisy_yaw = yaw
    noisy_z = z

    if imu_noise.get("position_std", 0) > 0:
        noisy_position = noisy_position + np.random.normal(0, imu_noise["position_std"], size=noisy_position.shape)
    if imu_noise.get("velocity_std", 0) > 0:
        noisy_velocity = noisy_velocity + np.random.normal(0, imu_noise["velocity_std"], size=noisy_velocity.shape)
    if imu_noise.get("yaw_std_deg", 0) > 0:
        noisy_yaw = noisy_yaw + float(np.deg2rad(np.random.normal(0, imu_noise["yaw_std_deg"])))
    if imu_noise.get("altitude_std", 0) > 0:
        noisy_z = noisy_z + float(np.random.normal(0, imu_noise["altitude_std"]))

    return noisy_position, noisy_velocity, noisy_yaw, noisy_z, orientation


def _install_perturbation_wrappers(bridge, lidar_noise=None, imu_noise=None):
    """Wrap bridge methods so noise applies to both manual and planner-driven runs."""
    if hasattr(bridge, "process_lidar"):
        original_process_lidar = bridge.process_lidar

        def noisy_process_lidar(*args, **kwargs):
            lidar_obs, min_obs = original_process_lidar(*args, **kwargs)
            if lidar_noise and (lidar_noise.get("noise_std", 0) > 0 or lidar_noise.get("dropout", 0) > 0):
                lidar_np = lidar_obs.detach().cpu().numpy()
                if lidar_noise.get("noise_std", 0) > 0:
                    noise = np.random.normal(0, lidar_noise["noise_std"], lidar_np.shape)
                    lidar_np = np.clip(lidar_np + noise, 0, MAX_RAY_LENGTH)
                if lidar_noise.get("dropout", 0) > 0:
                    mask = np.random.random(lidar_np.shape) < lidar_noise["dropout"]
                    lidar_np[mask] = 0.0
                lidar_obs = torch.tensor(lidar_np, dtype=torch.float32, device=lidar_obs.device)
            return lidar_obs, min_obs

        bridge.process_lidar = noisy_process_lidar

    if hasattr(bridge, "get_state"):
        original_get_state = bridge.get_state

        def noisy_get_state():
            return _apply_imu_noise(original_get_state(), imu_noise)

        bridge.get_state = noisy_get_state

    if hasattr(bridge, "get_drone_state"):
        original_get_drone_state = bridge.get_drone_state

        def noisy_get_drone_state():
            return _apply_imu_noise(original_get_drone_state(), imu_noise)

        bridge.get_drone_state = noisy_get_drone_state


def _bundle_runs(runs: list) -> dict:
    """Return a consistent run bundle for suite exports."""
    return {
        "n_runs": len(runs),
        "stats": compute_multi_run_stats(runs),
        "runs": runs,
    }


def _format_optional_metric(value, precision: int = 2, suffix: str = "") -> str:
    """Format optional numeric metrics for console output."""
    if value is None:
        return "N/A"
    return f"{value:.{precision}f}{suffix}"


def _format_optional_table_value(value, width: int = 12, precision: int = 2) -> str:
    """Format optional numeric metrics for aligned comparison tables."""
    if value is None:
        return f"{'N/A':>{width}s}"
    return f"{value:>{width}.{precision}f}"


def _compute_path_efficiency(success: bool, start_dist: float, path_length: float) -> float:
    """Return path efficiency only for successful legs with meaningful travel."""
    if not success or start_dist <= 0.1 or path_length <= 0.1:
        return 0.0
    return (start_dist / path_length) * 100.0


def _sample_domain_randomization_conditions(num_runs: int, seed: int) -> list:
    """Sample reproducible weather + wind conditions for domain randomization."""
    rng = np.random.default_rng(seed)
    conditions = []
    for idx in range(num_runs):
        angle = float(rng.uniform(0.0, 2.0 * np.pi))
        conditions.append({
            "name": f"randomized_{idx + 1:02d}",
            "weather": {
                "fog": round(float(rng.uniform(0.0, 0.7)), 3),
                "rain": round(float(rng.uniform(0.0, 0.4)), 3),
            },
            "wind": {
                "speed": round(float(rng.uniform(0.0, 8.0)), 3),
                "direction": [round(float(np.cos(angle)), 3), round(float(np.sin(angle)), 3), 0.0],
            },
        })
    return conditions


def run_roam(controller_type: str, goals: list, timeout_per_goal: float,
             weather=None, wind=None, lidar_noise=None, imu_noise=None):
    """Run all goals sequentially, no respawn between goals."""

    if controller_type == "pure_rl":
        from navrl_airsim_bridge import NavRLBridge
        bridge = NavRLBridge()
    elif controller_type == "hybrid":
        from navrl_city_planner import NavRLCityPlanner
        planner = NavRLCityPlanner(verbose=False)
        bridge = planner.bridge  # underlying NavRLAirSimBridge
    elif controller_type in ("rl_alt", "rl_fixed_alt", "p_control_alt"):
        from navrl_airsim_hybrid_controller import NavRLAirSimBridge
        bridge = NavRLAirSimBridge()
    else:
        raise ValueError(f"Unknown controller type: {controller_type}")

    _apply_environment(bridge, weather=weather, wind=wind)
    _install_perturbation_wrappers(bridge, lidar_noise=lidar_noise, imu_noise=imu_noise)
    get_state = bridge.get_state if hasattr(bridge, "get_state") and controller_type == "pure_rl" else bridge.get_drone_state

    total_collisions = 0
    total_goals = len(goals)
    results = []
    next_leg_starts_from_reset = False

    print(f"\n{'='*70}")
    print(f"  ROAM TEST -- {_controller_label(controller_type).upper()}")
    print(f"  Goals: {total_goals} | Timeout/goal: {timeout_per_goal}s")
    print(f"{'='*70}\n")

    if controller_type != "hybrid":
        # Single reset + takeoff at the start
        bridge.reset_drone()
        bridge.client.takeoffAsync().join()
        bridge.client.moveToZAsync(DEFAULT_ALTITUDE, 2).join()
        time.sleep(0.5)

    for i, wp in enumerate(goals):
        name = wp["name"]
        goal = np.array(wp["goal"], dtype=float)
        post_collision_reset = next_leg_starts_from_reset
        next_leg_starts_from_reset = False

        position, velocity, yaw, z, orientation = get_state()
        start_pos = position.copy()
        start_dist = np.linalg.norm(goal[:2] - position[:2])

        print(f"  [{i+1}/{total_goals}] {name:25s} -> [{goal[0]:6.0f}, {goal[1]:6.0f}]  "
              f"(from [{position[0]:5.0f},{position[1]:5.0f}], dist={start_dist:.0f}m)")

        if controller_type == "hybrid":
            # ---- City Planner handles the entire navigation ----
            nav_result = planner.navigate_to_goal(
                goal=goal[:2],
                timeout=timeout_per_goal,
                min_altitude=abs(DEFAULT_ALTITUDE),
            )
            success = nav_result.get('success', False)
            collision = nav_result.get('collision', False)
            path_length = nav_result.get('path_length', 0.0)
            total_time = nav_result.get('time', 0.0)
            min_obs_ever = nav_result.get('closest_obstacle', MAX_RAY_LENGTH)
            close_calls = nav_result.get('close_calls', 0)
            timed_out = not success and not collision
            stuck = False

            efficiency = _compute_path_efficiency(success, start_dist, path_length)

            if collision:
                total_collisions += 1
                # Force the planner to hard-reset on the next leg so the drone
                # is not left crashed against the same wall (state pollution fix).
                planner._first_nav = True
                next_leg_starts_from_reset = True

            if success:
                tag = "[OK] SUCCESS"
            elif collision:
                tag = "[!!] COLLISION"
            else:
                tag = "[>>] TIMEOUT"

            print(f"    {tag} | {total_time:.1f}s | path:{path_length:.0f}m | "
                  f"eff:{efficiency:.0f}% | minObs:{min_obs_ever:.2f}m | "
                  f"replans:{nav_result.get('replans', 0)}")

            # Capture end position for this leg
            end_position, _, _, _, _ = get_state()

            results.append({
                "name": name,
                "goal": goal.tolist(),
                "start_pos": [round(start_pos[0], 1), round(start_pos[1], 1)],
                "end_pos": [round(end_position[0], 1), round(end_position[1], 1)],
                "success": success,
                "collision": collision,
                "stuck": stuck,
                "timeout": timed_out,
                "time": round(total_time, 2),
                "path_length": round(path_length, 2),
                "start_dist": round(start_dist, 2),
                "post_collision_reset": post_collision_reset,
                "efficiency": round(efficiency, 1),
                "min_obstacle_dist": round(min_obs_ever, 3),
                "close_calls": close_calls,
                "steps": 0,
                "replans": nav_result.get('replans', 0),
                "proactive_replans": nav_result.get('proactive_replans', 0),
                "rl_fallback": nav_result.get('rl_fallback', False),
                "obstacles_mapped": nav_result.get('obstacles_mapped', 0),
                "altitude_min": nav_result.get('altitude_min'),
                "altitude_max": nav_result.get('altitude_max'),
                "altitude_mean": nav_result.get('altitude_avg'),
                "altitude_std": nav_result.get('altitude_std'),
                "altitude_climbs": nav_result.get('altitude_climbs', 0),
            })

            time.sleep(1.0)
            continue

        # ---- Manual controller loop (Pure RL + ablations) ----
        # --- reset altitude state for consecutive legs (no position reset) ---
        if hasattr(bridge, 'prepare_for_flight'):
            bridge.prepare_for_flight()

        success = False
        collision = False
        timed_out = False
        stuck = False
        stuck_timer = 0.0
        path_length = 0.0
        prev_pos = position.copy()
        min_obs_ever = MAX_RAY_LENGTH
        close_calls = 0
        step_count = 0
        altitude_readings = []
        # Rolling position buffer for chattering detection:
        # RL policies can oscillate back-and-forth at non-zero speed ("chattering")
        # while making zero net progress.  Speed-only stuck detection misses this.
        # Buffer stores the last 5 seconds of (x,y) positions at CONTROL_FREQ rate.
        _pos_history: deque = deque(maxlen=int(5 * CONTROL_FREQ))  # 100 steps @ 20 Hz

        # Prime last_sim_time_ns BEFORE the control loop to prevent stale collision
        # timestamps from the previous leg firing on the first iteration.
        # check_collision() uses last_sim_time_ns which is only updated by get_state();
        # without this call it still holds the timestamp from the prior leg's final step.
        _ = get_state()

        goal_start = time.time()
        sim_start_ns = bridge.last_sim_time_ns

        while True:
            loop_start = time.time()

            # --- collision check ---
            if bridge.check_collision():
                collision = True
                total_collisions += 1
                print(f"    [COLLISION] at step {step_count}")
                break

            position, velocity, yaw, z, orientation = get_state()
            altitude_readings.append(z)

            # --- sim-clock timeout ---
            sim_elapsed = (bridge.last_sim_time_ns - sim_start_ns) / 1e9
            if sim_elapsed > timeout_per_goal:
                timed_out = True
                break

            dist = np.linalg.norm(goal[:2] - position[:2])
            if dist < GOAL_THRESHOLD:
                success = True
                break

            # --- stuck detection ---
            speed = np.linalg.norm(velocity[:2])
            _pos_history.append(position[:2].copy())
            if speed < STUCK_SPEED_THRESHOLD and step_count > 20:
                stuck_timer += 1.0 / CONTROL_FREQ
            else:
                stuck_timer = 0.0
            # Chattering check: high speed but zero net displacement over 5 s
            if (len(_pos_history) == _pos_history.maxlen and
                    np.linalg.norm(position[:2] - _pos_history[0]) < 0.5):
                stuck_timer = max(stuck_timer, STUCK_TIME_LIMIT + 0.1)  # Force trip
            if stuck_timer > STUCK_TIME_LIMIT:
                stuck = True
                break

            # --- path length ---
            seg = np.linalg.norm(position - prev_pos)
            path_length += seg
            prev_pos = position.copy()

            # --- lidar + action ---
            if controller_type == "pure_rl":
                lidar_obs, min_obs = bridge.process_lidar(position, goal, orientation)
            else:
                lidar_obs, min_obs = bridge.process_lidar(position, yaw, goal, orientation=orientation)

            min_obs_ever = min(min_obs_ever, min_obs)
            if min_obs < CLOSE_CALL_THRESHOLD:
                close_calls += 1

            goal_3d = np.array([goal[0], goal[1], DEFAULT_ALTITUDE])

            if controller_type == "pure_rl":
                vel_cmd = bridge.compute_action(position, velocity, goal_3d, lidar_obs, z)
                vel_x, vel_y, vel_z = vel_cmd[0], vel_cmd[1], vel_cmd[2]
            elif controller_type == "rl_fixed_alt":
                vel_cmd = bridge.compute_action(position, velocity, goal_3d, lidar_obs,
                                                current_z=z, min_obstacle_dist=min_obs)
                vel_x, vel_y = vel_cmd[0], vel_cmd[1]
                alt_error = DEFAULT_ALTITUDE - z
                vel_z = float(np.clip(alt_error * 0.5, -1.5, 1.5))
            elif controller_type == "rl_alt":
                vel_cmd = bridge.compute_action(position, velocity, goal_3d, lidar_obs,
                                                current_z=z, min_obstacle_dist=min_obs)
                vel_x, vel_y = vel_cmd[0], vel_cmd[1]
                vel_z = bridge.compute_dynamic_altitude(lidar_obs, z, DEFAULT_ALTITUDE, min_obs)
            elif controller_type == "p_control_alt":
                vel_cmd = _proportional_waypoint_follow(position, goal, DEFAULT_ALTITUDE, z)
                vel_x, vel_y = vel_cmd[0], vel_cmd[1]
                vel_z = bridge.compute_dynamic_altitude(lidar_obs, z, DEFAULT_ALTITUDE, min_obs)
            else:
                raise ValueError(f"Unsupported manual controller type: {controller_type}")

            goal_dir = goal[:2] - position
            yaw_deg = float(np.degrees(np.arctan2(goal_dir[1], goal_dir[0])))

            bridge.client.moveByVelocityAsync(
                float(vel_x), float(vel_y), float(vel_z),
                duration=1.0 / CONTROL_FREQ,  # Match sleep period exactly; 1.5x caused 33% command overlap
                drivetrain=airsim.DrivetrainType.MaxDegreeOfFreedom,
                yaw_mode=airsim.YawMode(is_rate=False, yaw_or_rate=yaw_deg)
            )

            step_count += 1

            # progress every ~2s
            if step_count % 40 == 0:
                status = "R" if min_obs < CLOSE_CALL_THRESHOLD else ("Y" if min_obs < 2.5 else "G")
                print(f"\r    [{status}] D:{dist:5.1f}m Alt:{-z:4.1f}m Obs:{min_obs:.1f}m "
                      f"t:{sim_elapsed:.0f}s spd:{speed:.1f}", end="")

            time.sleep(1.0 / CONTROL_FREQ)

        # stop
        try:
            bridge.client.moveByVelocityAsync(0, 0, 0, 1).join()
        except Exception:
            pass

        total_time = (bridge.last_sim_time_ns - sim_start_ns) / 1e9
        efficiency = _compute_path_efficiency(success, start_dist, path_length)
        alt_np = np.array(altitude_readings) if altitude_readings else np.array([DEFAULT_ALTITUDE])

        if success:
            tag = "[OK] SUCCESS"
        elif collision:
            tag = "[!!] COLLISION"
        elif stuck:
            tag = "[==] STUCK"
        else:
            tag = "[>>] TIMEOUT"

        print(f"\n    {tag} | {total_time:.1f}s | path:{path_length:.0f}m | "
              f"eff:{efficiency:.0f}% | minObs:{min_obs_ever:.2f}m | close:{close_calls}")

        # Capture end position for this leg
        end_position, _, _, _, _ = get_state()

        results.append({
            "name": name,
            "goal": goal.tolist(),
            "start_pos": [round(start_pos[0], 1), round(start_pos[1], 1)],
            "end_pos": [round(end_position[0], 1), round(end_position[1], 1)],
            "success": success,
            "collision": collision,
            "stuck": stuck,
            "timeout": timed_out,
            "time": round(total_time, 2),
            "path_length": round(path_length, 2),
            "start_dist": round(start_dist, 2),
            "post_collision_reset": post_collision_reset,
            "efficiency": round(efficiency, 1),
            "min_obstacle_dist": round(min_obs_ever, 3),
            "close_calls": close_calls,
            "steps": step_count,
            "altitude_min": round(float(-np.max(alt_np)), 2),
            "altitude_max": round(float(-np.min(alt_np)), 2),
            "altitude_mean": round(float(-np.mean(alt_np)), 2),
            "altitude_std": round(float(np.std(alt_np)), 3),
        })

        # If collision, we need to recover — re-enable API, re-arm, hover
        if collision:
            print("    -> Recovering from collision...")
            try:
                bridge.reset_drone()  # reset() + physics settle + enableApiControl + armDisarm
                bridge.client.takeoffAsync().join()
                bridge.client.moveToZAsync(DEFAULT_ALTITUDE, 2).join()
                time.sleep(0.5)
                next_leg_starts_from_reset = True
            except Exception as e:
                print(f"    [WARN] Recovery failed: {e}")

        time.sleep(1.0)  # brief pause between goals

    # ── Compute All Metrics ──
    successes = sum(1 for r in results if r["success"])
    collisions = sum(1 for r in results if r["collision"])
    stucks = sum(1 for r in results if r["stuck"])
    timeouts = sum(1 for r in results if r["timeout"])
    total_path = sum(r["path_length"] for r in results)
    total_time = sum(r["time"] for r in results)
    total_close = sum(r["close_calls"] for r in results)
    post_collision_reset_legs = sum(1 for r in results if r.get("post_collision_reset", False))
    valid_results = [r for r in results if not r.get("post_collision_reset", False)]
    valid_successes = [r for r in valid_results if r["success"]]

    # Core metrics
    success_rate = successes / total_goals * 100
    collision_rate_per_dist = collisions / max(total_path, 0.1)  # collisions/meter
    collision_rate_per_goal = collisions / total_goals
    efficiency_values = [r["efficiency"] for r in valid_successes]
    avg_eff = float(np.mean(efficiency_values)) if efficiency_values else None
    successful_times = [r["time"] for r in valid_successes]
    avg_time_to_goal = float(np.mean(successful_times)) if successful_times else None
    valid_total_path = sum(r["path_length"] for r in valid_results)
    valid_total_time = sum(r["time"] for r in valid_results)
    if valid_results and valid_total_time > 0:
        time_efficiency = valid_total_path / valid_total_time
    else:
        time_efficiency = None

    # Safety metrics
    avg_min_obs = float(np.mean([r["min_obstacle_dist"] for r in results]))
    # Recovery score: % of close calls that did NOT end in collision
    # A close call on a leg that ended in collision = failed recovery
    close_calls_on_collision_legs = sum(r["close_calls"] for r in results if r["collision"])
    recovery_score = ((total_close - close_calls_on_collision_legs) / max(total_close, 1)) * 100

    # Altitude metrics (aggregate across all legs)
    all_alt_means = [r["altitude_mean"] for r in results if r.get("altitude_mean") is not None]
    alt_mean = float(np.mean(all_alt_means)) if all_alt_means else 0.0
    alt_min_values = [r["altitude_min"] for r in results if r.get("altitude_min") is not None]
    alt_max_values = [r["altitude_max"] for r in results if r.get("altitude_max") is not None]
    alt_min = min(alt_min_values) if alt_min_values else 0.0
    alt_max = max(alt_max_values) if alt_max_values else 0.0
    all_alt_stds = [r["altitude_std"] for r in results if r.get("altitude_std") is not None]
    alt_std = float(np.mean(all_alt_stds)) if all_alt_stds else 0.0

    print(f"\n{'='*70}")
    print(f"  ROAM SUMMARY — {controller_type.upper()}")
    print(f"{'='*70}")
    print(f"  Success Rate      : {successes}/{total_goals} ({success_rate:.0f}%)")
    print(f"  Collisions        : {collisions}  "
          f"({collision_rate_per_dist*1000:.2f}/km, {collision_rate_per_goal:.2f}/goal)")
    print(f"  Stuck             : {stucks}")
    print(f"  Timeouts          : {timeouts}")
    print(f"  Total path        : {total_path:.0f}m")
    print(f"  Total time        : {total_time:.0f}s")
    print(f"  Reset-origin legs : {post_collision_reset_legs}")
    print(f"  Avg efficiency    : {_format_optional_metric(avg_eff, precision=0, suffix='%')} "
          f"(successful, non-reset legs)")
    print(f"  Avg time/goal     : {_format_optional_metric(avg_time_to_goal, precision=1, suffix='s')} "
          f"(successful, non-reset legs)")
    print(f"  Time efficiency   : {_format_optional_metric(time_efficiency, precision=2, suffix=' m/s')} "
          f"(non-reset legs)")
    print(f"  Avg min obstacle  : {avg_min_obs:.2f}m")
    print(f"  Close calls       : {total_close} (obs < {CLOSE_CALL_THRESHOLD:.1f}m)")
    print(f"  Recovery score    : {recovery_score:.0f}%")
    print(f"  Altitude          : mean={alt_mean:.1f}m, min={alt_min:.1f}m, "
          f"max={alt_max:.1f}m, std={alt_std:.2f}m")
    print(f"{'='*70}")

    # Per-leg coordinate table for cross-referencing with environment map
    print(f"  {'Leg':<22s} {'Status':>6s}  {'Start':>14s}  {'End':>14s}  {'Goal':>14s}  {'Dist':>5s}")
    print(f"  {'-'*82}")
    for r in results:
        s = "OK" if r["success"] else ("!!" if r["collision"] else ("==" if r["stuck"] else ">>"))
        name_label = f"{r['name']}*" if r.get("post_collision_reset", False) else r["name"]
        sp = r.get("start_pos", [0, 0])
        ep = r.get("end_pos", [0, 0])
        g = r.get("goal", [0, 0])
        print(f"  {name_label:<22.22s} [{s:>2s}]  ({sp[0]:6.0f},{sp[1]:6.0f})  "
              f"({ep[0]:6.0f},{ep[1]:6.0f})  ({g[0]:6.0f},{g[1]:6.0f})  {r['start_dist']:5.0f}m")
    if post_collision_reset_legs:
        print("  * reset-origin leg after collision recovery; excluded from efficiency/time aggregates")
    print(f"{'='*70}\n")

    metrics = {
        "controller": controller_type,
        "controller_label": _controller_label(controller_type),
        "goals_total": total_goals,
        # Core
        "successes": successes,
        "success_rate": round(success_rate, 1),
        "collisions": collisions,
        "collision_rate_per_km": round(collision_rate_per_dist * 1000, 3),
        "collision_rate_per_goal": round(collision_rate_per_goal, 3),
        "stucks": stucks,
        "timeouts": timeouts,
        "total_path_m": round(total_path, 1),
        "total_time_s": round(total_time, 1),
        "avg_efficiency_pct": round(avg_eff, 1) if avg_eff is not None else None,
        "avg_time_to_goal_s": round(avg_time_to_goal, 1) if avg_time_to_goal is not None else None,
        "time_efficiency_mps": round(time_efficiency, 3) if time_efficiency is not None else None,
        "post_collision_reset_legs": post_collision_reset_legs,
        # Safety
        "avg_min_obstacle_m": round(avg_min_obs, 3),
        "total_close_calls": total_close,
        "recovery_score_pct": round(recovery_score, 1),
        # Altitude
        "altitude_mean_m": round(alt_mean, 2),
        "altitude_min_m": round(alt_min, 2),
        "altitude_max_m": round(alt_max, 2),
        "altitude_std_m": round(alt_std, 3),
        # Per-leg detail
        "legs": results,
    }
    _reset_environment(bridge, weather=weather, wind=wind)
    return metrics


def compute_multi_run_stats(all_runs: list) -> dict:
    """
    Compute mean ± std across multiple runs for all scalar metrics.

    Args:
        all_runs: List of metric dicts from run_roam()

    Returns:
        Dict with mean, std, and all individual runs
    """
    scalar_keys = [
        "success_rate", "collision_rate_per_km", "collision_rate_per_goal",
        "avg_efficiency_pct", "avg_time_to_goal_s", "time_efficiency_mps",
        "avg_min_obstacle_m", "total_close_calls", "recovery_score_pct",
        "altitude_mean_m", "altitude_min_m", "altitude_max_m", "altitude_std_m",
        "post_collision_reset_legs",
        "successes", "collisions", "stucks", "timeouts",
        "total_path_m", "total_time_s",
    ]

    stats = {}
    for key in scalar_keys:
        values = [r[key] for r in all_runs if key in r and r[key] is not None]
        if values:
            stats[key] = {
                "mean": round(float(np.mean(values)), 3),
                "std": round(float(np.std(values)), 3),
                "min": round(float(np.min(values)), 3),
                "max": round(float(np.max(values)), 3),
                "values": [round(float(v), 3) for v in values],
            }

    return stats


def print_multi_run_summary(controller: str, stats: dict, n_runs: int):
    """Print a clean summary table for multi-run results."""
    print(f"\n{'#'*70}")
    print(f"  MULTI-RUN SUMMARY — {controller.upper()} ({n_runs} runs)")
    print(f"{'#'*70}")
    print(f"  {'Metric':<30s} {'Mean':>10s} {'± Std':>10s} {'Min':>8s} {'Max':>8s}")
    print(f"  {'-'*68}")

    display = [
        ("Success Rate (%)",        "success_rate"),
        ("Collisions/km",           "collision_rate_per_km"),
        ("Collisions/goal",         "collision_rate_per_goal"),
        ("Avg Efficiency (%)",      "avg_efficiency_pct"),
        ("Avg Time/Goal (s)",       "avg_time_to_goal_s"),
        ("Eff. Speed (m/s)",        "time_efficiency_mps"),
        ("Avg Min Obstacle (m)",    "avg_min_obstacle_m"),
        ("Close Calls",             "total_close_calls"),
        ("Recovery Score (%)",      "recovery_score_pct"),
        ("Altitude Mean (m)",       "altitude_mean_m"),
        ("Altitude Std (m)",        "altitude_std_m"),
        ("Altitude Min (m)",        "altitude_min_m"),
        ("Altitude Max (m)",        "altitude_max_m"),
        ("Reset-Origin Legs",      "post_collision_reset_legs"),
        ("Total Path (m)",          "total_path_m"),
        ("Total Time (s)",          "total_time_s"),
    ]

    for label, key in display:
        if key in stats:
            s = stats[key]
            print(f"  {label:<30s} {s['mean']:>10.2f} {s['std']:>9.2f} {s['min']:>8.2f} {s['max']:>8.2f}")

    print(f"  {'-'*68}")


def run_domain_randomization_suite(controllers: list, num_runs: int,
                                   timeout_per_goal: float, seed: int) -> dict:
    """Run the roam path under randomized weather + wind conditions."""
    conditions = _sample_domain_randomization_conditions(num_runs, seed)
    suite_results = {
        "suite": "domain_randomization",
        "path_strategy": "roam_goals_continuous",
        "num_runs": num_runs,
        "seed": seed,
        "conditions": [],
        "controller_summary": {},
    }

    controller_runs = {ctrl: [] for ctrl in controllers}
    for idx, cond in enumerate(conditions, start=1):
        print(f"\n{'*'*70}")
        print(f"  DOMAIN RANDOMIZATION {idx}/{len(conditions)} — {cond['name']}")
        print(f"  fog={cond['weather']['fog']:.2f} rain={cond['weather']['rain']:.2f} "
              f"wind={cond['wind']['speed']:.1f}m/s dir={cond['wind']['direction'][:2]}")
        print(f"{'*'*70}")

        cond_entry = {
            "name": cond["name"],
            "weather": cond["weather"],
            "wind": cond["wind"],
            "results": {},
        }
        for ctrl in controllers:
            run_data = run_roam(ctrl, ROAM_GOALS, timeout_per_goal,
                                weather=cond["weather"], wind=cond["wind"])
            run_data["run_index"] = idx
            run_data["condition_name"] = cond["name"]
            cond_entry["results"][ctrl] = _bundle_runs([run_data])
            controller_runs[ctrl].append(run_data)
        suite_results["conditions"].append(cond_entry)

    for ctrl, runs in controller_runs.items():
        suite_results["controller_summary"][ctrl] = _bundle_runs(runs)
        print_multi_run_summary(_controller_label(ctrl), suite_results["controller_summary"][ctrl]["stats"], len(runs))

    return suite_results


def run_sensor_noise_suite(controllers: list, num_runs: int,
                           timeout_per_goal: float) -> dict:
    """Run the roam path under LiDAR noise and dropout conditions."""
    suite_results = {
        "suite": "sensor_noise",
        "path_strategy": "roam_goals_continuous",
        "num_runs": num_runs,
        "conditions": [],
        "controller_summary": {},
    }

    controller_runs = {ctrl: [] for ctrl in controllers}
    for cond in LIDAR_NOISE_CONDITIONS:
        print(f"\n{'*'*70}")
        print(f"  SENSOR NOISE — {cond['name']}")
        print(f"{'*'*70}")
        cond_entry = {
            "name": cond["name"],
            "lidar_noise": cond,
            "results": {},
        }

        for ctrl in controllers:
            runs = []
            for run_idx in range(num_runs):
                print(f"\n  {_controller_label(ctrl)} | Run {run_idx + 1}/{num_runs}")
                run_data = run_roam(ctrl, ROAM_GOALS, timeout_per_goal, lidar_noise=cond)
                run_data["run_index"] = run_idx + 1
                run_data["condition_name"] = cond["name"]
                runs.append(run_data)
                controller_runs[ctrl].append(run_data)
            cond_entry["results"][ctrl] = _bundle_runs(runs)
            if num_runs > 1:
                print_multi_run_summary(f"{_controller_label(ctrl)} [{cond['name']}]",
                                        cond_entry["results"][ctrl]["stats"], num_runs)
        suite_results["conditions"].append(cond_entry)

    for ctrl, runs in controller_runs.items():
        suite_results["controller_summary"][ctrl] = _bundle_runs(runs)
        print_multi_run_summary(_controller_label(ctrl), suite_results["controller_summary"][ctrl]["stats"], len(runs))

    return suite_results


def run_imu_noise_suite(controllers: list, num_runs: int,
                        timeout_per_goal: float) -> dict:
    """Run the roam path under position/velocity/yaw/altitude state noise."""
    suite_results = {
        "suite": "imu_noise",
        "path_strategy": "roam_goals_continuous",
        "num_runs": num_runs,
        "conditions": [],
        "controller_summary": {},
    }

    controller_runs = {ctrl: [] for ctrl in controllers}
    for cond in IMU_NOISE_CONDITIONS:
        print(f"\n{'*'*70}")
        print(f"  IMU NOISE — {cond['name']}")
        print(f"{'*'*70}")
        cond_entry = {
            "name": cond["name"],
            "imu_noise": cond,
            "results": {},
        }

        for ctrl in controllers:
            runs = []
            for run_idx in range(num_runs):
                print(f"\n  {_controller_label(ctrl)} | Run {run_idx + 1}/{num_runs}")
                run_data = run_roam(ctrl, ROAM_GOALS, timeout_per_goal, imu_noise=cond)
                run_data["run_index"] = run_idx + 1
                run_data["condition_name"] = cond["name"]
                runs.append(run_data)
                controller_runs[ctrl].append(run_data)
            cond_entry["results"][ctrl] = _bundle_runs(runs)
            if num_runs > 1:
                print_multi_run_summary(f"{_controller_label(ctrl)} [{cond['name']}]",
                                        cond_entry["results"][ctrl]["stats"], num_runs)
        suite_results["conditions"].append(cond_entry)

    for ctrl, runs in controller_runs.items():
        suite_results["controller_summary"][ctrl] = _bundle_runs(runs)
        print_multi_run_summary(_controller_label(ctrl), suite_results["controller_summary"][ctrl]["stats"], len(runs))

    return suite_results


def run_ablation_suite(num_runs: int, timeout_per_goal: float) -> dict:
    """Run ablation controllers over the same continuous 12-leg roam mission."""
    suite_results = {
        "suite": "ablation",
        "path_strategy": "roam_goals_continuous",
        "num_runs": num_runs,
        "configs": [],
    }

    for cfg in ABLATION_CONFIGS:
        print(f"\n{'#'*70}")
        print(f"  ABLATION — {cfg['label']}")
        print(f"{'#'*70}")
        runs = []
        for run_idx in range(num_runs):
            print(f"\n  Run {run_idx + 1}/{num_runs}")
            run_data = run_roam(cfg["controller_type"], ROAM_GOALS, timeout_per_goal)
            run_data["run_index"] = run_idx + 1
            runs.append(run_data)

        config_entry = {
            "label": cfg["label"],
            "controller_type": cfg["controller_type"],
            "results": _bundle_runs(runs),
        }
        suite_results["configs"].append(config_entry)
        if num_runs > 1:
            print_multi_run_summary(cfg["label"], config_entry["results"]["stats"], num_runs)

    return suite_results


def export_csv(all_results: dict, csv_path: Path):
    """
    Flatten nested JSON results into a single CSV with one row per leg.

    Columns: controller, run, leg_name, goal_x, goal_y, start_x, start_y,
             end_x, end_y, success, collision, stuck, timeout, time_s,
             path_length_m, start_dist_m, efficiency_pct, min_obstacle_m,
             close_calls, steps, altitude_min, altitude_max, altitude_mean,
             altitude_std, replans, proactive_replans, rl_fallback, ...
    """
    def append_rows(rows: list, run_data: dict, meta: dict):
        run_idx = run_data.get("run_index", 1)
        for leg in run_data.get("legs", []):
            row = {**meta, "run": run_idx}
            for key in (
                "success_rate", "collisions", "collision_rate_per_km",
                "collision_rate_per_goal", "avg_efficiency_pct",
                "avg_time_to_goal_s", "time_efficiency_mps",
                "avg_min_obstacle_m", "total_close_calls",
                "recovery_score_pct", "altitude_mean_m", "altitude_std_m",
                "post_collision_reset_legs",
            ):
                if key in run_data:
                    row[f"run_{key}"] = run_data[key]

            for k, v in leg.items():
                if k == "goal":
                    row["goal_x"] = v[0] if isinstance(v, list) else v
                    row["goal_y"] = v[1] if isinstance(v, list) else 0
                elif k == "start_pos":
                    row["start_x"] = v[0] if isinstance(v, list) else v
                    row["start_y"] = v[1] if isinstance(v, list) else 0
                elif k == "end_pos":
                    row["end_x"] = v[0] if isinstance(v, list) else v
                    row["end_y"] = v[1] if isinstance(v, list) else 0
                else:
                    row[k] = v
            rows.append(row)

    rows = []
    if "suite" not in all_results:
        for ctrl, data in all_results.items():
            run_list = data["runs"] if "runs" in data else [data]
            for run_data in run_list:
                append_rows(rows, run_data, {"suite": "standard", "controller": ctrl})
    elif all_results["suite"] == "ablation":
        for cfg in all_results["configs"]:
            for run_data in cfg["results"]["runs"]:
                append_rows(rows, run_data, {
                    "suite": "ablation",
                    "config": cfg["label"],
                    "controller": cfg["controller_type"],
                })
    else:
        suite_name = all_results["suite"]
        for cond in all_results["conditions"]:
            cond_meta = {
                "suite": suite_name,
                "condition": cond["name"],
            }
            if "weather" in cond:
                cond_meta["fog"] = cond["weather"]["fog"]
                cond_meta["rain"] = cond["weather"]["rain"]
            if "wind" in cond:
                cond_meta["wind_speed"] = cond["wind"]["speed"]
                cond_meta["wind_dir_x"] = cond["wind"]["direction"][0]
                cond_meta["wind_dir_y"] = cond["wind"]["direction"][1]
            if "lidar_noise" in cond:
                cond_meta["lidar_noise_std"] = cond["lidar_noise"]["noise_std"]
                cond_meta["lidar_dropout"] = cond["lidar_noise"]["dropout"]
            if "imu_noise" in cond:
                cond_meta["imu_position_std"] = cond["imu_noise"]["position_std"]
                cond_meta["imu_velocity_std"] = cond["imu_noise"]["velocity_std"]
                cond_meta["imu_yaw_std_deg"] = cond["imu_noise"]["yaw_std_deg"]
                cond_meta["imu_altitude_std"] = cond["imu_noise"]["altitude_std"]

            for ctrl, result_block in cond["results"].items():
                for run_data in result_block["runs"]:
                    append_rows(rows, run_data, {**cond_meta, "controller": ctrl})

    df = pd.DataFrame(rows)
    df.to_csv(csv_path, index=False)


def main():
    parser = argparse.ArgumentParser(
        description="Roam Test — Capstone Evaluation (multi-goal, multi-run)")
    parser.add_argument("--timeout-per-goal", type=int, default=120,
                        help="Seconds before declaring a single goal failed (default: 120)")
    parser.add_argument("--controller", choices=["pure_rl", "hybrid", "both"], default="both",
                        help="Which controller to test (default: both)")
    parser.add_argument("--suite", choices=["standard", "domain_randomization", "sensor_noise", "imu_noise", "ablation"], default="standard",
                        help="Robustness or ablation suite to run on top of the roam path (default: standard)")
    parser.add_argument("--runs", type=int, default=1,
                        help="Number of runs per controller for statistical validity (default: 1)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducible randomized conditions/noise (default: 42)")
    args = parser.parse_args()

    np.random.seed(args.seed)

    controllers = ["pure_rl", "hybrid"] if args.controller == "both" else [args.controller]

    if args.suite == "domain_randomization":
        all_results = run_domain_randomization_suite(controllers, args.runs, args.timeout_per_goal, args.seed)
    elif args.suite == "sensor_noise":
        all_results = run_sensor_noise_suite(controllers, args.runs, args.timeout_per_goal)
    elif args.suite == "imu_noise":
        all_results = run_imu_noise_suite(controllers, args.runs, args.timeout_per_goal)
    elif args.suite == "ablation":
        all_results = run_ablation_suite(args.runs, args.timeout_per_goal)
    else:
        all_results = {}

        for ctrl in controllers:
            runs = []
            for run_idx in range(args.runs):
                if args.runs > 1:
                    print(f"\n{'*'*70}")
                    print(f"  RUN {run_idx + 1}/{args.runs} — {ctrl.upper()}")
                    print(f"{'*'*70}")

                run_data = run_roam(ctrl, ROAM_GOALS, args.timeout_per_goal)
                run_data["run_index"] = run_idx + 1
                runs.append(run_data)

            if args.runs > 1:
                stats = compute_multi_run_stats(runs)
                print_multi_run_summary(ctrl, stats, args.runs)
                all_results[ctrl] = {
                    "n_runs": args.runs,
                    "stats": stats,
                    "runs": runs,
                }
            else:
                all_results[ctrl] = runs[0]

        # ── Side-by-side comparison (single run or means) ──
        if len(all_results) == 2:
            def _get_val(data, key):
                if "stats" in data:
                    stat_entry = data["stats"].get(key)
                    return stat_entry.get("mean") if stat_entry else None
                return data.get(key)

            rl = all_results["pure_rl"]
            hy = all_results["hybrid"]
            suffix = f" (mean of {args.runs} runs)" if args.runs > 1 else ""

            print(f"\n{'#'*70}")
            print(f"  COMPARISON — PURE RL vs HYBRID{suffix}")
            print(f"{'#'*70}")
            print(f"  {'Metric':<30s} {'Pure RL':>12s} {'Hybrid':>12s}")
            print(f"  {'-'*55}")
            rows = [
                ("Success Rate (%)",     "success_rate"),
                ("Collisions/km",        "collision_rate_per_km"),
                ("Avg Efficiency (%)",   "avg_efficiency_pct"),
                ("Avg Time/Goal (s)",    "avg_time_to_goal_s"),
                ("Eff. Speed (m/s)",     "time_efficiency_mps"),
                ("Avg Min Obstacle (m)", "avg_min_obstacle_m"),
                ("Close Calls",          "total_close_calls"),
                ("Recovery Score (%)",   "recovery_score_pct"),
                ("Altitude Mean (m)",    "altitude_mean_m"),
                ("Altitude Std (m)",     "altitude_std_m"),
                ("Reset-Origin Legs",    "post_collision_reset_legs"),
            ]
            for label, key in rows:
                rv = _get_val(rl, key)
                hv = _get_val(hy, key)
                print(f"  {label:<30s} {_format_optional_table_value(rv)} {_format_optional_table_value(hv)}")
            print(f"  {'-'*55}")

            # Per-leg comparison (first run only for readability)
            rl_legs = rl.get("legs") or rl.get("runs", [{}])[0].get("legs", [])
            hy_legs = hy.get("legs") or hy.get("runs", [{}])[0].get("legs", [])
            if rl_legs and hy_legs:
                print(f"\n  {'Leg':<25s} {'Pure RL':>12s} {'City Plan':>12s}")
                print(f"  {'-'*50}")
                for rl_leg, hy_leg in zip(rl_legs, hy_legs):
                    rl_s = "OK" if rl_leg["success"] else ("!!" if rl_leg["collision"] else ("==" if rl_leg["stuck"] else ">>"))
                    hy_s = "OK" if hy_leg["success"] else ("!!" if hy_leg["collision"] else ("==" if hy_leg["stuck"] else ">>"))
                    print(f"  {rl_leg['name']:<25s} {rl_s} {rl_leg['time']:5.0f}s  {hy_s} {hy_leg['time']:5.0f}s")
                print()

    # Save results — write into results/{suite}/ subfolder
    out_dir = Path(__file__).parent / "results" / args.suite
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    n_tag = f"_{args.runs}runs" if args.runs > 1 else ""
    prefix = "roam" if args.suite == "standard" else f"roam_{args.suite}"
    filepath = out_dir / f"{prefix}_{ts}{n_tag}.json"
    with open(filepath, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"Results saved: {filepath}")

    # CSV export — flat per-leg table ready for Matplotlib/Seaborn
    csv_path = out_dir / f"{prefix}_{ts}{n_tag}.csv"
    export_csv(all_results, csv_path)
    print(f"CSV saved:     {csv_path}")


if __name__ == "__main__":
    main()
