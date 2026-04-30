"""
NavRL AirSim Bridge - MINIMAL VERSION
======================================
Pure RL deployment without hand-engineered control.

This is the BASELINE for academic evaluation:
- Model controls XYZ directly (even if Z is poor)
- NO altitude state machine
- NO recovery logic
- NO smoothing filters
- Only yaw alignment (training assumption: drone faces goal)

For the hybrid controller with all helpers, see:
    navrl_airsim_hybrid_controller.py

TRAINING ASSUMPTIONS PRESERVED:
- MAX_RAY_LENGTH = 4.0m
- HRES_DEG = 10.0 (36 horizontal bins)
- VFOV_ANGLES_DEG = [-10.0, 0.0, 10.0, 20.0] (4 vertical bins)
- LiDAR in goal-relative frame (bin 0 = toward goal)
- State: [rpos_clipped_g(3), distance_2d(1), distance_z(1), vel_g(3)]

Usage:
    python navrl_airsim_bridge.py --goal 50 0
    python navrl_airsim_bridge.py --mission
"""

import airsim
import numpy as np
import torch
import time
import argparse
import sys
import os

# Add local navrl_model to path for model loading (self-contained capstone copy)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'navrl_model'))
from agent import Agent

from navrl_utils import (
    vec_to_new_frame, get_robot_state,
    MAX_RAY_LENGTH, HRES_DEG, VFOV_ANGLES_DEG,
    MAX_VELOCITY, DEFAULT_FLIGHT_HEIGHT, GOAL_THRESHOLD, CONTROL_FREQ,
)


# ============================================================================
# Frame transformation imported from navrl_utils.py
# ============================================================================


