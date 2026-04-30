"""
NavRL Capstone — Unified Test Runner
======================================
Runs all 11 test categories from TESTING_PLAN.md and saves results + diagrams.

Usage:
    python capstone_test_runner.py --test 1          # Navigation baseline (both controllers)
    python capstone_test_runner.py --test 2          # Adverse conditions baseline (both controllers)
    python capstone_test_runner.py --test 3          # Obstacle avoidance (both controllers)
    python capstone_test_runner.py --test 4          # Altitude dynamics (both controllers)
    python capstone_test_runner.py --test 5          # Domain robustness (both controllers)
    python capstone_test_runner.py --test 6          # Multi-waypoint mission
    python capstone_test_runner.py --test 7          # Computational performance
    python capstone_test_runner.py --test 8          # Ablation study
    python capstone_test_runner.py --test 9          # Long-range urban traverse
    python capstone_test_runner.py --test 10         # Pop-up obstacle stress
    python capstone_test_runner.py --test 11         # Sensor degradation gauntlet
    python capstone_test_runner.py --test all        # Run everything
    python capstone_test_runner.py --test 1 2 8      # Run specific tests
    python capstone_test_runner.py --trials 5        # Override trial count
"""

import airsim
import numpy as np
import torch
import time
import json
import argparse
import sys
import os
import traceback
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional

# Add paths
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'navrl_model'))

# ============================================================================
# CONFIGURATION
# ============================================================================
RESULTS_DIR = Path(__file__).parent / "results"
GOAL_THRESHOLD = 2.0
CONTROL_FREQ = 20
DEFAULT_ALTITUDE = -3.0  # NED

# Scenarios for TEST 1, 2, 8
# Designed around actual AirSim building locations:
#   BG_Building      (0.3, 29)     - 29m north
#   Building_C cluster (0 to -20, -78 to -105) - south
#   OrnateWall compound (50-100, -45 to -87)   - southeast
#   Building_9       (97, 26)     - 100m northeast
#   Apartment        (93, -69)    - 116m east-southeast
#   Building_4       (-95, 67)    - 116m northwest
#   Apartment towers (57,112) (-60,119) - north
NAVIGATION_SCENARIOS = [
    # 1. Fly THROUGH the north building — direct collision course with BG_Building at (0.3,29)
    {"name": "through_north_bldg",    "goal": [0, 60],     "timeout": 60},
    # 2. Goal BEHIND the north building, offset — must detect + go around
    {"name": "behind_north_bldg",     "goal": [5, 55],     "timeout": 60},
    # 3. Navigate into the southern Building_C cluster
    {"name": "south_bldg_cluster",    "goal": [-10, -95],  "timeout": 90},
    # 4. Through the OrnateWall walled compound — tight passages
    {"name": "wall_compound",         "goal": [75, -65],   "timeout": 100},
    # 5. To Building_9 past the north building — must dodge building at y=29
    {"name": "northeast_past_bldg",   "goal": [97, 30],    "timeout": 100},
    # 6. To Apartment through wall compound — dense obstacle zone
    {"name": "apartment_through_walls","goal": [90, -70],   "timeout": 120},
    # 7. Cross-city diagonal — passes north bldg, continues to NW building area
    {"name": "cross_city_NW",         "goal": [-90, 70],   "timeout": 120},
    # 8. Long traverse to far apartment tower — through multiple obstacle zones
    {"name": "long_to_tower",         "goal": [55, 115],   "timeout": 150},
]

OBSTACLE_SCENARIOS = [
    # Fly directly into BG_Building — must avoid or climb
    {"name": "head_on_building",      "goal": [0, 55],     "timeout": 90},
    # Navigate through the dense Building_C cluster (multiple buildings)
    {"name": "dense_bldg_cluster",    "goal": [-15, -100], "timeout": 120},
    # Through OrnateWall compound — narrow walled passages
    {"name": "walled_compound",       "goal": [80, -60],   "timeout": 120},
    # Goal right behind building at (0.3,29) — must navigate around corner
    {"name": "behind_building",       "goal": [3, 35],     "timeout": 90},
    # Diagonal through multiple obstacle zones NE
    {"name": "multi_obstacle_traverse","goal": [95, 25],    "timeout": 120},
]

ABLATION_SCENARIOS = [
    # Open field control (no obstacles) — baseline for all configs
    {"name": "open_field",            "goal": [50, 0],    "timeout": 70},
    # Through north building — tests obstacle avoidance layer
    {"name": "through_building",      "goal": [0, 55],    "timeout": 90},
    # Dense Building_C cluster — stresses avoidance
    {"name": "dense_cluster",         "goal": [-10, -95], "timeout": 120},
    # Walled compound — precision navigation
    {"name": "walled_area",           "goal": [75, -65],  "timeout": 120},
    # Long diagonal through city — needs global + local planning
    {"name": "long_through_city",     "goal": [55, 115],  "timeout": 150},
]

MISSION_CONFIGS = [
    # Patrol around the north building — 4 WPs forming a box around BG_Building at (0.3,29)
    {"name": "building_patrol",  "waypoints": [[-15,25],[15,25],[15,55],[0,60]], "timeout_per_wp": 60},
    # Urban patrol — visits multiple building areas, must navigate around obstacles
    {"name": "urban_patrol",     "waypoints": [[0,55],[50,-50],[90,-65],[95,25],[55,110],[-60,115],[-90,65]], "timeout_per_wp": 80},
    # Full city tour — long mission touching all major building clusters
    {"name": "city_tour",        "waypoints": [[0,55],[-10,-90],[75,-65],[95,25],[55,110],[-60,115],[-90,65],[-20,-100],[90,-70],[0,0]], "timeout_per_wp": 90},
]

WEATHER_CONDITIONS = [
    {"name": "clear",      "fog": 0.0, "rain": 0.0},
    {"name": "fog",        "fog": 0.3, "rain": 0.0},
    {"name": "heavy_fog",  "fog": 0.7, "rain": 0.0},
]

WIND_CONDITIONS = [
    {"name": "calm",        "speed": 0, "direction": [0,0,0]},
    {"name": "light_wind",  "speed": 3, "direction": [0,1,0]},
    {"name": "strong_wind", "speed": 8, "direction": [1,-1,0]},
]

LIDAR_NOISE_CONDITIONS = [
    {"name": "clean",         "noise_std": 0.0,  "dropout": 0.0},
    {"name": "lidar_noise",   "noise_std": 0.1,  "dropout": 0.0},
    {"name": "lidar_dropout", "noise_std": 0.0,  "dropout": 0.2},
]

# ============================================================================
# PHASE 1 — Dense Urban Long-Range Traverse (300-500m)
# ============================================================================
LONG_RANGE_GOALS = [
    # 300m north — must traverse north building zone first
    {"name": "long_north_300m",   "goal": [0, 300],     "timeout": 250},
    # ~350m NE — diagonal past multiple buildings
    {"name": "long_NE_350m",      "goal": [200, 280],   "timeout": 300},
    # ~400m SE — through wall compound, past apartment
    {"name": "long_SE_400m",      "goal": [280, -280],  "timeout": 350},
    # ~300m NW — through north bldg, past Building_4
    {"name": "long_NW_300m",      "goal": [-200, 220],  "timeout": 300},
]

LONG_RANGE_MISSIONS = [
    # ~500m grand traverse through every major building cluster
    {"name": "grand_traverse_500m",
     "waypoints": [[0, 55], [97, 26], [90, -70], [-10, -95], [-90, 70], [-60, 119]],
     "timeout_per_wp": 120},
    # ~400m urban canyon — tight legs weaving between building zones
    {"name": "urban_canyon_400m",
     "waypoints": [[-5, 35], [5, 55], [50, 20], [75, -65], [90, -70], [50, -30], [-10, -95]],
     "timeout_per_wp": 100},
]

# ============================================================================
# PHASE 2 — Pop-Up Obstacle Stress Test
# ============================================================================
POPUP_SCENARIOS = [
    # Cube spawns directly ahead at full speed
    {"name": "head_on_cube",
     "goal": [0, 80], "timeout": 120,
     "trigger_remaining_m": 50, "spawn_ahead_m": 10,
     "lateral_offset_m": 0, "obstacle_scale": [3, 3, 5]},
    # Wide wall blocks entire flight path
    {"name": "wall_across_path",
     "goal": [0, 80], "timeout": 120,
     "trigger_remaining_m": 55, "spawn_ahead_m": 12,
     "lateral_offset_m": 0, "obstacle_scale": [12, 1, 6]},
    # Two sequential pop-ups — second spawns after first dodge
    {"name": "double_popup",
     "goal": [50, 80], "timeout": 150,
     "trigger_remaining_m": 65, "spawn_ahead_m": 10,
     "lateral_offset_m": 0, "obstacle_scale": [3, 3, 5],
     "second_trigger_remaining_m": 35,
     "second_spawn_ahead_m": 10, "second_lateral_offset_m": 2},
    # Pop-up near existing building — creates compound obstacle
    {"name": "compound_near_building",
     "goal": [0, 55], "timeout": 120,
     "trigger_remaining_m": 30, "spawn_ahead_m": 8,
     "lateral_offset_m": 3, "obstacle_scale": [4, 4, 6]},
]

# ============================================================================
# PHASE 3 — Sensor Degradation Gauntlet
# ============================================================================
DEGRADATION_GOALS = [
    {"name": "through_building",  "goal": [0, 55],   "timeout": 120},
    {"name": "wall_compound",     "goal": [75, -65],  "timeout": 150},
]

DEGRADATION_CONDITIONS = [
    {"name": "clean",              "noise_std": 0.0, "dropout": 0.0},
    {"name": "noise_moderate",     "noise_std": 0.3, "dropout": 0.0},
    {"name": "noise_heavy",        "noise_std": 0.6, "dropout": 0.0},
    {"name": "dropout_30pct",      "noise_std": 0.0, "dropout": 0.3},
    {"name": "dropout_50pct",      "noise_std": 0.0, "dropout": 0.5},
    {"name": "combined_moderate",  "noise_std": 0.2, "dropout": 0.3},
    {"name": "combined_heavy",     "noise_std": 0.4, "dropout": 0.5},
    {"name": "near_blackout",      "noise_std": 0.3, "dropout": 0.7},
]


# ============================================================================
# METRIC COLLECTION
# ============================================================================

class MetricsCollector:
    """Collects detailed metrics during a navigation run."""

    def __init__(self):
        self.path = []
        self.velocities = []
        self.altitudes = []
        self.z_velocities = []
        self.obstacle_distances = []
        self.timestamps = []
        self.loop_times = []
        self.inference_times = []
        self.astar_times = []
        self.grid_update_times = []
        self.altitude_states = []
        self.close_calls = 0
        self.replans = 0
        self.waypoints_generated = 0
        self.stuck_events = 0
        self.altitude_climbs = 0
        self.altitude_state_transitions = 0
        self.best_effort_used = False
        self._last_alt_state = None

    def record_step(self, position, velocity, altitude, z_velocity,
                    obstacle_dist, loop_time=0, inference_time=0,
                    altitude_state=None, sim_time=None):
        t = sim_time if sim_time is not None else time.time()
        self.timestamps.append(t)
        self.path.append(position.copy() if hasattr(position, 'copy') else list(position))
        self.velocities.append(velocity.copy() if hasattr(velocity, 'copy') else list(velocity))
        self.altitudes.append(float(altitude))
        self.z_velocities.append(float(z_velocity))
        self.obstacle_distances.append(float(obstacle_dist))
        self.loop_times.append(float(loop_time))
        if inference_time > 0:
            self.inference_times.append(float(inference_time))
        if obstacle_dist < 1.5:
            self.close_calls += 1
        if altitude_state:
            self.altitude_states.append(altitude_state)
            if self._last_alt_state and altitude_state != self._last_alt_state:
                self.altitude_state_transitions += 1
                if altitude_state == 'climbing':
                    self.altitude_climbs += 1
            self._last_alt_state = altitude_state

    def compute_summary(self, success, collision, start_pos, goal, total_time):
        path_np = np.array(self.path)
        path_length = sum(
            np.linalg.norm(path_np[i+1] - path_np[i])
            for i in range(len(path_np) - 1)
        ) if len(path_np) > 1 else 0.0
        optimal = np.linalg.norm(np.array(goal[:2]) - np.array(start_pos[:2]))
        efficiency = min(100.0, optimal / path_length * 100) if path_length > 0.1 else 0.0

        alts = np.array(self.altitudes) if self.altitudes else np.array([0.0])
        obs = np.array(self.obstacle_distances) if self.obstacle_distances else np.array([99.0])
        vels = np.array(self.velocities) if self.velocities else np.array([[0,0]])
        vel_mags = np.linalg.norm(vels, axis=1) if len(vels.shape) > 1 else np.array([0])

        summary = {
            "success": bool(success),
            "collision": bool(collision),
            "timeout": not success and not collision,
            "time_to_goal": round(total_time, 2),
            "path_length": round(path_length, 2),
            "optimal_distance": round(optimal, 2),
            "path_efficiency": round(efficiency, 2),
            "min_obstacle_distance": round(float(np.min(obs)), 3),
            "avg_obstacle_distance": round(float(np.mean(obs)), 3),
            "close_calls": self.close_calls,
            "avg_velocity": round(float(np.mean(vel_mags)), 3),
            "max_velocity": round(float(np.max(vel_mags)), 3),
            "altitude_mean": round(float(np.mean(alts)), 3),
            "altitude_std": round(float(np.std(alts)), 3),
            "altitude_min": round(float(np.min(alts)), 3),
            "altitude_max": round(float(np.max(alts)), 3),
            "z_velocity_mean": round(float(np.mean(self.z_velocities)), 4) if self.z_velocities else 0,
            "z_velocity_std": round(float(np.std(self.z_velocities)), 4) if self.z_velocities else 0,
            "replans": self.replans,
            "waypoints_generated": self.waypoints_generated,
            "stuck_events": self.stuck_events,
            "altitude_climbs": self.altitude_climbs,
            "altitude_state_transitions": self.altitude_state_transitions,
            "best_effort_used": self.best_effort_used,
        }

        if self.loop_times:
            lt = np.array(self.loop_times)
            summary["loop_time_mean_ms"] = round(float(np.mean(lt)) * 1000, 2)
            summary["loop_time_p95_ms"] = round(float(np.percentile(lt, 95)) * 1000, 2)
            summary["loop_time_max_ms"] = round(float(np.max(lt)) * 1000, 2)
            summary["control_frequency_hz"] = round(1.0 / max(np.mean(lt), 1e-6), 1)

        if self.inference_times:
            it = np.array(self.inference_times)
            summary["inference_time_mean_ms"] = round(float(np.mean(it)) * 1000, 2)
            summary["inference_time_p95_ms"] = round(float(np.percentile(it, 95)) * 1000, 2)

        return summary

    def get_trajectory_data(self):
        """Return trajectory data for plotting."""
        return {
            "path": [list(p) for p in self.path],
            "altitudes": self.altitudes,
            "velocities": [list(v) for v in self.velocities],
            "obstacle_distances": self.obstacle_distances,
            "z_velocities": self.z_velocities,
            "timestamps": self.timestamps,
            "altitude_states": self.altitude_states,
        }


# ============================================================================
# NAVIGATION CORE — Runs a single trial
# ============================================================================

def run_navigation_trial(bridge, goal, timeout, altitude=DEFAULT_ALTITUDE,
                         controller_type="pure_rl",
                         weather=None, wind=None, lidar_noise=None):
    """
    Run a single navigation trial and collect comprehensive metrics.

    Args:
        bridge: NavRLBridge or NavRLAirSimBridge instance
        goal: [x, y] target
        timeout: max seconds
        altitude: NED target altitude
        controller_type: "pure_rl", "hybrid", "astar_alt"
        weather: {"fog": float, "rain": float} or None
        wind: {"speed": float, "direction": [x,y,z]} or None
        lidar_noise: {"noise_std": float, "dropout": float} or None

    Returns:
        dict with full trial metrics
    """
    mc = MetricsCollector()
    goal = np.array(goal, dtype=float)

    # Reset drone
    bridge.reset_drone()

    # Apply environment conditions
    if weather:
        bridge.client.simEnableWeather(True)
        bridge.client.simSetWeatherParameter(airsim.WeatherParameter.Fog, weather["fog"])
        bridge.client.simSetWeatherParameter(airsim.WeatherParameter.Rain, weather["rain"])

    if wind:
        d = np.array(wind["direction"], dtype=float)
        n = np.linalg.norm(d)
        if n > 0:
            d = d / n
        w = d * wind["speed"]
        bridge.client.simSetWind(airsim.Vector3r(float(w[0]), float(w[1]), float(w[2])))

    # Takeoff
    bridge.client.takeoffAsync().join()
    bridge.client.moveToZAsync(altitude, 2).join()
    time.sleep(0.5)

    # Get start position
    if controller_type == "pure_rl":
        start_pos, _, _, start_z, _ = bridge.get_state()
    else:
        start_pos, _, _, start_z, _ = bridge.get_drone_state()

    success = False
    collision = False
    _prev_z = start_z
    _prev_sim_ns = bridge.last_sim_time_ns
    sim_start_ns = bridge.last_sim_time_ns

    start_time = time.time()

    while True:
        loop_start = time.time()

        if bridge.check_collision():
            collision = True
            break

        # Get state (also updates bridge.last_sim_time_ns)
        if controller_type == "pure_rl":
            position, velocity, yaw, z, orientation = bridge.get_state()
        else:
            position, velocity, yaw, z, orientation = bridge.get_drone_state()

        # Sim-clock timeout (prevents false timeouts from GPU lag)
        sim_elapsed = (bridge.last_sim_time_ns - sim_start_ns) / 1e9
        if sim_elapsed > timeout:
            break

        dist = np.linalg.norm(goal[:2] - position[:2])
        if dist < GOAL_THRESHOLD:
            success = True
            break

        # Process LiDAR
        if controller_type == "pure_rl":
            lidar_obs, min_obs = bridge.process_lidar(position, goal, orientation)
        else:
            lidar_obs, min_obs = bridge.process_lidar(position, yaw, goal, orientation=orientation)

        # Add LiDAR noise if specified
        # NOTE: min_obs above is pre-noise ground truth from AirSim physics.
        # Safety metrics (close_calls) use true proximity even under sensor degradation.
        # Noise below only affects lidar_obs fed to the RL model.
        if lidar_noise and (lidar_noise["noise_std"] > 0 or lidar_noise["dropout"] > 0):
            lidar_np = lidar_obs.cpu().numpy()
            if lidar_noise["noise_std"] > 0:
                noise = np.random.normal(0, lidar_noise["noise_std"], lidar_np.shape)
                lidar_np = np.clip(lidar_np + noise, 0, 4.0)
            if lidar_noise["dropout"] > 0:
                mask = np.random.random(lidar_np.shape) < lidar_noise["dropout"]
                lidar_np[mask] = 0.0
            lidar_obs = torch.tensor(lidar_np, dtype=torch.float32, device=lidar_obs.device)

        # Compute action
        goal_3d = np.array([goal[0], goal[1], altitude])
        infer_start = time.time()

        if controller_type == "pure_rl":
            vel_cmd = bridge.compute_action(position, velocity, goal_3d, lidar_obs, z)
            vel_x, vel_y, vel_z = vel_cmd[0], vel_cmd[1], vel_cmd[2]
        elif controller_type == "p_control_alt":
            # Simple proportional waypoint follower — no RL, no avoidance
            vel_cmd = _proportional_waypoint_follow(position, goal, altitude, z, min_obs)
            vel_x, vel_y, vel_z = vel_cmd[0], vel_cmd[1], vel_cmd[2]
        elif controller_type == "rl_fixed_alt":
            # RL model for X/Y + simple P-control for altitude (no state machine)
            vel_cmd = bridge.compute_action(position, velocity, goal_3d, lidar_obs, z)
            vel_x, vel_y = vel_cmd[0], vel_cmd[1]
            alt_error = altitude - z
            vel_z = float(np.clip(alt_error * 0.5, -1.5, 1.5))
        else:  # hybrid
            vel_cmd = bridge.compute_action(position, velocity, goal_3d, lidar_obs,
                                            current_z=z, min_obstacle_dist=min_obs)
            vel_x, vel_y = vel_cmd[0], vel_cmd[1]
            vel_z = bridge.compute_dynamic_altitude(lidar_obs, z, altitude, min_obs)

        infer_time = time.time() - infer_start

        # Yaw toward goal
        goal_dir = goal[:2] - position
        yaw_deg = float(np.degrees(np.arctan2(goal_dir[1], goal_dir[0])))

        bridge.client.moveByVelocityAsync(
            float(vel_x), float(vel_y), float(vel_z),
            duration=1.5 / CONTROL_FREQ,
            drivetrain=airsim.DrivetrainType.MaxDegreeOfFreedom,
            yaw_mode=airsim.YawMode(is_rate=False, yaw_or_rate=yaw_deg)
        )

        loop_time = time.time() - loop_start

        sim_dt = (bridge.last_sim_time_ns - _prev_sim_ns) / 1e9
        z_vel = (z - _prev_z) / max(sim_dt, 0.001)
        _prev_z = z
        _prev_sim_ns = bridge.last_sim_time_ns

        alt_state = getattr(bridge, 'altitude_state', 'n/a')
        mc.record_step(
            position=position, velocity=velocity,
            altitude=-z,  # Convert NED to positive altitude
            z_velocity=z_vel,
            obstacle_dist=min_obs,
            loop_time=loop_time,
            inference_time=infer_time,
            altitude_state=alt_state,
            sim_time=sim_elapsed
        )

        # Print progress periodically
        if int(sim_elapsed * 2) % 4 == 0:
            status = "R" if min_obs < 1.5 else ("Y" if min_obs < 2.5 else "G")
            print(f"\r   [{status}] D:{dist:5.1f}m Alt:{-z:4.1f}m Obs:{min_obs:.1f}m t:{sim_elapsed:.0f}s", end="")

        time.sleep(1.0 / CONTROL_FREQ)

    # Stop drone
    try:
        bridge.client.moveByVelocityAsync(0, 0, 0, 1).join()
    except Exception:
        pass

    # Always reset weather/wind (even on partial failure)
    _reset_environment(bridge, weather, wind)

    total_time = (bridge.last_sim_time_ns - sim_start_ns) / 1e9
    summary = mc.compute_summary(success, collision, start_pos, goal, total_time)
    trajectory = mc.get_trajectory_data()

    outcome = "SUCCESS" if success else ("COLLISION" if collision else "TIMEOUT")
    print(f"\n   -> {outcome} | {total_time:.1f}s | eff:{summary['path_efficiency']:.0f}%")

    return {
        "summary": summary,
        "trajectory": trajectory,
        "goal": goal.tolist(),
        "controller": controller_type,
    }