class NavRLBridge:
    """
    Minimal RL bridge - model controls everything, no hand-engineering.
    
    For academic baseline evaluation.
    """
    
    def __init__(self, device: str = None):
        if device is None:
            self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        else:
            self.device = torch.device(device)
        
        print("="*60)
        print("NavRL AirSim Bridge - MINIMAL (Pure RL)")
        print("="*60)
        print(f"Device: {self.device}")
        print(f"Mode: Pure RL (no hand-engineered control)")
        print("="*60)
        
        print("\nLoading NavRL model...")
        self.agent = Agent(device=self.device)
        print("✅ Model loaded")
        
        print("\nConnecting to AirSim...")
        self.client = airsim.MultirotorClient()
        self.client.confirmConnection()
        self.last_sim_time_ns = 0
        self._last_collision_ts = 0  # FIX: dedupe persistent contacts by timestamp
        print("✅ Connected")
        
    def reset_drone(self):
        """Reset drone."""
        self.client.reset()
        time.sleep(0.5)  # Let AirSim physics settle before re-enabling API control
        self.client.enableApiControl(True)
        self.client.armDisarm(True)
        
    def takeoff(self, altitude: float = DEFAULT_FLIGHT_HEIGHT):
        """Take off to altitude."""
        print(f"\nTaking off to {abs(altitude):.1f}m...")
        self.client.takeoffAsync().join()
        self.client.moveToZAsync(altitude, 2).join()
        print("✅ Ready")
        
    def get_state(self) -> tuple:
        """Get drone state."""
        state = self.client.getMultirotorState()
        self.last_sim_time_ns = state.timestamp
        pos = state.kinematics_estimated.position
        vel = state.kinematics_estimated.linear_velocity
        orientation = state.kinematics_estimated.orientation
        _, _, yaw = airsim.to_eularian_angles(orientation)
        
        return (
            np.array([pos.x_val, pos.y_val]),
            np.array([vel.x_val, vel.y_val, vel.z_val]),
            yaw,
            pos.z_val,
            orientation
        )
    
    def check_collision(self) -> bool:
        """Check collision.

        FIX (persistent contact + stale window):
          1. AirSim updates `info.time_stamp` only on a *new* contact event.
             A drone wedged against a wall for >0.5 s used to look stale and
             slipped past the recovery code, so the bounce-back never fired
             for the second/third scrape. Track the last handled timestamp
             and treat any *unseen* timestamp as a fresh event regardless of
             age.
          2. Widen the freshness window to 1.5 s so loops with heavier
             RL/LiDAR processing don't miss a true new collision.
        """
        info = self.client.simGetCollisionInfo()
        if not info.has_collided:
            return False
        ts = info.time_stamp
        # New collision event we haven't acted on yet — always count.
        if ts != 0 and ts != self._last_collision_ts:
            self._last_collision_ts = ts
            return True
        # Same event we already saw — only count if it's still genuinely fresh
        # relative to the latest sim-time read. Use abs() to survive a sim-time
        # reset (e.g., after `client.reset()`).
        collision_age_ns = abs(self.last_sim_time_ns - ts)
        return collision_age_ns < 1.5e9  # 1.5 s in nanoseconds
    
    def process_lidar(self, position: np.ndarray, goal: np.ndarray, 
                      orientation) -> tuple:
        """
        Process LiDAR to match training format.
        
        Transform: Body → World → Goal Frame → ENU → bins
        This matches training where LiDAR bin 0 = toward goal.
        """
        lidar_data = self.client.getLidarData(lidar_name="LidarSensor1", vehicle_name="Drone1")
        
        num_h = int(360 / HRES_DEG)  # 36
        num_v = len(VFOV_ANGLES_DEG)  # 4
        
        range_matrix = np.full((num_h, num_v), MAX_RAY_LENGTH, dtype=np.float32)
        min_dist = MAX_RAY_LENGTH
        
        if len(lidar_data.point_cloud) >= 3:
            points = np.array(lidar_data.point_cloud).reshape(-1, 3)
            
            # Body → World rotation
            q = orientation
            q_w, q_x, q_y, q_z = q.w_val, q.x_val, q.y_val, q.z_val
            s = 1.0 / (q_w**2 + q_x**2 + q_y**2 + q_z**2)
            R = np.array([
                [1 - 2*s*(q_y**2 + q_z**2),     2*s*(q_x*q_y - q_z*q_w),     2*s*(q_x*q_z + q_y*q_w)],
                [2*s*(q_x*q_y + q_z*q_w),       1 - 2*s*(q_x**2 + q_z**2),   2*s*(q_y*q_z - q_x*q_w)],
                [2*s*(q_x*q_z - q_y*q_w),       2*s*(q_y*q_z + q_x*q_w),     1 - 2*s*(q_x**2 + q_y**2)]
            ])
            points_world = points @ R.T
            
            # World → Goal frame (X axis = toward goal)
            goal_dir = np.array([goal[0] - position[0], goal[1] - position[1]])
            goal_angle = np.arctan2(goal_dir[1], goal_dir[0])
            cg, sg = np.cos(-goal_angle), np.sin(-goal_angle)
            R_goal = np.array([[cg, -sg, 0], [sg, cg, 0], [0, 0, 1]])
            points_aligned = points_world @ R_goal.T
            
            # NED → ENU
            x_body = points_aligned[:, 0]
            y_body = -points_aligned[:, 1]
            z_body = -points_aligned[:, 2]
            
            dists = np.sqrt(x_body**2 + y_body**2 + z_body**2)
            valid = (dists > 0.1) & (dists < MAX_RAY_LENGTH)
            
            if np.any(valid):
                x_v, y_v, z_v = x_body[valid], y_body[valid], z_body[valid]
                dists_v = dists[valid]
                min_dist = np.min(dists_v)
                
                h_angles = np.degrees(np.arctan2(y_v, x_v))
                h_angles = (h_angles + 360) % 360
                h_idxs = (h_angles / HRES_DEG).astype(int) % num_h
                
                flat_dists = np.sqrt(x_v**2 + y_v**2)
                v_angles = np.degrees(np.arctan2(z_v, flat_dists))
                
                # Vectorized vertical bin assignment
                vfov_arr = np.array(VFOV_ANGLES_DEG)
                v_diffs = np.abs(v_angles[:, np.newaxis] - vfov_arr[np.newaxis, :])  # (N, 4)
                v_idxs = np.argmin(v_diffs, axis=1)  # (N,)
                
                # Scatter-reduce: keep minimum distance per (h, v) bin
                np.minimum.at(range_matrix, (h_idxs, v_idxs), dists_v)
        
        # Invert to match training format (high = close)
        range_matrix = np.maximum(range_matrix, 0.1)
        range_matrix = MAX_RAY_LENGTH - range_matrix
        
        tensor = torch.tensor(range_matrix, dtype=torch.float32, device=self.device)
        tensor = tensor.unsqueeze(0).unsqueeze(0)  # (1, 1, 36, 4)
        
        return tensor, min_dist
    
    def compute_action(self, position: np.ndarray, velocity: np.ndarray,
                       goal: np.ndarray, lidar_obs: torch.Tensor,
                       current_z: float, min_obstacle_dist: float = None) -> np.ndarray:
        """
        Compute velocity from RL model.
        
        Args:
            position: Current [x, y] position in NED (promoted to 3D internally with current_z)
            velocity: Current [vx, vy, vz] velocity in NED
            goal: Target [x, y, z] position in NED
            lidar_obs: LiDAR tensor from process_lidar
            current_z: Current altitude in NED (negative = above ground)
        
        NO post-processing, NO filtering, NO clamping beyond what model outputs.
        """
        # NED → ENU
        pos_enu = np.array([position[0], -position[1], -current_z])
        vel_enu = np.array([velocity[0], -velocity[1], -velocity[2]])
        goal_enu = np.array([goal[0], -goal[1], -goal[2]])
        
        target_dir_enu = goal_enu - pos_enu
        
        # distance_z=None: use real vertical distance — paper (Eq.12) shows model trained with rpos[2]
        robot_state = get_robot_state(
            pos=pos_enu, goal=goal_enu, vel=vel_enu,
            target_dir=target_dir_enu, device=self.device,
            distance_z=None
        )
        
        dyn_obs = torch.zeros((1, 1, 5, 10), dtype=torch.float32, device=self.device)
        
        target_dir_2d = np.array([target_dir_enu[0], target_dir_enu[1], 0.0])
        norm = np.linalg.norm(target_dir_2d)
        goal_dir = target_dir_2d / max(norm, 1e-6)
        goal_dir_tensor = torch.tensor(goal_dir, dtype=torch.float32, 
                                        device=self.device).unsqueeze(0).unsqueeze(0)
        
        with torch.no_grad():
            vel_enu_out = self.agent.plan(
                robot_state=robot_state,
                static_obs_input=lidar_obs,
                dyn_obs_input=dyn_obs,
                target_dir=goal_dir_tensor
            )
        
        # ENU → NED (no filtering, raw model output)
        vel_ned = np.array([
            vel_enu_out[0],
            -vel_enu_out[1],
            -vel_enu_out[2]
        ])
        
        return vel_ned
    
    def navigate_to_goal(self, goal: np.ndarray, timeout: float = 60.0,
                          altitude: float = None) -> dict:
        """
        Navigate using PURE RL.
        
        - Model controls XYZ
        - Only yaw is externally controlled (training assumption)
        - NO altitude correction
        - NO collision recovery
        - NO smoothing
        """
        print(f"\n🎯 Goal: [{goal[0]:.1f}, {goal[1]:.1f}]")
        print("Mode: Pure RL (model controls XYZ)")
        
        self.reset_drone()
        z_target = altitude if altitude is not None else DEFAULT_FLIGHT_HEIGHT
        self.takeoff(z_target)
        
        start_time = time.time()
        start_pos, _, _, start_z, _ = self.get_state()
        
        success = False
        collision = False
        path = [start_pos.copy()]
        
        while True:
            elapsed = time.time() - start_time
            
            if elapsed > timeout:
                print(f"\n⏱️ Timeout")
                break
            
            if self.check_collision():
                collision = True
                print(f"\n💥 Collision at {elapsed:.1f}s")
                break
            
            position, velocity, yaw, z, orientation = self.get_state()
            path.append(position.copy())
            
            dist = np.linalg.norm(goal[:2] - position[:2])
            if dist < GOAL_THRESHOLD:
                success = True
                print(f"\n🏁 Goal reached in {elapsed:.1f}s")
                break
            
            lidar_obs, min_obs = self.process_lidar(position, goal, orientation)
            
            goal_3d = np.array([goal[0], goal[1], z_target])
            vel_cmd = self.compute_action(position, velocity, goal_3d, lidar_obs, z)
            
            # Yaw toward goal (TRAINING ASSUMPTION: drone faces goal)
            goal_dir = goal[:2] - position
            yaw_deg = np.degrees(np.arctan2(goal_dir[1], goal_dir[0]))
            
            # RAW model output - no filtering
            self.client.moveByVelocityAsync(
                float(vel_cmd[0]),
                float(vel_cmd[1]),
                float(vel_cmd[2]),  # Model controls Z
                duration=1.0/CONTROL_FREQ,
                drivetrain=airsim.DrivetrainType.MaxDegreeOfFreedom,
                yaw_mode=airsim.YawMode(is_rate=False, yaw_or_rate=yaw_deg)
            )
            
            if int(elapsed * 5) % 5 == 0:
                print(f"   D:{dist:5.1f}m Z:{-z:4.1f}m V:[{vel_cmd[0]:+.1f},{vel_cmd[1]:+.1f},{vel_cmd[2]:+.2f}] Obs:{min_obs:.1f}m", end='\r')
            
            time.sleep(1.0 / CONTROL_FREQ)
        
        self.client.moveByVelocityAsync(0, 0, 0, 1).join()
        
        total_time = time.time() - start_time
        path_len = sum(np.linalg.norm(np.array(path[i+1]) - np.array(path[i])) 
                       for i in range(len(path)-1))
        opt_len = np.linalg.norm(goal[:2] - start_pos[:2])
        eff = (opt_len / path_len * 100) if path_len > 0 else 0
        
        print("\n" + "-"*40)
        print(f"{'✅ SUCCESS' if success else ('💥 COLLISION' if collision else '⏱️ TIMEOUT')}")
        print(f"Time: {total_time:.1f}s | Path: {path_len:.1f}m | Optimal: {opt_len:.1f}m | Eff: {eff:.0f}%")
        
        return {
            'success': success,
            'collision': collision,
            'time': total_time,
            'path_length': path_len,
            'optimal_length': opt_len,
            'efficiency': eff
        }
    
    def run_mission(self, waypoints: list, altitude: float = None) -> dict:
        """Run multi-waypoint mission with NO recovery logic."""
        print("\n" + "="*60)
        print("🚁 MISSION (Pure RL - No Recovery)")
        print("="*60)
        
        self.reset_drone()
        z_target = altitude if altitude is not None else DEFAULT_FLIGHT_HEIGHT
        self.takeoff(z_target)
        
        start_pos, _, _, _, _ = self.get_state()
        
        print(f"Base: [{start_pos[0]:.1f}, {start_pos[1]:.1f}]")
        print(f"Waypoints: {len(waypoints)}")
        
        results = []
        mission_start = time.time()
        
        for i, wp in enumerate(waypoints):
            print(f"\n[WP{i+1}/{len(waypoints)}] → [{wp[0]:.1f}, {wp[1]:.1f}]")
            
            result = self._navigate_continuous(np.array(wp), 60.0, z_target)
            results.append(result)
            
            if result['collision']:
                print("💥 Mission aborted - collision")
                break
        
        # Return to base
        print(f"\n[RTB] → [{start_pos[0]:.1f}, {start_pos[1]:.1f}]")
        rtb = self._navigate_continuous(start_pos, 60.0, z_target)
        results.append({**rtb, 'waypoint': 'RTB'})
        
        self.client.moveByVelocityAsync(0, 0, 0, 1).join()
        
        # Summary
        total_time = time.time() - mission_start
        successes = sum(1 for r in results if r.get('success', False))
        collisions = sum(1 for r in results if r.get('collision', False))
        
        print("\n" + "="*60)
        print(f"Mission: {successes}/{len(results)} waypoints")
        print(f"Collisions: {collisions}")
        print(f"Time: {total_time:.1f}s")
        print("="*60)
        
        return {
            'waypoints_reached': successes,
            'total_waypoints': len(results),
            'collisions': collisions,
            'time': total_time,
            'results': results
        }
    
    def _navigate_continuous(self, goal: np.ndarray, timeout: float,
                              z_target: float) -> dict:
        """Navigate without reset - for mission waypoints."""
        start_time = time.time()
        start_pos, _, _, _, _ = self.get_state()
        
        success = False
        collision = False
        path_len = 0.0
        last_pos = start_pos.copy()
        
        while True:
            elapsed = time.time() - start_time
            
            if elapsed > timeout:
                break
            
            if self.check_collision():
                collision = True
                break
            
            position, velocity, _, z, orientation = self.get_state()
            path_len += np.linalg.norm(position - last_pos)
            last_pos = position.copy()
            
            dist = np.linalg.norm(goal[:2] - position[:2])
            if dist < GOAL_THRESHOLD:
                success = True
                print(f" ✅ {elapsed:.1f}s")
                break
            
            lidar_obs, _ = self.process_lidar(position, goal, orientation)
            
            goal_3d = np.array([goal[0], goal[1], z_target])
            vel_cmd = self.compute_action(position, velocity, goal_3d, lidar_obs, z)
            
            goal_dir = goal[:2] - position
            yaw_deg = np.degrees(np.arctan2(goal_dir[1], goal_dir[0]))
            
            self.client.moveByVelocityAsync(
                float(vel_cmd[0]),
                float(vel_cmd[1]),
                float(vel_cmd[2]),
                duration=1.0/CONTROL_FREQ,
                drivetrain=airsim.DrivetrainType.MaxDegreeOfFreedom,
                yaw_mode=airsim.YawMode(is_rate=False, yaw_or_rate=yaw_deg)
            )
            
            time.sleep(1.0 / CONTROL_FREQ)
        
        return {
            'success': success,
            'collision': collision,
            'time': time.time() - start_time,
            'path_length': path_len
        }


def main():
    parser = argparse.ArgumentParser(description='NavRL AirSim - Minimal Bridge')
    parser.add_argument('--goal', nargs=2, type=float, default=[50, 0])
    parser.add_argument('--timeout', type=float, default=60)
    parser.add_argument('--altitude', type=float, default=None)
    parser.add_argument('--mission', action='store_true')
    parser.add_argument('--device', type=str, default=None)
    
    args = parser.parse_args()
    
    altitude = -abs(args.altitude) if args.altitude else None
    bridge = NavRLBridge(device=args.device)
    
    if args.mission:
        waypoints = [
            [15, 5], [25, 15], [20, 30], [5, 35], [-10, 25],
            [-20, 10], [-15, -5], [0, -15], [15, -10], [25, 5]
        ]
        bridge.run_mission(waypoints, altitude)
    else:
        bridge.navigate_to_goal(np.array(args.goal), args.timeout, altitude)


if __name__ == "__main__":
    main()