def _proportional_waypoint_follow(position, goal, altitude, current_z, min_obs):
    """
    Simple proportional controller for PControl+Alt ablation baseline.
    No RL, no pathfinding — just fly toward the waypoint with P-control.
    """
    dx = goal[0] - position[0]
    dy = goal[1] - position[1]
    dist = np.sqrt(dx**2 + dy**2)

    if dist < 0.5:
        return np.array([0.0, 0.0, 0.0])

    # Normalize direction, scale to 2 m/s max
    speed = min(2.0, dist * 0.3)
    vx = (dx / dist) * speed
    vy = (dy / dist) * speed

    # Simple altitude P-control
    alt_error = altitude - current_z
    vz = np.clip(alt_error * 0.5, -1.5, 1.5)

    return np.array([vx, vy, vz])


def _reset_environment(bridge, weather=None, wind=None):
    """Reset weather and wind to defaults — safe to call even if already clean."""
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


# ============================================================================
# POP-UP OBSTACLE HELPERS (Phase 2)
# ============================================================================

def _spawn_popup(bridge, position, goal, ahead_m, lateral_m, scale,
                 spawned_list, events_list, sim_time, dist, trial_idx, spawn_idx):
    """Spawn a collidable cube ahead of the drone's current flight path."""
    dir_to_goal = (goal[:2] - position)
    norm = np.linalg.norm(dir_to_goal)
    if norm < 1e-6:
        return
    dir_to_goal = dir_to_goal / norm
    perp = np.array([-dir_to_goal[1], dir_to_goal[0]])  # 90 deg CCW
    spawn_xy = position + dir_to_goal * ahead_m + perp * lateral_m
    spawn_z = DEFAULT_ALTITUDE  # same altitude as drone flight level

    obj_name = f"popup_{trial_idx}_{spawn_idx}_{int(time.time()*1000) % 100000}"
    pose = airsim.Pose(
        airsim.Vector3r(float(spawn_xy[0]), float(spawn_xy[1]), float(spawn_z)),
        airsim.to_quaternion(0, 0, 0)
    )
    obj_scale = airsim.Vector3r(float(scale[0]), float(scale[1]), float(scale[2]))

    try:
        bridge.client.simSpawnObject(obj_name, "Cube", pose, obj_scale, physics_enabled=False)
        spawned_list.append(obj_name)
        events_list.append({
            "time": sim_time,
            "spawn_pos": [float(spawn_xy[0]), float(spawn_xy[1]), float(spawn_z)],
            "drone_pos": position.tolist(),
            "dist_to_goal": float(dist),
            "object": obj_name,
        })
        print(f"\n   >> POP-UP spawned at [{spawn_xy[0]:.1f}, {spawn_xy[1]:.1f}]!", end="")
    except Exception as e:
        print(f"\n   >> Spawn failed: {e}", end="")


def _run_popup_trial(bridge, popup_cfg, controller_type, trial_idx):
    """Run a navigation trial with pop-up obstacles spawned mid-flight.

    The key difference from run_navigation_trial: collidable cubes are
    spawned in the drone's path when it crosses a distance threshold,
    testing the RL policy's reactive obstacle avoidance latency.
    """
    mc = MetricsCollector()
    goal = np.array(popup_cfg["goal"], dtype=float)
    timeout = popup_cfg["timeout"]
    spawned_objects = []
    popup_events = []
    first_triggered = False
    second_triggered = False

    bridge.reset_drone()
    bridge.client.takeoffAsync().join()
    bridge.client.moveToZAsync(DEFAULT_ALTITUDE, 2).join()
    time.sleep(0.5)

    if controller_type == "pure_rl":
        start_pos, _, _, start_z, _ = bridge.get_state()
    else:
        start_pos, _, _, start_z, _ = bridge.get_drone_state()

    success = False
    collision = False
    _prev_z = start_z
    _prev_sim_ns = bridge.last_sim_time_ns
    sim_start_ns = bridge.last_sim_time_ns

    while True:
        loop_start = time.time()

        if bridge.check_collision():
            collision = True
            break

        if controller_type == "pure_rl":
            position, velocity, yaw, z, orientation = bridge.get_state()
        else:
            position, velocity, yaw, z, orientation = bridge.get_drone_state()

        sim_elapsed = (bridge.last_sim_time_ns - sim_start_ns) / 1e9
        if sim_elapsed > timeout:
            break

        dist = np.linalg.norm(goal[:2] - position[:2])
        if dist < GOAL_THRESHOLD:
            success = True
            break

        # ----- POP-UP SPAWN LOGIC -----
        if not first_triggered and dist < popup_cfg["trigger_remaining_m"]:
            first_triggered = True
            _spawn_popup(bridge, position, goal, popup_cfg["spawn_ahead_m"],
                         popup_cfg.get("lateral_offset_m", 0),
                         popup_cfg["obstacle_scale"],
                         spawned_objects, popup_events,
                         sim_elapsed, dist, trial_idx, 0)

        if (not second_triggered and first_triggered and
                "second_trigger_remaining_m" in popup_cfg and
                dist < popup_cfg["second_trigger_remaining_m"]):
            second_triggered = True
            _spawn_popup(bridge, position, goal,
                         popup_cfg.get("second_spawn_ahead_m", 10),
                         popup_cfg.get("second_lateral_offset_m", 0),
                         popup_cfg["obstacle_scale"],
                         spawned_objects, popup_events,
                         sim_elapsed, dist, trial_idx, 1)

        # ----- NAVIGATION (mirrors run_navigation_trial) -----
        if controller_type == "pure_rl":
            lidar_obs, min_obs = bridge.process_lidar(position, goal, orientation)
        else:
            lidar_obs, min_obs = bridge.process_lidar(position, yaw, goal, orientation=orientation)

        goal_3d = np.array([goal[0], goal[1], DEFAULT_ALTITUDE])
        infer_start = time.time()

        if controller_type == "pure_rl":
            vel_cmd = bridge.compute_action(position, velocity, goal_3d, lidar_obs, z)
            vel_x, vel_y, vel_z = vel_cmd[0], vel_cmd[1], vel_cmd[2]
        else:
            vel_cmd = bridge.compute_action(position, velocity, goal_3d, lidar_obs,
                                            current_z=z, min_obstacle_dist=min_obs)
            vel_x, vel_y = vel_cmd[0], vel_cmd[1]
            vel_z = bridge.compute_dynamic_altitude(lidar_obs, z, DEFAULT_ALTITUDE, min_obs)

        infer_time = time.time() - infer_start

        goal_dir = goal[:2] - position
        yaw_deg = float(np.degrees(np.arctan2(goal_dir[1], goal_dir[0])))
        bridge.client.moveByVelocityAsync(
            float(vel_x), float(vel_y), float(vel_z),
            duration=1.5 / CONTROL_FREQ,
            drivetrain=airsim.DrivetrainType.MaxDegreeOfFreedom,
            yaw_mode=airsim.YawMode(is_rate=False, yaw_or_rate=yaw_deg)
        )

        loop_time = time.time() - loop_start
        sim_dt = (bridge.last_sim_time_ns - _prev_sim_ns) / 1e9
        z_vel = (z - _prev_z) / max(sim_dt, 0.001)
        _prev_z = z
        _prev_sim_ns = bridge.last_sim_time_ns

        alt_state = getattr(bridge, 'altitude_state', 'n/a')
        mc.record_step(
            position=position, velocity=velocity,
            altitude=-z, z_velocity=z_vel,
            obstacle_dist=min_obs,
            loop_time=loop_time, inference_time=infer_time,
            altitude_state=alt_state, sim_time=sim_elapsed
        )

        if int(sim_elapsed * 2) % 4 == 0:
            status = "R" if min_obs < 1.5 else ("Y" if min_obs < 2.5 else "G")
            print(f"\r   [{status}] D:{dist:5.1f}m Alt:{-z:4.1f}m Obs:{min_obs:.1f}m t:{sim_elapsed:.0f}s", end="")

        time.sleep(1.0 / CONTROL_FREQ)

    # Stop and cleanup spawned objects
    bridge.client.moveByVelocityAsync(0, 0, 0, 1).join()
    for obj_name in spawned_objects:
        try:
            bridge.client.simDestroyObject(obj_name)
        except Exception:
            pass

    total_time = (bridge.last_sim_time_ns - sim_start_ns) / 1e9
    summary = mc.compute_summary(success, collision, start_pos, goal, total_time)
    summary["popup_events"] = popup_events
    summary["popups_spawned"] = len(spawned_objects)
    trajectory = mc.get_trajectory_data()

    outcome = "SUCCESS" if success else ("COLLISION" if collision else "TIMEOUT")
    print(f"\n   -> {outcome} | {total_time:.1f}s | eff:{summary['path_efficiency']:.0f}% | popups:{len(spawned_objects)}")

    return {
        "summary": summary,
        "trajectory": trajectory,
        "goal": goal.tolist(),
        "controller": controller_type,
    }


# ============================================================================
# BRIDGE FACTORY
# ============================================================================

def create_bridge(controller_type):
    """Create the appropriate bridge for a controller type."""
    if controller_type == "pure_rl":
        from navrl_airsim_bridge import NavRLBridge
        return NavRLBridge()
    elif controller_type in ("hybrid", "rl_alt", "p_control_alt", "rl_fixed_alt"):
        from navrl_airsim_hybrid_controller import NavRLAirSimBridge
        return NavRLAirSimBridge()
    else:
        raise ValueError(f"Unknown controller: {controller_type}")


def _is_connection_error(e):
    """Check if an exception indicates an AirSim RPC connection failure."""
    err_types = ('ConnectionResetError', 'ConnectionRefusedError', 'TimeoutError',
                 'BrokenPipeError', 'ConnectionAbortedError')
    msg = str(e).lower()
    return (type(e).__name__ in err_types or
            'rpc' in msg or 'connection' in msg or 'msgpack' in msg)


def _ensure_connected(bridge, controller_type):
    """Verify AirSim connection is alive; reconnect if dead. Returns bridge."""
    try:
        bridge.client.getMultirotorState()
        return bridge
    except Exception:
        print("  ⚠ AirSim connection lost — reconnecting...")
        time.sleep(3)
        try:
            return create_bridge(controller_type)
        except Exception:
            print("  ❌ Reconnect failed. Please restart AirSim and press Enter.")
            input()
            return create_bridge(controller_type)


# ============================================================================
# SAVE/LOAD RESULTS
# ============================================================================

def save_test_results(test_name, data):
    """Save test results to the appropriate directory."""
    out_dir = RESULTS_DIR / test_name
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = out_dir / f"{test_name}_{ts}.json"
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    print(f"\n   Results saved: {filepath}")
    return filepath


# ============================================================================
# TEST 1 — Pure RL Baseline
# ============================================================================

def run_test1(num_trials=10):
    """TEST 1: Navigation Baseline — Pure RL vs Hybrid on core scenarios."""
    print("\n" + "=" * 70)
    print("TEST 1 — Navigation Baseline (Pure RL vs Hybrid)")
    print("=" * 70)

    all_results = {"test": "test1_navigation_baseline", "num_trials": num_trials,
                   "controllers": {}, "timestamp": datetime.now().isoformat()}

    for ctrl in ["pure_rl", "hybrid"]:
        print(f"\n=== Controller: {ctrl.upper()} ===")
        bridge = create_bridge(ctrl)
        ctrl_results = {}

        for scenario in NAVIGATION_SCENARIOS:
            name = scenario["name"]
            print(f"\n--- Scenario: {name} [{scenario['goal']}] ---")
            trials = []
            for t in range(num_trials):
                print(f"  Trial {t+1}/{num_trials}")
                bridge = _ensure_connected(bridge, ctrl)
                try:
                    result = run_navigation_trial(
                        bridge, scenario["goal"], scenario["timeout"],
                        controller_type=ctrl
                    )
                    trials.append(result)
                except Exception as e:
                    print(f"  Trial {t+1} ERROR: {e}")
                    traceback.print_exc()
                    if _is_connection_error(e):
                        bridge = _ensure_connected(bridge, ctrl)
                    trials.append({"summary": {"success": False, "collision": False, "timeout": True,
                                               "time_to_goal": scenario["timeout"], "error": str(e)},
                                   "trajectory": {}, "goal": scenario["goal"], "controller": ctrl})
                time.sleep(2)

            ctrl_results[name] = {
                "goal": scenario["goal"],
                "trials": trials,
                "aggregate": _aggregate_trials(trials)
            }
            print(f"  => {name}: {ctrl_results[name]['aggregate']['success_rate']}% success")

        all_results["controllers"][ctrl] = ctrl_results

    save_test_results("test1_navigation_baseline", all_results)
    return all_results


# ============================================================================
# TEST 2 — Adverse Conditions Baseline
# ============================================================================

def run_test2(num_trials=10):
    """TEST 2: Navigation under adverse conditions — fog + wind.

    Re-runs Test 1 scenarios under fog (0.3) and light crosswind (3 m/s)
    to measure whether each controller's performance degrades equally
    or if the hybrid modification is more/less resilient.
    """
    print("\n" + "=" * 70)
    print("TEST 2 — Adverse Conditions Baseline (Fog + Wind)")
    print("=" * 70)

    adverse_weather = {"fog": 0.3, "rain": 0.0}
    adverse_wind = {"speed": 3, "direction": [0, 1, 0]}

    all_results = {"test": "test2_adverse_conditions", "num_trials": num_trials,
                   "conditions": {"fog": 0.3, "wind_speed": 3, "wind_dir": [0,1,0]},
                   "controllers": {}, "timestamp": datetime.now().isoformat()}

    for ctrl in ["pure_rl", "hybrid"]:
        print(f"\n=== Controller: {ctrl.upper()} ===")
        bridge = create_bridge(ctrl)
        ctrl_results = {}

        for scenario in NAVIGATION_SCENARIOS:
            name = scenario["name"]
            print(f"\n--- Scenario: {name} [{scenario['goal']}] ---")
            trials = []
            for t in range(num_trials):
                print(f"  Trial {t+1}/{num_trials}")
                bridge = _ensure_connected(bridge, ctrl)
                try:
                    result = run_navigation_trial(
                        bridge, scenario["goal"], scenario["timeout"],
                        controller_type=ctrl,
                        weather=adverse_weather,
                        wind=adverse_wind
                    )
                    trials.append(result)
                except Exception as e:
                    print(f"  Trial {t+1} ERROR: {e}")
                    traceback.print_exc()
                    _reset_environment(bridge, adverse_weather, adverse_wind)
                    if _is_connection_error(e):
                        bridge = _ensure_connected(bridge, ctrl)
                    trials.append({"summary": {"success": False, "collision": False, "timeout": True,
                                               "time_to_goal": scenario["timeout"], "error": str(e)},
                                   "trajectory": {}, "goal": scenario["goal"], "controller": ctrl})
                time.sleep(2)

            ctrl_results[name] = {
                "goal": scenario["goal"],
                "trials": trials,
                "aggregate": _aggregate_trials(trials)
            }
            print(f"  => {name}: {ctrl_results[name]['aggregate']['success_rate']}% success")

        all_results["controllers"][ctrl] = ctrl_results

    save_test_results("test2_adverse_conditions", all_results)
    return all_results


# ============================================================================
# TEST 3 — Obstacle Avoidance Comparison
# ============================================================================

def run_test3(num_trials=10):
    """TEST 3: Obstacle avoidance — Pure RL vs Hybrid."""
    print("\n" + "=" * 70)
    print("TEST 3 — Obstacle Avoidance Comparison")
    print("=" * 70)

    all_results = {"test": "test3_obstacle_avoidance", "num_trials": num_trials,
                   "controllers": {}, "timestamp": datetime.now().isoformat()}

    for ctrl in ["pure_rl", "hybrid"]:
        print(f"\n=== Controller: {ctrl.upper()} ===")
        bridge = create_bridge(ctrl)
        ctrl_results = {}

        for scenario in OBSTACLE_SCENARIOS:
            name = scenario["name"]
            print(f"\n--- {name} [{scenario['goal']}] ---")
            trials = []
            for t in range(num_trials):
                print(f"  Trial {t+1}/{num_trials}")
                bridge = _ensure_connected(bridge, ctrl)
                try:
                    result = run_navigation_trial(
                        bridge, scenario["goal"], scenario["timeout"],
                        controller_type=ctrl
                    )
                    trials.append(result)
                except Exception as e:
                    print(f"  Trial {t+1} ERROR: {e}")
                    if _is_connection_error(e):
                        bridge = _ensure_connected(bridge, ctrl)
                    trials.append({"summary": {"success": False, "collision": True,
                                               "time_to_goal": scenario["timeout"], "error": str(e)},
                                   "trajectory": {}, "goal": scenario["goal"], "controller": ctrl})
                time.sleep(2)

            ctrl_results[name] = {
                "goal": scenario["goal"],
                "trials": trials,
                "aggregate": _aggregate_trials(trials)
            }
            print(f"  => {name}: {ctrl_results[name]['aggregate']['success_rate']}% success")

        all_results["controllers"][ctrl] = ctrl_results

    save_test_results("test3_obstacle_avoidance", all_results)
    return all_results


# ============================================================================
# TEST 4 — Altitude Dynamics
# ============================================================================

def run_test4(num_trials=10):
    """TEST 4: Altitude dynamics — Pure RL vs Hybrid at various altitudes."""
    print("\n" + "=" * 70)
    print("TEST 4 — Altitude Dynamics (Pure RL vs Hybrid)")
    print("=" * 70)

    altitude_scenarios = [
        # Fly over north building at low alt — tests climb reaction
        {"name": "low_over_building",      "goal": [0, 55],  "altitude": -2.0, "timeout": 90},
        # Through building cluster at higher alt — should clear obstacles
        {"name": "high_over_cluster",      "goal": [-10, -95],"altitude": -8.0, "timeout": 90},
        # Through wall compound at default — needs altitude maneuvering
        {"name": "walls_default_alt",      "goal": [75, -65], "altitude": -3.0, "timeout": 120},
        # Hover near obstacle — stability test near building
        {"name": "hover_near_building",    "goal": [3, 25],   "altitude": -3.0, "timeout": 30},
        # Very low altitude through building area — max altitude stress
        {"name": "low_alt_urban",          "goal": [0, 55],   "altitude": -1.5, "timeout": 90},
    ]

    all_results = {"test": "test4_altitude_dynamics", "num_trials": num_trials,
                   "controllers": {}, "timestamp": datetime.now().isoformat()}

    for ctrl in ["pure_rl", "hybrid"]:
        print(f"\n=== Controller: {ctrl.upper()} ===")
        bridge = create_bridge(ctrl)
        ctrl_results = {}

        for scenario in altitude_scenarios:
            name = scenario["name"]
            print(f"\n--- {name} [{scenario['goal']}] alt={scenario['altitude']}m ---")
            trials = []
            trial_count = 5 if name == "hover_near_building" else num_trials
            for t in range(trial_count):
                print(f"  Trial {t+1}/{trial_count}")
                bridge = _ensure_connected(bridge, ctrl)
                try:
                    result = run_navigation_trial(
                        bridge, scenario["goal"], scenario["timeout"],
                        altitude=scenario["altitude"], controller_type=ctrl
                    )
                    trials.append(result)
                except Exception as e:
                    print(f"  Trial {t+1} ERROR: {e}")
                    if _is_connection_error(e):
                        bridge = _ensure_connected(bridge, ctrl)
                    trials.append({"summary": {"success": False, "error": str(e)},
                                   "trajectory": {}, "goal": scenario["goal"], "controller": ctrl})
                time.sleep(2)

            ctrl_results[name] = {
                "goal": scenario["goal"],
                "altitude": scenario["altitude"],
                "trials": trials,
                "aggregate": _aggregate_trials(trials)
            }
            print(f"  => {name}: {ctrl_results[name]['aggregate']['success_rate']}% success")

        all_results["controllers"][ctrl] = ctrl_results

    save_test_results("test4_altitude_dynamics", all_results)
    return all_results


# ============================================================================
# TEST 5 — Domain Robustness
# ============================================================================

def run_test5(num_trials=10):
    """TEST 5: Domain robustness — weather, wind, LiDAR noise for both controllers."""
    print("\n" + "=" * 70)
    print("TEST 5 — Domain Robustness (Pure RL vs Hybrid)")
    print("=" * 70)

    # Use a goal that goes through the north building — exposes robustness under degraded conditions
    fixed_goal = [0, 55]
    fixed_timeout = 90

    all_results = {"test": "test5_domain_robustness", "num_trials": num_trials,
                   "controllers": {}, "timestamp": datetime.now().isoformat()}

    for ctrl in ["pure_rl", "hybrid"]:
        print(f"\n=== Controller: {ctrl.upper()} ===")
        bridge = create_bridge(ctrl)
        ctrl_conditions = {}

        # Weather tests
        print("\n--- WEATHER ---")
        for cond in WEATHER_CONDITIONS:
            name = f"weather_{cond['name']}"
            print(f"\n  {name}")
            trials = []
            for t in range(num_trials):
                print(f"    Trial {t+1}/{num_trials}")
                bridge = _ensure_connected(bridge, ctrl)
                try:
                    result = run_navigation_trial(
                        bridge, fixed_goal, fixed_timeout,
                        controller_type=ctrl,
                        weather={"fog": cond["fog"], "rain": cond["rain"]}
                    )
                    trials.append(result)
                except Exception as e:
                    print(f"    Trial {t+1} ERROR: {e}")
                    _reset_environment(bridge, weather={"fog": cond["fog"], "rain": cond["rain"]})
                    if _is_connection_error(e):
                        bridge = _ensure_connected(bridge, ctrl)
                    trials.append({"summary": {"success": False, "error": str(e)},
                                   "trajectory": {}, "goal": fixed_goal, "controller": ctrl})
                time.sleep(2)
            ctrl_conditions[name] = {"config": cond, "trials": trials,
                                      "aggregate": _aggregate_trials(trials)}
            print(f"    => {name}: {ctrl_conditions[name]['aggregate']['success_rate']}% success")

        # Wind tests
        print("\n--- WIND ---")
        for cond in WIND_CONDITIONS:
            name = f"wind_{cond['name']}"
            print(f"\n  {name}")
            trials = []
            for t in range(num_trials):
                print(f"    Trial {t+1}/{num_trials}")
                bridge = _ensure_connected(bridge, ctrl)
                try:
                    result = run_navigation_trial(
                        bridge, fixed_goal, fixed_timeout,
                        controller_type=ctrl,
                        wind={"speed": cond["speed"], "direction": cond["direction"]}
                    )
                    trials.append(result)
                except Exception as e:
                    print(f"    Trial {t+1} ERROR: {e}")
                    _reset_environment(bridge, wind={"speed": cond["speed"], "direction": cond["direction"]})
                    if _is_connection_error(e):
                        bridge = _ensure_connected(bridge, ctrl)
                    trials.append({"summary": {"success": False, "error": str(e)},
                                   "trajectory": {}, "goal": fixed_goal, "controller": ctrl})
                time.sleep(2)
            ctrl_conditions[name] = {"config": cond, "trials": trials,
                                      "aggregate": _aggregate_trials(trials)}
            print(f"    => {name}: {ctrl_conditions[name]['aggregate']['success_rate']}% success")

        # LiDAR noise tests
        print("\n--- LIDAR NOISE ---")
        for cond in LIDAR_NOISE_CONDITIONS:
            name = f"lidar_{cond['name']}"
            print(f"\n  {name}")
            trials = []
            for t in range(num_trials):
                print(f"    Trial {t+1}/{num_trials}")
                bridge = _ensure_connected(bridge, ctrl)
                try:
                    result = run_navigation_trial(
                        bridge, fixed_goal, fixed_timeout,
                        controller_type=ctrl,
                        lidar_noise={"noise_std": cond["noise_std"], "dropout": cond["dropout"]}
                    )
                    trials.append(result)
                except Exception as e:
                    print(f"    Trial {t+1} ERROR: {e}")
                    if _is_connection_error(e):
                        bridge = _ensure_connected(bridge, ctrl)
                    trials.append({"summary": {"success": False, "error": str(e)},
                                   "trajectory": {}, "goal": fixed_goal, "controller": ctrl})
                time.sleep(2)
            ctrl_conditions[name] = {"config": cond, "trials": trials,
                                      "aggregate": _aggregate_trials(trials)}
            print(f"    => {name}: {ctrl_conditions[name]['aggregate']['success_rate']}% success")

        all_results["controllers"][ctrl] = ctrl_conditions

    save_test_results("test5_domain_robustness", all_results)
    return all_results


# ============================================================================
# TEST 6 — Multi-Waypoint Mission
# ============================================================================

def run_test6(num_trials=5):
    """TEST 6: Multi-waypoint mission with RTB."""
    print("\n" + "=" * 70)
    print("TEST 6 — Multi-Waypoint Mission")
    print("=" * 70)

    all_results = {"test": "test6_multi_waypoint", "num_trials": num_trials,
                   "controllers": {}, "timestamp": datetime.now().isoformat()}

    for ctrl in ["pure_rl", "hybrid"]:
        print(f"\n=== Controller: {ctrl.upper()} ===")
        bridge = create_bridge(ctrl)
        ctrl_results = {}

        for mission in MISSION_CONFIGS:
            name = mission["name"]
            waypoints = mission["waypoints"]
            timeout_per = mission["timeout_per_wp"]
            print(f"\n--- {name} ({len(waypoints)} WPs) ---")

            trials = []
            for t in range(num_trials):
                print(f"  Trial {t+1}/{num_trials}")
                try:
                    result = _run_mission_trial(bridge, waypoints, timeout_per, ctrl)
                    trials.append(result)
                except Exception as e:
                    print(f"  Trial {t+1} ERROR: {e}")
                    trials.append({"waypoints_reached": 0, "waypoints_total": len(waypoints),
                                   "rtb_success": False, "total_time": 0, "error": str(e)})
                time.sleep(3)

            ctrl_results[name] = {"waypoints": waypoints, "trials": trials,
                                   "aggregate": _aggregate_mission_trials(trials, len(waypoints))}
            print(f"  => {name}: {ctrl_results[name]['aggregate']['avg_waypoints_reached']}/{len(waypoints)} WPs avg")

        all_results["controllers"][ctrl] = ctrl_results

    save_test_results("test6_multi_waypoint", all_results)
    return all_results


def _run_mission_trial(bridge, waypoints, timeout_per_wp, controller_type):
    """Run a single multi-waypoint mission trial."""
    bridge.reset_drone()
    bridge.client.takeoffAsync().join()
    bridge.client.moveToZAsync(DEFAULT_ALTITUDE, 2).join()
    time.sleep(0.5)

    # Get home position
    if controller_type == "pure_rl":
        home_pos, _, _, _, _ = bridge.get_state()
    else:
        home_pos, _, _, _, _ = bridge.get_drone_state()

    reached = 0
    total_path = 0.0
    leg_results = []
    mission_start_ns = bridge.last_sim_time_ns

    for i, wp in enumerate(waypoints):
        print(f"    WP {i+1}/{len(waypoints)}: {wp}")
        wp_goal = np.array(wp, dtype=float)

        # Get current pos
        if controller_type == "pure_rl":
            cur_pos, _, _, cur_z, _ = bridge.get_state()
        else:
            cur_pos, _, _, cur_z, _ = bridge.get_drone_state()

        # Navigate leg (reuse the core navigation but without reset)
        bridge.client.enableApiControl(True)
        bridge.client.armDisarm(True)
        if hasattr(bridge, 'prev_velocity_cmd'):
            bridge.prev_velocity_cmd = np.zeros(3)

        leg_start_ns = bridge.last_sim_time_ns
        leg_path = [cur_pos.copy()]
        leg_success = False
        leg_collision = False

        while True:
            elapsed = (bridge.last_sim_time_ns - leg_start_ns) / 1e9
            if elapsed > timeout_per_wp:
                break
            if bridge.check_collision():
                leg_collision = True
                break

            if controller_type == "pure_rl":
                pos, vel, yaw, z, orient = bridge.get_state()
            else:
                pos, vel, yaw, z, orient = bridge.get_drone_state()

            leg_path.append(pos.copy())
            dist = np.linalg.norm(wp_goal[:2] - pos[:2])

            if dist < GOAL_THRESHOLD:
                leg_success = True
                break

            if controller_type == "pure_rl":
                lidar, obs_d = bridge.process_lidar(pos, wp_goal, orient)
                goal_3d = np.array([wp_goal[0], wp_goal[1], DEFAULT_ALTITUDE])
                v = bridge.compute_action(pos, vel, goal_3d, lidar, z)
                vx, vy, vz = v[0], v[1], v[2]
            else:
                lidar, obs_d = bridge.process_lidar(pos, yaw, wp_goal, orientation=orient)
                goal_3d = np.array([wp_goal[0], wp_goal[1], DEFAULT_ALTITUDE])
                v = bridge.compute_action(pos, vel, goal_3d, lidar, current_z=z, min_obstacle_dist=obs_d)
                vx, vy = v[0], v[1]
                vz = bridge.compute_dynamic_altitude(lidar, z, DEFAULT_ALTITUDE, obs_d)

            gd = wp_goal[:2] - pos
            yd = float(np.degrees(np.arctan2(gd[1], gd[0])))
            bridge.client.moveByVelocityAsync(
                float(vx), float(vy), float(vz), 1.5/CONTROL_FREQ,
                drivetrain=airsim.DrivetrainType.MaxDegreeOfFreedom,
                yaw_mode=airsim.YawMode(is_rate=False, yaw_or_rate=yd))
            time.sleep(1.0 / CONTROL_FREQ)

        bridge.client.moveByVelocityAsync(0, 0, 0, 1).join()

        leg_len = sum(np.linalg.norm(np.array(leg_path[j+1]) - np.array(leg_path[j]))
                      for j in range(len(leg_path)-1)) if len(leg_path) > 1 else 0
        total_path += leg_len

        if leg_success:
            reached += 1
            print(f"      -> REACHED ({(bridge.last_sim_time_ns - leg_start_ns) / 1e9:.1f}s)")
        elif leg_collision:
            print(f"      -> COLLISION")
            break  # End mission on collision
        else:
            print(f"      -> TIMEOUT")

        leg_results.append({"wp": wp, "success": leg_success, "collision": leg_collision,
                            "time": (bridge.last_sim_time_ns - leg_start_ns) / 1e9, "path_length": leg_len})
        time.sleep(1)

    # RTB
    rtb_success = False
    if reached > 0 and not leg_collision:
        print(f"    RTB -> [{home_pos[0]:.0f}, {home_pos[1]:.0f}]")
        if controller_type == "pure_rl":
            cur_pos, _, _, _, _ = bridge.get_state()
        else:
            cur_pos, _, _, _, _ = bridge.get_drone_state()

        rtb_dist = np.linalg.norm(home_pos - cur_pos)
        rtb_timeout = max(60, rtb_dist / 1.5)

        rtb_start_ns = bridge.last_sim_time_ns
        while True:
            elapsed = (bridge.last_sim_time_ns - rtb_start_ns) / 1e9
            if elapsed > rtb_timeout:
                break
            if bridge.check_collision():
                break

            if controller_type == "pure_rl":
                pos, vel, yaw, z, orient = bridge.get_state()
            else:
                pos, vel, yaw, z, orient = bridge.get_drone_state()

            d = np.linalg.norm(home_pos - pos)
            if d < GOAL_THRESHOLD:
                rtb_success = True
                break

            if controller_type == "pure_rl":
                lidar, obs_d = bridge.process_lidar(pos, home_pos, orient)
                goal_3d = np.array([home_pos[0], home_pos[1], DEFAULT_ALTITUDE])
                v = bridge.compute_action(pos, vel, goal_3d, lidar, z)
                vx, vy, vz = v[0], v[1], v[2]
            else:
                lidar, obs_d = bridge.process_lidar(pos, yaw, home_pos, orientation=orient)
                goal_3d = np.array([home_pos[0], home_pos[1], DEFAULT_ALTITUDE])
                v = bridge.compute_action(pos, vel, goal_3d, lidar, current_z=z, min_obstacle_dist=obs_d)
                vx, vy = v[0], v[1]
                vz = bridge.compute_dynamic_altitude(lidar, z, DEFAULT_ALTITUDE, obs_d)

            gd = home_pos - pos
            yd = float(np.degrees(np.arctan2(gd[1], gd[0])))
            bridge.client.moveByVelocityAsync(
                float(vx), float(vy), float(vz), 1.5/CONTROL_FREQ,
                drivetrain=airsim.DrivetrainType.MaxDegreeOfFreedom,
                yaw_mode=airsim.YawMode(is_rate=False, yaw_or_rate=yd))
            time.sleep(1.0 / CONTROL_FREQ)

        bridge.client.moveByVelocityAsync(0, 0, 0, 1).join()
        if rtb_success:
            print(f"      -> RTB SUCCESS ({(bridge.last_sim_time_ns - rtb_start_ns) / 1e9:.1f}s)")
        else:
            print(f"      -> RTB FAILED")

    total_time = (bridge.last_sim_time_ns - mission_start_ns) / 1e9
    return {
        "waypoints_reached": reached,
        "waypoints_total": len(waypoints),
        "rtb_success": rtb_success,
        "total_time": total_time,
        "total_path_length": total_path,
        "legs": leg_results,
    }


# ============================================================================
# TEST 7 — Computational Performance
# ============================================================================

def run_test7():
    """TEST 7: Computational performance — Pure RL vs Hybrid overhead."""
    print("\n" + "=" * 70)
    print("TEST 7 — Computational Performance")
    print("=" * 70)

    import psutil
    process = psutil.Process(os.getpid())

    all_results = {"test": "test7_computational_perf", "controllers": {},
                   "timestamp": datetime.now().isoformat()}

    for ctrl in ["pure_rl", "hybrid"]:
        print(f"\n=== {ctrl.upper()} ===")
        bridge = create_bridge(ctrl)
        bridge.reset_drone()
        bridge.client.takeoffAsync().join()
        bridge.client.moveToZAsync(DEFAULT_ALTITUDE, 2).join()
        time.sleep(1)

        goal = np.array([0.0, 500.0])  # Phantom goal — unreachable, ensures full 1000 steps
        loop_times = []
        inference_times = []
        mem_samples = []

        for step in range(1000):
            loop_start = time.time()

            if ctrl == "pure_rl":
                pos, vel, yaw, z, orient = bridge.get_state()
                lidar, obs = bridge.process_lidar(pos, goal, orient)
                goal_3d = np.array([goal[0], goal[1], DEFAULT_ALTITUDE])
                t0 = time.time()
                v = bridge.compute_action(pos, vel, goal_3d, lidar, z)
                inference_times.append(time.time() - t0)
                vx, vy, vz = v[0], v[1], v[2]
            else:
                pos, vel, yaw, z, orient = bridge.get_drone_state()
                lidar, obs = bridge.process_lidar(pos, yaw, goal, orientation=orient)
                goal_3d = np.array([goal[0], goal[1], DEFAULT_ALTITUDE])
                t0 = time.time()
                v = bridge.compute_action(pos, vel, goal_3d, lidar, current_z=z, min_obstacle_dist=obs)
                inference_times.append(time.time() - t0)
                vx, vy = v[0], v[1]
                vz = bridge.compute_dynamic_altitude(lidar, z, DEFAULT_ALTITUDE, obs)

            gd = goal[:2] - pos
            yd = float(np.degrees(np.arctan2(gd[1], gd[0])))
            bridge.client.moveByVelocityAsync(
                float(vx), float(vy), float(vz), 1.5/CONTROL_FREQ,
                drivetrain=airsim.DrivetrainType.MaxDegreeOfFreedom,
                yaw_mode=airsim.YawMode(is_rate=False, yaw_or_rate=yd))

            loop_times.append(time.time() - loop_start)

            if step % 100 == 0:
                mem_samples.append(process.memory_info().rss / 1024 / 1024)
                print(f"  Step {step}/1000, loop: {loop_times[-1]*1000:.1f}ms")

            # Only break on collision — goal is unreachable phantom
            if bridge.check_collision():
                print(f"\n  [COLLISION at step {step} — perf data truncated]")
                break

            time.sleep(1.0 / CONTROL_FREQ)

        bridge.client.moveByVelocityAsync(0, 0, 0, 1).join()

        lt = np.array(loop_times)
        it = np.array(inference_times)
        all_results["controllers"][ctrl] = {
            "steps": len(loop_times),
            "loop_time_mean_ms": round(float(np.mean(lt)) * 1000, 2),
            "loop_time_p95_ms": round(float(np.percentile(lt, 95)) * 1000, 2),
            "loop_time_max_ms": round(float(np.max(lt)) * 1000, 2),
            "control_frequency_hz": round(1.0 / max(np.mean(lt), 1e-6), 1),
            "inference_mean_ms": round(float(np.mean(it)) * 1000, 2),
            "inference_p95_ms": round(float(np.percentile(it, 95)) * 1000, 2),
            "inference_max_ms": round(float(np.max(it)) * 1000, 2),
            "memory_mb_samples": [round(m, 1) for m in mem_samples],
            "memory_avg_mb": round(float(np.mean(mem_samples)), 1) if mem_samples else 0,
        }
        print(f"  => loop: {all_results['controllers'][ctrl]['loop_time_mean_ms']}ms avg, "
              f"inference: {all_results['controllers'][ctrl]['inference_mean_ms']}ms avg")

    save_test_results("test7_computational_perf", all_results)
    return all_results


# ============================================================================
# TEST 8 — Ablation Study
# ============================================================================

def run_test8(num_trials=10):
    """TEST 8: Ablation study — isolate each modification layer.

    Configs:
      RL             — Pure RL baseline (raw model Z output, no altitude control)
      RL+FixedAlt    — RL X/Y + simple P-control altitude hold (isolates alt benefit)
      RL+AltSM       — RL X/Y + intelligent altitude state machine (full hybrid)
      PControl+AltSM — No RL avoidance, P-control X/Y + altitude SM (isolates RL value)
    """
    print("\n" + "=" * 70)
    print("TEST 8 — Ablation Study (Layer Contribution)")
    print("=" * 70)

    configs = [
        {"label": "RL",              "controller_type": "pure_rl"},
        {"label": "RL+FixedAlt",     "controller_type": "rl_fixed_alt"},
        {"label": "RL+AltSM",        "controller_type": "hybrid"},
        {"label": "PControl+AltSM",  "controller_type": "p_control_alt"},
    ]

    all_results = {"test": "test8_ablation_study", "num_trials": num_trials,
                   "configs": {}, "timestamp": datetime.now().isoformat()}

    for cfg in configs:
        label = cfg["label"]
        print(f"\n=== Configuration: {label} ===")

        if cfg["controller_type"] in ("p_control_alt", "rl_fixed_alt"):
            bridge = create_bridge("hybrid")  # Reuse hybrid bridge, override action
        else:
            bridge = create_bridge(cfg["controller_type"])

        cfg_results = {}
        for scenario in ABLATION_SCENARIOS:
            name = scenario["name"]
            print(f"\n--- {name} [{scenario['goal']}] ---")
            trials = []
            for t in range(num_trials):
                print(f"  Trial {t+1}/{num_trials}")
                _bridge_type = "hybrid" if cfg["controller_type"] in ("p_control_alt", "rl_fixed_alt") else cfg["controller_type"]
                bridge = _ensure_connected(bridge, _bridge_type)
                try:
                    result = run_navigation_trial(
                        bridge, scenario["goal"], scenario["timeout"],
                        controller_type=cfg["controller_type"]
                    )
                    trials.append(result)
                except Exception as e:
                    print(f"  Trial {t+1} ERROR: {e}")
                    if _is_connection_error(e):
                        bridge = _ensure_connected(bridge, _bridge_type)
                    trials.append({"summary": {"success": False, "collision": True,
                                               "time_to_goal": scenario["timeout"], "error": str(e)},
                                   "trajectory": {}, "goal": scenario["goal"], "controller": label})
                time.sleep(2)

            cfg_results[name] = {
                "goal": scenario["goal"],
                "trials": trials,
                "aggregate": _aggregate_trials(trials)
            }
            print(f"  => {name}: {cfg_results[name]['aggregate']['success_rate']}% success")

        all_results["configs"][label] = cfg_results

    save_test_results("test8_ablation_study", all_results)
    return all_results


# ============================================================================
# TEST 9 — Phase 1: Dense Urban Long-Range Traverse
# ============================================================================

def run_test9(num_trials=5):
    """TEST 9: Long-range (300-500m) navigation through dense urban zones.

    Tests whether the global planner + local RL avoidance can sustain
    performance over long distances without getting trapped in local minima.
    """
    print("\n" + "=" * 70)
    print("TEST 9 — Dense Urban Long-Range Traverse (300-500m)")
    print("=" * 70)

    all_results = {"test": "test9_long_range_traverse", "num_trials": num_trials,
                   "controllers": {}, "timestamp": datetime.now().isoformat()}

    for ctrl in ["pure_rl", "hybrid"]:
        print(f"\n=== Controller: {ctrl.upper()} ===")
        bridge = create_bridge(ctrl)
        ctrl_results = {}

        # --- Direct long-range goals ---
        print("\n--- Direct Long-Range Goals ---")
        for scenario in LONG_RANGE_GOALS:
            name = scenario["name"]
            print(f"\n--- {name} [{scenario['goal']}] ---")
            trials = []
            for t in range(num_trials):
                print(f"  Trial {t+1}/{num_trials}")
                bridge = _ensure_connected(bridge, ctrl)
                try:
                    result = run_navigation_trial(
                        bridge, scenario["goal"], scenario["timeout"],
                        controller_type=ctrl
                    )
                    trials.append(result)
                except Exception as e:
                    print(f"  Trial {t+1} ERROR: {e}")
                    if _is_connection_error(e):
                        bridge = _ensure_connected(bridge, ctrl)
                    trials.append({"summary": {"success": False, "collision": False, "timeout": True,
                                               "time_to_goal": scenario["timeout"], "error": str(e)},
                                   "trajectory": {}, "goal": scenario["goal"], "controller": ctrl})
                time.sleep(2)
            ctrl_results[name] = {
                "goal": scenario["goal"],
                "trials": trials,
                "aggregate": _aggregate_trials(trials)
            }
            print(f"  => {name}: {ctrl_results[name]['aggregate']['success_rate']}% success")

        # --- Long-range multi-waypoint missions ---
        print("\n--- Long-Range Multi-WP Missions ---")
        for mission in LONG_RANGE_MISSIONS:
            name = mission["name"]
            waypoints = mission["waypoints"]
            timeout_per = mission["timeout_per_wp"]
            print(f"\n--- {name} ({len(waypoints)} WPs) ---")
            trials = []
            for t in range(num_trials):
                print(f"  Trial {t+1}/{num_trials}")
                bridge = _ensure_connected(bridge, ctrl)
                try:
                    result = _run_mission_trial(bridge, waypoints, timeout_per, ctrl)
                    trials.append(result)
                except Exception as e:
                    print(f"  Trial {t+1} ERROR: {e}")
                    if _is_connection_error(e):
                        bridge = _ensure_connected(bridge, ctrl)
                    trials.append({"waypoints_reached": 0, "waypoints_total": len(waypoints),
                                   "rtb_success": False, "total_time": 0, "error": str(e)})
                time.sleep(3)
            ctrl_results[name] = {
                "waypoints": waypoints,
                "trials": trials,
                "aggregate": _aggregate_mission_trials(trials, len(waypoints))
            }
            wps_avg = ctrl_results[name]['aggregate'].get('avg_waypoints_reached', 0)
            print(f"  => {name}: {wps_avg}/{len(waypoints)} WPs avg")

        all_results["controllers"][ctrl] = ctrl_results

    save_test_results("test9_long_range_traverse", all_results)
    return all_results


# ============================================================================
# TEST 10 — Phase 2: Pop-Up Obstacle Stress Test
# ============================================================================

def run_test10(num_trials=5):
    """TEST 10: Spawn collidable obstacles mid-flight to test reactive avoidance.

    Uses AirSim's simSpawnObject API to place cubes/walls directly in the
    drone's active path during flight, measuring RL policy latency.
    """
    print("\n" + "=" * 70)
    print("TEST 10 — Pop-Up Obstacle Stress Test")
    print("=" * 70)

    all_results = {"test": "test10_popup_obstacles", "num_trials": num_trials,
                   "controllers": {}, "timestamp": datetime.now().isoformat()}

    for ctrl in ["pure_rl", "hybrid"]:
        print(f"\n=== Controller: {ctrl.upper()} ===")
        bridge = create_bridge(ctrl)
        ctrl_results = {}

        for scenario in POPUP_SCENARIOS:
            name = scenario["name"]
            print(f"\n--- {name} [{scenario['goal']}] ---")
            trials = []
            for t in range(num_trials):
                print(f"  Trial {t+1}/{num_trials}")
                bridge = _ensure_connected(bridge, ctrl)
                try:
                    result = _run_popup_trial(bridge, scenario, ctrl, t)
                    trials.append(result)
                except Exception as e:
                    print(f"  Trial {t+1} ERROR: {e}")
                    traceback.print_exc()
                    if _is_connection_error(e):
                        bridge = _ensure_connected(bridge, ctrl)
                    trials.append({"summary": {"success": False, "collision": True,
                                               "time_to_goal": scenario["timeout"],
                                               "error": str(e), "popups_spawned": 0},
                                   "trajectory": {}, "goal": scenario["goal"], "controller": ctrl})
                time.sleep(2)
            ctrl_results[name] = {
                "goal": scenario["goal"],
                "trials": trials,
                "aggregate": _aggregate_trials(trials)
            }
            print(f"  => {name}: {ctrl_results[name]['aggregate']['success_rate']}% success")

        all_results["controllers"][ctrl] = ctrl_results

    save_test_results("test10_popup_obstacles", all_results)
    return all_results


# ============================================================================
# TEST 11 — Phase 3: Sensor Degradation Gauntlet
# ============================================================================

def run_test11(num_trials=5):
    """TEST 11: Progressively degrade LiDAR to find the failure boundary.

    Cranks noise and dropout well beyond what Test 5 covered, testing
    whether the agent panics or clips corners under sensor failure.
    Tests both controllers against two obstacle-rich goals.
    """
    print("\n" + "=" * 70)
    print("TEST 11 — Sensor Degradation Gauntlet")
    print("=" * 70)

    all_results = {"test": "test11_sensor_degradation", "num_trials": num_trials,
                   "results": {}, "timestamp": datetime.now().isoformat()}

    for ctrl in ["pure_rl", "hybrid"]:
        print(f"\n=== Controller: {ctrl.upper()} ===")
        bridge = create_bridge(ctrl)
        ctrl_results = {}

        for goal_cfg in DEGRADATION_GOALS:
            goal_name = goal_cfg["name"]
            print(f"\n--- Goal: {goal_name} [{goal_cfg['goal']}] ---")
            goal_results = {}

            for cond in DEGRADATION_CONDITIONS:
                cond_name = cond["name"]
                print(f"\n  Condition: {cond_name} (noise={cond['noise_std']}, dropout={cond['dropout']})")
                trials = []
                for t in range(num_trials):
                    print(f"    Trial {t+1}/{num_trials}")
                    bridge = _ensure_connected(bridge, ctrl)
                    try:
                        result = run_navigation_trial(
                            bridge, goal_cfg["goal"], goal_cfg["timeout"],
                            controller_type=ctrl,
                            lidar_noise={"noise_std": cond["noise_std"], "dropout": cond["dropout"]}
                        )
                        trials.append(result)
                    except Exception as e:
                        print(f"    Trial {t+1} ERROR: {e}")
                        if _is_connection_error(e):
                            bridge = _ensure_connected(bridge, ctrl)
                        trials.append({"summary": {"success": False, "collision": True,
                                                   "time_to_goal": goal_cfg["timeout"], "error": str(e)},
                                       "trajectory": {}, "goal": goal_cfg["goal"], "controller": ctrl})
                    time.sleep(2)

                goal_results[cond_name] = {
                    "config": cond,
                    "trials": trials,
                    "aggregate": _aggregate_trials(trials)
                }
                sr = goal_results[cond_name]["aggregate"]["success_rate"]
                cr = goal_results[cond_name]["aggregate"]["collision_rate"]
                print(f"    => {cond_name}: {sr}% success, {cr}% collision")

            ctrl_results[goal_name] = goal_results

        all_results["results"][ctrl] = ctrl_results

    save_test_results("test11_sensor_degradation", all_results)
    return all_results


# ============================================================================
# AGGREGATION HELPERS
# ============================================================================

def _aggregate_trials(trials):
    """Compute aggregate statistics from a list of trial results."""
    summaries = [t.get("summary", t) for t in trials]
    n = len(summaries)
    if n == 0:
        return {}

    successes = sum(1 for s in summaries if s.get("success", False))
    collisions = sum(1 for s in summaries if s.get("collision", False))
    timeouts = sum(1 for s in summaries if s.get("timeout", False))

    success_rate = round(successes / n * 100, 1)
    collision_rate = round(collisions / n * 100, 1)

    def _safe_stats(key):
        vals = [s[key] for s in summaries if key in s and isinstance(s[key], (int, float))]
        if not vals:
            return {"mean": 0, "std": 0, "min": 0, "max": 0}
        a = np.array(vals)
        return {
            "mean": round(float(np.mean(a)), 3),
            "std": round(float(np.std(a)), 3),
            "min": round(float(np.min(a)), 3),
            "max": round(float(np.max(a)), 3),
        }

    # 95% CI for success rate (Wilson interval)
    if n > 0:
        p = successes / n
        z = 1.96
        denom = 1 + z**2 / n
        center = (p + z**2 / (2*n)) / denom
        spread = z * np.sqrt((p*(1-p) + z**2/(4*n)) / n) / denom
        ci_low = round(max(0, center - spread) * 100, 1)
        ci_high = round(min(1, center + spread) * 100, 1)
    else:
        ci_low, ci_high = 0, 0

    agg = {
        "total_trials": n,
        "successes": successes,
        "collisions": collisions,
        "timeouts": timeouts,
        "success_rate": success_rate,
        "success_rate_ci95": [ci_low, ci_high],
        "collision_rate": collision_rate,
        "time_to_goal": _safe_stats("time_to_goal"),
        "path_efficiency": _safe_stats("path_efficiency"),
        "path_length": _safe_stats("path_length"),
        "min_obstacle_distance": _safe_stats("min_obstacle_distance"),
        "close_calls": _safe_stats("close_calls"),
        "avg_velocity": _safe_stats("avg_velocity"),
        "altitude_mean": _safe_stats("altitude_mean"),
        "altitude_std": _safe_stats("altitude_std"),
    }
    return agg


def _aggregate_mission_trials(trials, total_wps):
    """Aggregate mission trial results."""
    n = len(trials)
    if n == 0:
        return {}

    reached = [t.get("waypoints_reached", 0) for t in trials]
    rtb = sum(1 for t in trials if t.get("rtb_success", False))
    times = [t.get("total_time", 0) for t in trials]

    return {
        "total_trials": n,
        "avg_waypoints_reached": round(float(np.mean(reached)), 1),
        "max_waypoints": total_wps,
        "completion_rate": round(sum(1 for r in reached if r == total_wps) / n * 100, 1),
        "rtb_success_rate": round(rtb / n * 100, 1),
        "avg_total_time": round(float(np.mean(times)), 1),
    }


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="NavRL Capstone Test Runner")
    parser.add_argument("--test", nargs="+", default=["all"],
                        help="Tests to run: 1-11 or 'all'")
    parser.add_argument("--trials", type=int, default=10,
                        help="Number of trials per scenario (default: 10)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility (default: 42)")
    args = parser.parse_args()

    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    tests_to_run = set()
    for t in args.test:
        if t == "all":
            tests_to_run = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11}
            break
        tests_to_run.add(int(t))

    print("\n" + "#" * 70)
    print("NAVRL CAPSTONE — TEST SUITE")
    print(f"Tests: {sorted(tests_to_run)}")
    print(f"Trials: {args.trials}")
    print(f"Seed: {args.seed}")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("#" * 70)

    results = {}

    test_funcs = {
        1: ("Navigation Baseline",    lambda: run_test1(args.trials)),
        2: ("Adverse Conditions",     lambda: run_test2(args.trials)),
        3: ("Obstacle Avoidance",     lambda: run_test3(args.trials)),
        4: ("Altitude Dynamics",      lambda: run_test4(args.trials)),
        5: ("Domain Robustness",      lambda: run_test5(args.trials)),
        6: ("Multi-Waypoint Mission", lambda: run_test6(min(args.trials, 5))),
        7: ("Computational Perf",     lambda: run_test7()),
        8: ("Ablation Study",         lambda: run_test8(args.trials)),
        9: ("Long-Range Traverse",    lambda: run_test9(min(args.trials, 5))),
        10: ("Pop-Up Obstacles",       lambda: run_test10(min(args.trials, 5))),
        11: ("Sensor Degradation",     lambda: run_test11(min(args.trials, 5))),
    }

    for num in sorted(tests_to_run):
        name, func = test_funcs[num]
        print(f"\n{'#'*70}")
        print(f"STARTING TEST {num}: {name}")
        print(f"{'#'*70}")
        try:
            results[num] = func()
        except Exception as e:
            print(f"\nTEST {num} FAILED: {e}")
            traceback.print_exc()
            results[num] = {"error": str(e)}

    print(f"\n{'#'*70}")
    print("ALL TESTS COMPLETE")
    print(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Results in: {RESULTS_DIR}")
    print(f"{'#'*70}")


if __name__ == "__main__":
    main()
