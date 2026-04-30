"""
NavRL AirSim Bridge
====================
Bridges the Isaac Sim-trained NavRL model to AirSim simulator.

The NavRL model was trained in Isaac Sim with specific parameters.
This script ensures those parameters are preserved when running in AirSim.

CRITICAL TRAINING PARAMETERS (DO NOT CHANGE):
- MAX_RAY_LENGTH = 4.0m (LiDAR range the model expects)
- HRES_DEG = 10.0 (360/10 = 36 horizontal bins)
- VFOV_ANGLES_DEG = [-10.0, 0.0, 10.0, 20.0] (4 vertical bins)
- LiDAR tensor shape: (1, 1, 36, 4)
- Robot state shape: (1, 8)
- Output: normalized velocity [-1, 1], scale by MAX_VELOCITY

Usage:
    python navrl_airsim_bridge.py --goal 50 0
    python navrl_airsim_bridge.py --goal 30 30 --timeout 120
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
    vec_to_new_frame, vec_to_world, get_robot_state,
    MAX_RAY_LENGTH, HRES_DEG, VFOV_ANGLES_DEG,
    MAX_VELOCITY, DEFAULT_FLIGHT_HEIGHT, GOAL_THRESHOLD, CONTROL_FREQ,
)


# Altitude safety limits (NED: negative = up)
MAX_ALTITUDE = -10.0          # Don't fly above 10m
MIN_ALTITUDE = -0.5           # Don't fly below 0.5m

# NOTE: Per the NavRL paper (Eq.12 height reward), the model IS trained with real distance_z = rpos[2].
# Setting False uses the actual vertical distance, enabling the model to self-regulate altitude.
# Setting True feeds distance_z=0 (original incorrect assumption — causes altitude drift).
USE_TRAINING_DISTANCE_Z = False  # False = real distance_z (correct per paper)


# ============================================================================
# Helper functions matching Isaac Sim training (from isaac-training/scripts/utils.py)
# vec_to_new_frame, vec_to_world, get_robot_state are imported from navrl_utils.py
# ============================================================================


class NavRLAirSimBridge:
    """
    Bridge class connecting NavRL model to AirSim.
    
    The NavRL model outputs velocity commands in a goal-relative frame.
    This class handles:
    1. LiDAR data processing to match training format
    2. State representation matching training
    3. Velocity transformation from local to world frame
    """
    
    def __init__(self, device: str = None):
        """Initialize the bridge."""
        # Auto-select device
        if device is None:
            self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        else:
            self.device = torch.device(device)
        
        print("="*60)
        print("NavRL AirSim Bridge")
        print("="*60)
        print(f"Device: {self.device}")
        print(f"LiDAR Range: {MAX_RAY_LENGTH}m")
        print(f"Max Velocity: {MAX_VELOCITY} m/s")
        print(f"Control Frequency: {CONTROL_FREQ} Hz")
        print("="*60)
        
        # Load the trained agent
        print("\nLoading NavRL model...")
        self.agent = Agent(device=self.device)
        print("✅ Model loaded successfully")
        
        # Connect to AirSim
        print("\nConnecting to AirSim...")
        self.client = airsim.MultirotorClient()
        self.client.confirmConnection()
        print("✅ Connected to AirSim")
        
        # Initialize state
        self.prev_velocity_cmd = np.zeros(3)
        self.altitude_state = 'cruise'  # States: 'cruise', 'climbing', 'descending', 'holding'
        self.altitude_hold_until = 0  # Time to hold current altitude
        self.last_vel_z = 0.0  # For smoothing
        self.last_sim_time_ns = 0
        
    def reset_drone(self):
        """Reset drone to starting position and prepare for flight."""
        self.client.reset()
        time.sleep(0.5)  # Let AirSim physics settle before re-enabling API control
        self.client.enableApiControl(True)
        self.client.armDisarm(True)
        self.prev_velocity_cmd = np.zeros(3)
        self.altitude_state = 'cruise'  # States: 'cruise', 'climbing', 'descending', 'holding'
        self.altitude_hold_until = 0  # Time to hold current altitude
        self.last_vel_z = 0.0  # For smoothing

    def prepare_for_flight(self):
        """Prepare drone for flight WITHOUT resetting position.
        Use this for consecutive navigations so the drone continues
        from its current position instead of respawning to (0,0)."""
        self.client.enableApiControl(True)
        self.client.armDisarm(True)
        self.prev_velocity_cmd = np.zeros(3)
        self.altitude_state = 'cruise'
        self.altitude_hold_until = 0
        self.last_vel_z = 0.0
        
    def compute_dynamic_altitude(self, lidar_obs: torch.Tensor, current_z: float, 
                                   base_altitude: float, min_obs_dist: float) -> float:
        """
        Compute dynamic altitude adjustment based on LiDAR vertical analysis.
        
        Uses state machine to prevent bouncing:
        - 'cruise': Return to base altitude smoothly
        - 'climbing': Actively climbing to avoid obstacle
        - 'descending': Actively descending to avoid obstacle
        - 'holding': Maintain current altitude after maneuver
        
        KEY INSIGHT: The model was trained for 2D navigation and knows how to avoid
        obstacles laterally. We should only change altitude when lateral avoidance
        is NOT possible. This complements the model's learned behavior.
        
        Args:
            lidar_obs: LiDAR tensor (1, 1, 36, 4)
            current_z: Current altitude in NED (negative = up)
            base_altitude: Target base altitude in NED
            min_obs_dist: Minimum obstacle distance
            
        Returns:
            vel_z: Vertical velocity command in NED (negative = climb)
        """
        current_time = time.time()
        
        lidar_np = lidar_obs.cpu().numpy()[0, 0]  # Shape: (36, 4)
        
        # Vertical bins: 0=-10° (down), 1=0° (level), 2=+10° (up), 3=+20° (more up)
        # Front sector: bins 0-4 (toward goal direction)
        front_bins = lidar_np[0:5, :]  # Shape: (5, 4)
        
        # IMPROVED: Weighted front obstacle detection (center bins matter more)
        # Bin 0 = directly toward goal, bins 1-4 spread outward
        front_weights = np.array([1.0, 0.9, 0.7, 0.5, 0.3])  # Center weighted highest
        front_weighted = front_bins * front_weights[:, np.newaxis]
        
        # Analyze vertical layers in front (weighted max across horizontal bins)
        front_down = np.max(front_weighted[:, 0])   # -10° rays
        front_level = np.max(front_weighted[:, 1])  # 0° rays  
        front_up1 = np.max(front_weighted[:, 2])    # +10° rays
        front_up2 = np.max(front_weighted[:, 3])    # +20° rays
        
        # Use ALL vertical levels to detect obstacle (weighted)
        front_any = np.max(front_weighted)
        
        # Thresholds (inverted: high value = close obstacle)
        # More aggressive thresholds to react earlier
        OBS_THRESHOLD = 1.5  # ~2.5m actual distance (react earlier)
        CLEAR_THRESHOLD = 0.8  # ~3.2m actual distance
        SAFE_THRESHOLD = 0.3  # Very clear
        
        # Check obstacle status - MORE SENSITIVE
        obstacle_close = front_any > OBS_THRESHOLD or min_obs_dist < 3.0
        obstacle_clear = front_any < SAFE_THRESHOLD and min_obs_dist > 3.5
        
        # Check vertical escape routes
        space_above = (front_up1 < CLEAR_THRESHOLD) and (front_up2 < CLEAR_THRESHOLD)
        space_below = front_down < CLEAR_THRESHOLD
        obstacle_above = (front_up1 > OBS_THRESHOLD) or (front_up2 > OBS_THRESHOLD)
        obstacle_below = front_down > OBS_THRESHOLD
        
        # LATERAL AVOIDANCE CHECK: Model was trained 2D - it knows lateral avoidance!
        # Only use altitude if lateral avoidance is NOT possible
        left_bins = lidar_np[7:12, :]   # Left sector (bins 7-11)
        right_bins = lidar_np[25:30, :] # Right sector (bins 25-29)
        left_clear = np.max(left_bins) < CLEAR_THRESHOLD
        right_clear = np.max(right_bins) < CLEAR_THRESHOLD
        lateral_avoidance_possible = left_clear or right_clear
        
        # State machine for altitude control
        if self.altitude_state == 'holding':
            # Check if hold period is over
            if current_time > self.altitude_hold_until:
                if obstacle_clear:
                    self.altitude_state = 'cruise'
                elif obstacle_close:
                    # Need to maneuver again
                    if space_above and not obstacle_above:
                        self.altitude_state = 'climbing'
                    elif space_below and not obstacle_below:
                        self.altitude_state = 'descending'
            # While holding, maintain altitude (vel_z = 0)
            vel_z = 0.0
            
        elif self.altitude_state == 'climbing':
            if obstacle_clear:
                # Obstacle cleared - hold altitude for 2 seconds before returning
                self.altitude_state = 'holding'
                self.altitude_hold_until = current_time + 2.0
                vel_z = 0.0
            elif obstacle_close and space_above:
                # Still climbing
                vel_z = -1.5  # Climb (negative = up in NED)
            else:
                # Can't climb anymore or obstacle passed - hold
                self.altitude_state = 'holding'
                self.altitude_hold_until = current_time + 1.5
                vel_z = 0.0
                
        elif self.altitude_state == 'descending':
            if obstacle_clear:
                # Obstacle cleared - hold altitude
                self.altitude_state = 'holding'
                self.altitude_hold_until = current_time + 2.0
                vel_z = 0.0
            elif obstacle_close and space_below:
                # Still descending
                vel_z = 1.5  # Descend (positive = down in NED)
            else:
                # Can't descend anymore - hold
                self.altitude_state = 'holding'
                self.altitude_hold_until = current_time + 1.5
                vel_z = 0.0
                
        else:  # 'cruise' state
            if obstacle_close:
                # CRITICAL FIX: The model was trained 2D but may not react fast enough
                # in 3D environments. We need to be more aggressive with altitude changes.
                #
                # Previous approach trusted lateral avoidance too much - disabled.
                # Now: Always climb when obstacle is close, regardless of lateral clearance.
                # The model can still steer laterally while we handle altitude.
                
                if min_obs_dist < 1.5:
                    # VERY close - emergency climb!
                    self.altitude_state = 'climbing'
                    vel_z = -2.0  # Fast climb
                elif space_above and not obstacle_above:
                    self.altitude_state = 'climbing'
                    vel_z = -1.5
                elif space_below and not obstacle_below:
                    self.altitude_state = 'descending'
                    vel_z = 1.5
                else:
                    # No clear path - try climbing anyway (safer for UAV)
                    self.altitude_state = 'climbing'
                    vel_z = -1.0
            else:
                # Return to base altitude SLOWLY
                alt_error = base_altitude - current_z
                vel_z = np.clip(alt_error * 0.5, -0.8, 0.8)  # Slower return
        
        # SAFETY LIMITS: Prevent flying too high or too low
        if current_z < MAX_ALTITUDE and vel_z < 0:  # Trying to climb above max
            vel_z = 0.0
            self.altitude_state = 'holding'
        elif current_z > MIN_ALTITUDE and vel_z > 0:  # Trying to descend below min
            vel_z = 0.0
            self.altitude_state = 'holding'
        
        # ADAPTIVE SMOOTHING: Less smoothing when actively avoiding obstacles
        # More aggressive smoothing when cruising, less when avoiding
        if self.altitude_state == 'cruise':
            smoothing = 0.7  # Smooth return to base altitude
        else:
            smoothing = 0.3  # Quick response for obstacle avoidance
        
        vel_z_smooth = smoothing * self.last_vel_z + (1 - smoothing) * vel_z
        self.last_vel_z = vel_z_smooth
        
        return vel_z_smooth
        
    def takeoff(self, altitude: float = None):
        """
        Take off to specified altitude.
        
        Args:
            altitude: Target altitude in NED (negative = up). Default: DEFAULT_FLIGHT_HEIGHT
        """
        if altitude is None:
            altitude = DEFAULT_FLIGHT_HEIGHT
        print(f"\nTaking off to altitude {abs(altitude):.1f}m...")
        # Only call takeoffAsync if the drone is currently on the ground.
        # LandedState: 0=Unknown, 1=Landed, 2=Flying
        try:
            state = self.client.getMultirotorState()
            if state.landed_state != 1:  # not Landed → already flying
                print("  (already airborne — skipping takeoff, moving to altitude)")
            else:
                self.client.takeoffAsync().join()
        except Exception:
            self.client.takeoffAsync().join()
        self.client.moveToZAsync(altitude, 2).join()
        print("✅ Ready for navigation")
        
    def get_drone_state(self) -> tuple:
        """
        Get current drone state from AirSim.
        
        Returns:
            position: np.array [x, y] in meters
            velocity: np.array [vx, vy, vz] in m/s (NED)
            yaw: float in radians
            z: float altitude (NED)
            orientation: airsim.Quaternionr
        """
        state = self.client.getMultirotorState()
        self.last_sim_time_ns = state.timestamp
        pos = state.kinematics_estimated.position
        vel = state.kinematics_estimated.linear_velocity
        orientation = state.kinematics_estimated.orientation
        
        _, _, yaw = airsim.to_eularian_angles(orientation)
        
        position = np.array([pos.x_val, pos.y_val])
        velocity = np.array([vel.x_val, vel.y_val, vel.z_val])
        
        return position, velocity, yaw, pos.z_val, orientation
    
    def check_collision(self) -> bool:
        """Check if drone has collided."""
        collision_info = self.client.simGetCollisionInfo()
        if collision_info.has_collided:
            # AirSim timestamps are in nanoseconds (sim clock)
            collision_age_ns = self.last_sim_time_ns - collision_info.time_stamp
            return collision_age_ns < 0.5e9  # 0.5 seconds in nanoseconds
        return False
    
    def process_lidar(self, position: np.ndarray, yaw: float, goal: np.ndarray, orientation=None) -> tuple:
        """
        Process AirSim LiDAR data into NavRL model format.
        
        SIMPLIFIED: Since drone faces the goal, body-frame LiDAR bin 0 = toward goal.
        We just need to convert NED to ENU and handle the bin ordering.
        
        Now handling GRAVITY ALIGNMENT to match Isaac Sim!
        
        Args:
            position: Current [x, y] position (NED)
            yaw: Current heading in radians (drone faces goal)
            goal: Target [x, y] position (NED)
            orientation: airsim.Quaternionr (optional, needed for gravity alignment)
        """
        lidar_data = self.client.getLidarData(lidar_name="LidarSensor1", vehicle_name="Drone1")
        
        num_h = int(360 / HRES_DEG)  # 36 horizontal bins
        num_v = len(VFOV_ANGLES_DEG)  # 4 vertical bins
        
        # Initialize with max range (no obstacle)
        range_matrix = np.full((num_h, num_v), MAX_RAY_LENGTH, dtype=np.float32)
        min_obstacle_dist = MAX_RAY_LENGTH
        
        if len(lidar_data.point_cloud) >= 3:
            points = np.array(lidar_data.point_cloud).reshape(-1, 3)
            
            # Points are in vehicle BODY frame (NED convention in general context, but let's be careful)
            # x=forward, y=right, z=down relative to drone body.
            
            # GRAVITY ALIGNMENT: 
            # We need to rotate these points by the drone's orientation to get World Frame,
            # then rotate back by Yaw only to get "Gravity-Aligned Heading Frame".
            
            if orientation is not None:
                # Convert quaternion to rotation matrix
                q = orientation
                # Scipy-style quaternion [x, y, z, w]
                # AirSim quaternion is [w, x, y, z] - Wait, check documentation. 
                # AirSim: w_val, x_val, y_val, z_val
                
                # Manual rotation using efficient formula or simplified assumption
                # Since we don't have scipy, let's use a simplified approach
                # Rotate Body -> World (Full Quaternion)
                # Rotate World -> Aligned (Inverse Yaw)
                
                # Easier: Get Pitch and Roll from quaternion
                pitch, roll, _ = airsim.to_eularian_angles(q)
                
                # Construct rotation matrix for Roll and Pitch ONLY (Body -> Desired Frame)
                # Note: Correct order depends on extrinsic/intrinsic.
                # AirSim is usually Yaw-Pitch-Roll (ZYX).
                # To "undo" roll and pitch, we want to transform Body points to Intermediate frame.
                
                # TRAINING CODE ANALYSIS - CRITICAL INSIGHT:
                # In Isaac Sim training:
                # 1. LiDAR has attach_yaw_only=True (follows yaw, gravity-aligned)
                # 2. Drone always FACES THE GOAL (yaw = atan2(goal_y-pos_y, goal_x-pos_x))
                # 3. Therefore bin 0 = drone forward = toward goal
                # 4. Model LEARNED that bin 0 = goal direction
                #
                # In AirSim:
                # 1. Drone yaw is NOT controlled to face goal
                # 2. LiDAR is in body frame
                # 3. We need to transform to GOAL DIRECTION frame so bin 0 = toward goal
                #    This is what the model expects!
                #
                # Solution: Transform LiDAR to GOAL FRAME, not just gravity-align
                
                # Step 1: Transform body points to world frame (full quaternion rotation)
                q_w, q_x, q_y, q_z = q.w_val, q.x_val, q.y_val, q.z_val
                
                s = 1.0 / (q_w**2 + q_x**2 + q_y**2 + q_z**2)
                R = np.array([
                    [1 - 2*s*(q_y**2 + q_z**2),     2*s*(q_x*q_y - q_z*q_w),     2*s*(q_x*q_z + q_y*q_w)],
                    [2*s*(q_x*q_y + q_z*q_w),       1 - 2*s*(q_x**2 + q_z**2),   2*s*(q_y*q_z - q_x*q_w)],
                    [2*s*(q_x*q_z - q_y*q_w),       2*s*(q_y*q_z + q_x*q_w),     1 - 2*s*(q_x**2 + q_y**2)]
                ])
                
                points_world = points @ R.T  # Body -> World
                
                # Step 2: Rotate by NEGATIVE GOAL ANGLE to get GOAL FRAME
                # This makes X axis point toward goal, matching training expectation
                # Goal direction in world NED frame
                goal_dir = np.array([goal[0] - position[0], goal[1] - position[1]])
                goal_angle = np.arctan2(goal_dir[1], goal_dir[0])  # Angle to goal in world
                
                # Rotate world -> goal frame (X axis = toward goal)
                # Rotation by -goal_angle makes goal direction become +X axis
                cg = np.cos(-goal_angle)
                sg = np.sin(-goal_angle)
                R_goal_inv = np.array([
                    [cg, -sg, 0],
                    [sg, cg, 0],
                    [0, 0, 1]
                ])
                
                points_aligned = points_world @ R_goal_inv.T
                
                x_aligned = points_aligned[:, 0]
                y_aligned = points_aligned[:, 1]
                z_aligned = points_aligned[:, 2]
                
            else:
                # Fallback to body frame (legacy behavior)
                x_aligned = points[:, 0]
                y_aligned = points[:, 1]
                z_aligned = points[:, 2]

            # Now convert to ENU for binning
            # Aligned Frame Is NED-like (X=Forward-Level, Y=Right-Level, Z=Down-Gravity)
            
            # Convert to ENU for angles
            # X_enu = X_ned (Forward)
            # Y_enu = -Y_ned (Left)
            # Z_enu = -Z_ned (Up)
            
            x_body = x_aligned
            y_body = -y_aligned
            z_body = -z_aligned
            
            # Calculate distances
            dists = np.sqrt(x_body**2 + y_body**2 + z_body**2)
            
            # Filter valid points
            valid_mask = (dists > 0.1) & (dists < MAX_RAY_LENGTH)
            
            if np.any(valid_mask):
                x_valid = x_body[valid_mask]
                y_valid = y_body[valid_mask]
                z_valid = z_body[valid_mask]
                dists_valid = dists[valid_mask]
                
                min_obstacle_dist = np.min(dists_valid)
                
                # Calculate angles in body frame
                # arctan2(y, x): 0° when y=0,x>0 (forward), 90° when y>0,x=0 (left)
                # Model convention: Bin 0 = Front (0°), Bin 9 = 90°, Bin 18 = Back (180°)
                h_angles = np.degrees(np.arctan2(y_valid, x_valid))
                
                # NO SHIFT NEEDED - Bin 0 is front, matching arctan2 convention
                h_angles = (h_angles + 360) % 360  # Just normalize to [0, 360)
                
                h_idxs = (h_angles / HRES_DEG).astype(int) % num_h
                
                # Vertical angle (elevation)
                flat_dists = np.sqrt(x_valid**2 + y_valid**2)
                v_angles = np.degrees(np.arctan2(z_valid, flat_dists))
                
                # ===== FULLY VECTORIZED binning =====
                # Broadcast: compute distance from each point's v_angle to each VFOV bin
                # v_angles shape: (N,), VFOV shape: (4,) => diff shape: (N, 4)
                vfov_arr = np.array(VFOV_ANGLES_DEG)
                v_diffs = np.abs(v_angles[:, np.newaxis] - vfov_arr[np.newaxis, :])  # (N, 4)
                v_idxs = np.argmin(v_diffs, axis=1)  # (N,) closest vertical bin per point
                
                # For each (h_idx, v_idx) pair, keep the minimum distance
                # Use np.minimum.at for scatter-reduce
                np.minimum.at(range_matrix, (h_idxs, v_idxs), dists_valid)
        
        # ===== PITCH COMPENSATION: Vertical Bin Extrapolation =====
        # When the drone pitches forward, the LiDAR's physical coverage shifts
        # downward. The upper vertical bins (+10°, +20°) may receive no data
        # because no body-frame rays reach those world-frame elevations.
        #
        # In training (Isaac Sim), attach_yaw_only=True kept the sensor level.
        # The model EXPECTS upper bins to contain obstacle data if a tall building
        # is ahead. Empty upper bins = "clear above" to the model.
        #
        # Fix: If an upper bin is empty but the bin below it detected an obstacle,
        # propagate the obstacle detection upward. This is conservative (may
        # cause unnecessary avoidance) but prevents the "fly into building" error.
        #
        # Only applies when pitch > 5° — at low pitch, the coverage gap is
        # negligible and extrapolation would add noise.
        if orientation is not None:
            pitch, _, _ = airsim.to_eularian_angles(orientation)
            pitch_deg = abs(np.degrees(pitch))
            
            if pitch_deg > 5.0:
                # Vectorized: propagate obstacle data from lower to upper bins
                # where upper bins have no data (coverage gap from pitch)
                for v in range(1, num_v):
                    empty_upper = range_matrix[:, v] >= MAX_RAY_LENGTH - 0.1
                    has_lower = range_matrix[:, v-1] < MAX_RAY_LENGTH - 0.5
                    fill_mask = empty_upper & has_lower
                    range_matrix[fill_mask, v] = range_matrix[fill_mask, v-1]
        
        # CRITICAL: Match training data format - INVERT distances
        range_matrix = np.maximum(range_matrix, 0.1)
        range_matrix = MAX_RAY_LENGTH - range_matrix
        
        # Convert to tensor with shape (1, 1, 36, 4)
        range_tensor = torch.tensor(range_matrix, dtype=torch.float32, device=self.device)
        range_tensor = range_tensor.unsqueeze(0).unsqueeze(0)
        
        return range_tensor, min_obstacle_dist
    
    def compute_action(self, position: np.ndarray, velocity: np.ndarray, 
                       goal: np.ndarray, lidar_obs: torch.Tensor,
                       current_z: float,
                       min_obstacle_dist: float = MAX_RAY_LENGTH) -> np.ndarray:
        """
        Compute velocity command using NavRL model with FULL 3D state.
        
        Now uses proper 3D state matching Isaac Sim training:
        - Full 3D relative position to goal
        - Real vertical distance (distance_z) instead of 0
        - Full 3D velocity
        
        Args:
            position: Current [x, y] position in NED (promoted to 3D internally with current_z)
            velocity: Current [vx, vy, vz] velocity in NED
            goal: Target [x, y, z] position (NED, z is target altitude)
            lidar_obs: LiDAR tensor (goal-relative from process_lidar)
            current_z: Current altitude in NED (negative = above ground)
            min_obstacle_dist: Distance to closest obstacle
            
        Returns:
            velocity_ned: np.array [vx, vy, vz] in AirSim NED frame
        """
        # =============================================
        # Convert NED -> ENU for model
        # AirSim NED: X=forward, Y=right, Z=down
        # Isaac Sim ENU: X=forward, Y=left, Z=up
        # =============================================
        
        # Full 3D position in ENU
        pos_enu = np.array([position[0], -position[1], -current_z])  # Z: NED down -> ENU up
        
        # Full 3D velocity in ENU (NED vz -> ENU vz by negation)
        vel_enu = np.array([velocity[0], -velocity[1], -velocity[2]])
        
        # Goal in ENU (goal[2] is NED altitude, negative = above ground)
        goal_enu = np.array([goal[0], -goal[1], -goal[2]])  # Z: NED -> ENU
        
        # Target direction in ENU (full 3D)
        target_dir_enu = goal_enu - pos_enu
        
        # Get FULL 3D robot state (matching Isaac Sim training exactly)
        # distance_z=None: use real vertical distance (hybrid mode)
        # distance_z=0.0: match training assumption (if USE_TRAINING_DISTANCE_Z)
        robot_state = get_robot_state(
            pos=pos_enu,
            goal=goal_enu, 
            vel=vel_enu,
            target_dir=target_dir_enu,
            device=self.device,
            distance_z=0.0 if USE_TRAINING_DISTANCE_Z else None
        )
        
        # Dynamic obstacles (not used in this deployment)
        dyn_obs = torch.zeros((1, 1, 5, 10), dtype=torch.float32, device=self.device)
        
        # Goal direction for network (2D horizontal, Z=0 for frame transform)
        target_dir_2d = np.array([target_dir_enu[0], target_dir_enu[1], 0.0])
        norm_dir = np.linalg.norm(target_dir_2d)
        if norm_dir < 1e-6:
            norm_dir = 1.0
        goal_dir_normalized = target_dir_2d / norm_dir
        
        goal_dir_tensor = torch.tensor(
            goal_dir_normalized, 
            dtype=torch.float32, 
            device=self.device
        ).unsqueeze(0).unsqueeze(0)
        
        # Get action from model
        # Model outputs velocity in ENU world frame (via internal vec_to_world transform)
        with torch.no_grad():
            velocity_enu_out = self.agent.plan(
                robot_state=robot_state,
                static_obs_input=lidar_obs,
                dyn_obs_input=dyn_obs,
                target_dir=goal_dir_tensor
            )
        
        # =============================================
        # Convert ENU world -> NED world for AirSim
        # =============================================
        vel_ned = np.zeros(3)
        vel_ned[0] = velocity_enu_out[0]       # X same (forward)
        vel_ned[1] = -velocity_enu_out[1]      # Y inverted (ENU left -> NED right)
        vel_ned[2] = -velocity_enu_out[2]      # Z inverted (ENU up -> NED down)
        
        return vel_ned
    
    def navigate_to_goal(self, goal: np.ndarray, timeout: float = 60.0,
                          target_altitude: float = None) -> dict:
        """
        Navigate drone to goal position using NavRL model.
        
        Args:
            goal: Target [x, y] position in meters
            timeout: Maximum time allowed (seconds)
            target_altitude: Target altitude in NED (negative = up). None = maintain takeoff altitude.
            
        Returns:
            dict with navigation results
        """
        print(f"\n🎯 Navigating to goal: [{goal[0]:.1f}, {goal[1]:.1f}]")
        
        self.prepare_for_flight()
        self.takeoff()
        
        start_time = time.time()
        start_pos, _, _, start_z, _ = self.get_drone_state()
        
        # Target altitude: use provided value, or maintain takeoff altitude
        z_target = target_altitude if target_altitude is not None else start_z
        
        success = False
        collision = False
        path = [start_pos.copy()]
        
        print("✅ Ready for navigation")
        
        while True:
            elapsed = time.time() - start_time
            
            # Check timeout
            if elapsed > timeout:
                print(f"\n⏱️ Timeout after {timeout}s")
                break
            
            # Check collision
            if self.check_collision():
                collision = True
                print("\n💥 Collision detected!")
                break
            
            # Get current state
            position, velocity, yaw, z, orientation = self.get_drone_state()
            path.append(position.copy())
            
            # Check if goal reached (2D distance)
            dist_to_goal = np.linalg.norm(goal[:2] - position[:2])
            if dist_to_goal < GOAL_THRESHOLD:
                success = True
                print(f"\n🏁 Goal reached in {elapsed:.1f}s!")
                break
            
            # Get LiDAR observation (already converted to ENU inside)
            lidar_obs, min_obs_dist = self.process_lidar(position, yaw, goal, orientation=orientation)
            
            # Compute action from model (handles X/Y navigation)
            goal_3d = np.array([goal[0], goal[1], z_target])
            velocity_cmd = self.compute_action(position, velocity, goal_3d, lidar_obs, 
                                               current_z=z,
                                               min_obstacle_dist=min_obs_dist)
            
            # Model controls X/Y
            vel_x = velocity_cmd[0]
            vel_y = velocity_cmd[1]
            
            # DYNAMIC altitude control - climb/descend to avoid obstacles
            vel_z = self.compute_dynamic_altitude(lidar_obs, z, z_target, min_obs_dist)
            
            # Calculate desired yaw - FACE THE GOAL
            # Model was trained with LiDAR bin 0 = toward goal
            # By facing the goal, body-frame LiDAR naturally aligns with goal-relative frame
            goal_dir = goal[:2] - position
            desired_yaw = np.arctan2(goal_dir[1], goal_dir[0])
            yaw_degrees = np.degrees(desired_yaw)
            
            # Execute action with yaw control
            self.client.moveByVelocityAsync(
                float(vel_x), 
                float(vel_y), 
                float(vel_z),
                duration=1.0/CONTROL_FREQ,
                drivetrain=airsim.DrivetrainType.MaxDegreeOfFreedom,
                yaw_mode=airsim.YawMode(is_rate=False, yaw_or_rate=yaw_degrees)
            )
            
            # Status update
            if int(elapsed * 10) % 10 == 0:  # Every ~1 second
                print(f"   Dist: {dist_to_goal:.1f}m | Alt: {-z:.1f}m | "
                      f"Vel: [{vel_x:.1f}, {vel_y:.1f}, {vel_z:.2f}]", end='\r')
            
            time.sleep(1.0 / CONTROL_FREQ)
        
        # Stop the drone
        self.client.moveByVelocityAsync(0, 0, 0, 1).join()
        
        # Calculate results
        total_time = time.time() - start_time
        path_length = sum(np.linalg.norm(np.array(path[i+1]) - np.array(path[i])) 
                         for i in range(len(path)-1))
        optimal_length = np.linalg.norm(goal[:2] - start_pos[:2])
        efficiency = (optimal_length / path_length * 100) if path_length > 0 else 0
        
        result = {
            'success': success,
            'collision': collision,
            'time': total_time,
            'path_length': path_length,
            'optimal_length': optimal_length,
            'efficiency': efficiency,
            'goal': goal.tolist()
        }
        
        # Print summary
        print("\n" + "="*40)
        print("Navigation Summary")
        print("="*40)
        print(f"Status: {'✅ SUCCESS' if success else ('💥 COLLISION' if collision else '⏱️ TIMEOUT')}")
        print(f"Time: {total_time:.1f}s")
        print(f"Path length: {path_length:.1f}m")
        print(f"Optimal length: {optimal_length:.1f}m")
        print(f"Efficiency: {efficiency:.1f}%")
        
        return result
    
    def run_test_sequence(self, goals: list) -> list:
        """Run navigation to multiple goals."""
        results = []
        
        print("\n" + "="*60)
        print(f"Running test sequence with {len(goals)} goals")
        print("="*60)
        
        for i, goal in enumerate(goals):
            print(f"\n[{i+1}/{len(goals)}] Goal: {goal}")
            result = self.navigate_to_goal(np.array(goal))
            results.append(result)
        
        # Summary
        successes = sum(1 for r in results if r['success'])
        collisions = sum(1 for r in results if r['collision'])
        
        print("\n" + "="*60)
        print("Test Sequence Complete")
        print("="*60)
        print(f"Success rate: {successes}/{len(goals)} ({100*successes/len(goals):.1f}%)")
        print(f"Collisions: {collisions}")
        
        return results
    
    def run_multi_waypoint_mission(self, waypoints: list, return_to_base: bool = True,
                                    timeout_per_waypoint: float = 60.0,
                                    target_altitude: float = None) -> dict:
        """
        Run a complete multi-waypoint mission with return to base.
        
        This is the HARD TEST: Navigate through multiple waypoints sequentially,
        then return to the starting position.
        
        Args:
            waypoints: List of [x, y] waypoint positions
            return_to_base: If True, return to start after completing all waypoints
            timeout_per_waypoint: Timeout for each waypoint (seconds)
            target_altitude: Target altitude in NED (negative = up). None = use default.
            
        Returns:
            dict with complete mission results
        """
        print("\n" + "="*70)
        print("🚁 MULTI-WAYPOINT MISSION WITH RETURN TO BASE")
        print("="*70)
        
        # Get starting position and takeoff
        self.reset_drone()
        altitude = target_altitude if target_altitude is not None else DEFAULT_FLIGHT_HEIGHT
        self.takeoff(altitude)
        start_pos, _, _, start_z, _ = self.get_drone_state()
        base_position = start_pos.copy()
        mission_altitude = start_z  # Use actual altitude after takeoff
        
        print(f"\n📍 BASE POSITION: [{base_position[0]:.1f}, {base_position[1]:.1f}]")
        print(f"📍 ALTITUDE: {abs(mission_altitude):.1f}m")
        print(f"📍 WAYPOINTS: {len(waypoints)}")
        for i, wp in enumerate(waypoints):
            print(f"   WP{i+1}: [{wp[0]:.1f}, {wp[1]:.1f}]")
        if return_to_base:
            print(f"   RTB: [{base_position[0]:.1f}, {base_position[1]:.1f}]")
        
        mission_start_time = time.time()
        results = []
        total_distance = 0.0
        optimal_distance = 0.0
        current_pos = base_position.copy()
        
        # Navigate to each waypoint
        for i, waypoint in enumerate(waypoints):
            wp = np.array(waypoint)
            print(f"\n{'='*50}")
            print(f"🎯 WAYPOINT {i+1}/{len(waypoints)}: [{wp[0]:.1f}, {wp[1]:.1f}]")
            print(f"{'='*50}")
            
            # Calculate optimal distance from current position
            opt_dist = np.linalg.norm(wp - current_pos)
            optimal_distance += opt_dist
            
            # Navigate to waypoint (don't reset - continue from current position)
            result = self._navigate_continuous(wp, timeout_per_waypoint, target_altitude=mission_altitude)
            results.append({
                'waypoint': i + 1,
                'goal': wp.tolist(),
                **result
            })
            
            if result['success']:
                total_distance += result['path_length']
                current_pos = wp.copy()
                print(f"✅ Waypoint {i+1} reached!")
            else:
                print(f"❌ Failed to reach waypoint {i+1}")
                if result['collision']:
                    print("💥 COLLISION - Recovering altitude and continuing...")
                    total_distance += result['path_length']
                    # Recover altitude before continuing
                    self._recover_altitude(mission_altitude)
                    # Update position to current actual position and continue
                    current_pos, _, _, _, _ = self.get_drone_state()
        
        # Return to base (always attempt if requested)
        rtb_result = None
        if return_to_base:
            print(f"\n{'='*50}")
            print(f"🏠 RETURN TO BASE: [{base_position[0]:.1f}, {base_position[1]:.1f}]")
            print(f"{'='*50}")
            
            # Get current position in case of previous collision
            current_pos, _, _, _, _ = self.get_drone_state()
            opt_dist = np.linalg.norm(base_position - current_pos)
            optimal_distance += opt_dist
            
            rtb_result = self._navigate_continuous(base_position, timeout_per_waypoint, target_altitude=mission_altitude)
            rtb_result['waypoint'] = 'RTB'
            rtb_result['goal'] = base_position.tolist()
            results.append(rtb_result)
            
            if rtb_result['success']:
                total_distance += rtb_result['path_length']
                print("✅ Returned to base!")
            else:
                print("❌ Failed to return to base")
        
        # Stop the drone
        self.client.moveByVelocityAsync(0, 0, 0, 1).join()
        
        # Mission summary
        mission_time = time.time() - mission_start_time
        waypoints_reached = sum(1 for r in results if r['success'] and r.get('waypoint') != 'RTB')
        total_waypoints = len(waypoints)
        mission_success = waypoints_reached == total_waypoints
        rtb_success = rtb_result['success'] if rtb_result else False
        full_mission_success = mission_success and (rtb_success if return_to_base else True)
        collisions = sum(1 for r in results if r.get('collision', False))
        efficiency = (optimal_distance / total_distance * 100) if total_distance > 0 else 0
        
        print("\n" + "="*70)
        print("📊 MISSION SUMMARY")
        print("="*70)
        print(f"Mission Status: {'✅ COMPLETE SUCCESS' if full_mission_success else '⚠️ PARTIAL' if mission_success else '❌ FAILED'}")
        print(f"Waypoints Reached: {waypoints_reached}/{total_waypoints}")
        if return_to_base:
            print(f"Return to Base: {'✅ YES' if rtb_success else '❌ NO'}")
        print(f"Total Time: {mission_time:.1f}s")
        print(f"Total Distance: {total_distance:.1f}m")
        print(f"Optimal Distance: {optimal_distance:.1f}m")
        print(f"Path Efficiency: {efficiency:.1f}%")
        print(f"Collisions: {collisions}")
        print("="*70)
        
        return {
            'mission_success': full_mission_success,
            'waypoints_reached': waypoints_reached,
            'total_waypoints': total_waypoints,
            'rtb_success': rtb_success,
            'total_time': mission_time,
            'total_distance': total_distance,
            'optimal_distance': optimal_distance,
            'efficiency': efficiency,
            'collisions': collisions,
            'base_position': base_position.tolist(),
            'waypoint_results': results
        }
    
    def _recover_altitude(self, target_altitude: float = None):
        """
        Recover to target altitude after collision.
        The drone may have dropped altitude during collision.
        
        Args:
            target_altitude: Target altitude in NED. Default: DEFAULT_FLIGHT_HEIGHT
        """
        _, _, _, z_current, _ = self.get_drone_state()
        z_target = target_altitude if target_altitude is not None else DEFAULT_FLIGHT_HEIGHT
        
        # Check if we need to recover
        alt_error = abs(z_current - z_target)
        if alt_error < 0.3:  # Within 30cm is fine
            return
        
        print(f"   ⬆️ Recovering altitude: {-z_current:.1f}m -> {-z_target:.1f}m")
        
        # Simple climb/descend to target altitude
        for _ in range(40):  # 2 seconds max
            _, _, _, z, _ = self.get_drone_state()
            alt_error = z_target - z
            
            if abs(alt_error) < 0.3:
                break
            
            vel_z = np.clip(alt_error * 1.5, -2.0, 2.0)
            self.client.moveByVelocityAsync(0, 0, float(vel_z), 0.1).join()
        
        print(f"   ✅ Altitude recovered")
    
    def _navigate_continuous(self, goal: np.ndarray, timeout: float = 60.0,
                               target_altitude: float = None) -> dict:
        """
        Navigate to goal WITHOUT resetting drone position.
        Used for multi-waypoint missions.
        
        Altitude: Model was trained 2D (distance_z=0), so we use a P-controller for Z.
        Set target_altitude=None for free altitude control based on goal_z.
        """
        start_time = time.time()
        start_pos, _, _, current_z, _ = self.get_drone_state()
        
        # Target altitude: use provided value, or current altitude if None
        z_target = target_altitude if target_altitude is not None else current_z
        
        success = False
        collision = False
        path_length = 0.0
        last_pos = start_pos.copy()
        
        while True:
            elapsed = time.time() - start_time
            
            if elapsed > timeout:
                print(f"\n⏱️ Timeout")
                break
            
            if self.check_collision():
                collision = True
                print("\n💥 Collision!")
                break
            
            position, velocity, yaw, z, orientation = self.get_drone_state()
            
            # Track path length
            path_length += np.linalg.norm(position - last_pos)
            last_pos = position.copy()
            
            # 2D distance check
            dist_to_goal = np.linalg.norm(goal[:2] - position[:2])
            if dist_to_goal < GOAL_THRESHOLD:
                success = True
                break
            
            # LiDAR (already converts NED->ENU inside)
            lidar_obs, min_obs_dist = self.process_lidar(position, yaw, goal, orientation=orientation)
            
            # Obstacle proximity tracked via min_obs_dist (no 20Hz printing)
            
            # Compute action from model (handles X/Y navigation)
            goal_3d = np.array([goal[0], goal[1], z_target])
            velocity_cmd = self.compute_action(position, velocity, goal_3d, lidar_obs, 
                                               current_z=z,
                                               min_obstacle_dist=min_obs_dist)
            
            # Model controls X/Y
            vel_x_final = velocity_cmd[0]
            vel_y_final = velocity_cmd[1]
            
            # DYNAMIC altitude control - climb/descend to avoid obstacles
            vel_z_final = self.compute_dynamic_altitude(lidar_obs, z, z_target, min_obs_dist)
            
            # Yaw control - FACE THE GOAL
            # Model was trained with LiDAR bin 0 = toward goal
            # By facing the goal, body-frame LiDAR naturally aligns with goal-relative frame
            goal_dir = goal[:2] - position
            desired_yaw = np.arctan2(goal_dir[1], goal_dir[0])
            yaw_degrees = np.degrees(desired_yaw)
            
            self.client.moveByVelocityAsync(
                float(vel_x_final), 
                float(vel_y_final), 
                float(vel_z_final),
                duration=1.0/CONTROL_FREQ,
                drivetrain=airsim.DrivetrainType.MaxDegreeOfFreedom,
                yaw_mode=airsim.YawMode(is_rate=False, yaw_or_rate=yaw_degrees)
            )
            
            # Status
            if int(elapsed * 10) % 10 == 0:
                print(f"   Dist: {dist_to_goal:.1f}m | Alt: {-z:.1f}m | "
                      f"Vel: [{vel_x_final:.1f}, {vel_y_final:.1f}, {vel_z_final:.2f}]", end='\r')
            
            time.sleep(1.0 / CONTROL_FREQ)
        
        print()  # Clear status line
        
        return {
            'success': success,
            'collision': collision,
            'time': time.time() - start_time,
            'path_length': path_length,
            'optimal_length': np.linalg.norm(goal[:2] - start_pos[:2])
        }
    
    def test_obstacle_avoidance(self, goal: np.ndarray, timeout: float = 60.0) -> dict:
        """
        Test obstacle avoidance with detailed feedback.
        
        This test shows:
        - Real-time LiDAR readings
        - Model's velocity response to obstacles
        - Whether model is avoiding or heading toward obstacles
        
        Args:
            goal: Target [x, y] position in meters
            timeout: Maximum time allowed (seconds)
            
        Returns:
            dict with test results
        """
        print("\n" + "="*70)
        print("🧪 OBSTACLE AVOIDANCE TEST")
        print("="*70)
        print(f"Goal: [{goal[0]:.1f}, {goal[1]:.1f}]")
        print("\nThis test shows detailed LiDAR and model response data.")
        print("Watch for:")
        print("  - MIN_OBS < 2.0m: Obstacle detected nearby")
        print("  - FRONT bins high: Obstacle ahead")
        print("  - Model should steer AWAY from obstacles")
        print("="*70)
        
        self.reset_drone()
        self.takeoff()
        
        z_flight = FLIGHT_HEIGHT
        start_time = time.time()
        start_pos, _, _, _, _ = self.get_drone_state()
        
        success = False
        collision = False
        close_calls = 0  # Count times obstacle was < 1.5m
        avoidance_events = 0  # Count times model steered away
        
        last_velocity = np.zeros(2)
        
        while True:
            elapsed = time.time() - start_time
            
            if elapsed > timeout:
                print(f"\n⏱️ Timeout after {timeout}s")
                break
            
            if self.check_collision():
                collision = True
                print("\n" + "!"*50)
                print("💥 COLLISION DETECTED!")
                print("!"*50)
                break
            
            position, velocity, yaw, z, orientation = self.get_drone_state()
            
            # Check goal
            dist_to_goal = np.linalg.norm(goal[:2] - position[:2])
            if dist_to_goal < GOAL_THRESHOLD:
                success = True
                print(f"\n🏁 Goal reached in {elapsed:.1f}s!")
                break
            
            # Get LiDAR with detailed analysis
            lidar_obs, min_obs_dist = self.process_lidar(position, yaw, goal, orientation=orientation)
            
            # Analyze LiDAR bins (after inversion: HIGH = close obstacle)
            # Bin 0 = Front, Bin 9 = Side, Bin 18 = Back, Bin 27 = Side
            lidar_np = lidar_obs.cpu().numpy()[0, 0]  # Shape: (36, 4)
            
            # Front bins (Centered at 0, wrapping around)
            front_bins = np.concatenate([lidar_np[34:36, :], lidar_np[0:3, :]])  # Bins 34,35,0,1,2
            front_max = np.max(front_bins)  # High = obstacle close
            
            # Left bins (Centered at 9) - in body frame +Y is left in NED
            left_bins = lidar_np[7:12, :]
            left_max = np.max(left_bins)
            
            # Right bins (Centered at 27) - in body frame -Y is right in NED  
            right_bins = lidar_np[25:30, :]
            right_max = np.max(right_bins)
            
            # Compute action - FULL 3D FREEDOM from model
            # Use start altitude as goal Z (model maintains altitude via state)
            goal_3d = np.array([goal[0], goal[1], z_flight])
            velocity_cmd = self.compute_action(position, velocity, goal_3d, lidar_obs, 
                                               current_z=z,
                                               min_obstacle_dist=min_obs_dist)
            
            # Track close calls
            if min_obs_dist < 1.5:
                close_calls += 1
            
            # Check if model is avoiding (velocity changed away from obstacle)
            vel_change = velocity_cmd[:2] - last_velocity
            if min_obs_dist < 2.0 and np.linalg.norm(vel_change) > 0.2:
                avoidance_events += 1
            last_velocity = velocity_cmd[:2].copy()
            
            # Detailed status every 0.5 seconds
            if int(elapsed * 2) % 1 == 0:
                # Determine obstacle status
                if min_obs_dist < 1.0:
                    obs_status = "🔴 VERY CLOSE"
                elif min_obs_dist < 2.0:
                    obs_status = "🟡 NEARBY"
                elif min_obs_dist < 3.0:
                    obs_status = "🟢 DETECTED"
                else:
                    obs_status = "⚪ CLEAR"
                
                # Direction indicator
                if front_max > 2.0:  # Obstacle ahead (inverted: high = close)
                    direction = "⬆️ FRONT"
                elif left_max > right_max and left_max > 1.5:
                    direction = "⬅️ LEFT"
                elif right_max > left_max and right_max > 1.5:
                    direction = "➡️ RIGHT"
                else:
                    direction = "✓ CLEAR"
                
                print(f"\r   Dist: {dist_to_goal:5.1f}m | "
                      f"Obs: {min_obs_dist:4.2f}m {obs_status} | "
                      f"Dir: {direction:8s} | "
                      f"Vel: [{velocity_cmd[0]:+5.2f}, {velocity_cmd[1]:+5.2f}, {velocity_cmd[2]:+5.2f}]   ", end='')
            
            # Yaw toward goal
            goal_dir = goal[:2] - position
            desired_yaw = np.arctan2(goal_dir[1], goal_dir[0])
            yaw_degrees = np.degrees(desired_yaw)
            
            # FULL 3D FREEDOM - no Z constraints, model controls everything!
            self.client.moveByVelocityAsync(
                float(velocity_cmd[0]), 
                float(velocity_cmd[1]), 
                float(velocity_cmd[2]),  # Model controls Z freely!
                duration=1.0/CONTROL_FREQ,
                drivetrain=airsim.DrivetrainType.MaxDegreeOfFreedom,
                yaw_mode=airsim.YawMode(is_rate=False, yaw_or_rate=yaw_degrees)
            )
            
            time.sleep(1.0 / CONTROL_FREQ)
        
        # Stop
        self.client.moveByVelocityAsync(0, 0, 0, 1).join()
        
        # Results
        total_time = time.time() - start_time
        
        print("\n\n" + "="*70)
        print("📊 OBSTACLE AVOIDANCE TEST RESULTS")
        print("="*70)
        print(f"Status: {'✅ SUCCESS' if success else ('💥 COLLISION' if collision else '⏱️ TIMEOUT')}")
        print(f"Time: {total_time:.1f}s")
        print(f"Close calls (< 1.5m): {close_calls}")
        print(f"Avoidance maneuvers: {avoidance_events}")
        
        if collision:
            print("\n⚠️  Model failed to avoid obstacle!")
            print("    Check LiDAR configuration and coordinate transforms.")
        elif close_calls > 0 and success:
            print(f"\n✅ Model successfully avoided {close_calls} close obstacles!")
        elif success:
            print("\n✅ Path was clear - no obstacles encountered.")
        
        print("="*70)
        
        return {
            'success': success,
            'collision': collision,
            'time': total_time,
            'close_calls': close_calls,
            'avoidance_events': avoidance_events
        }


def main():
    parser = argparse.ArgumentParser(description='NavRL AirSim Navigation')
    parser.add_argument('--goal', nargs=2, type=float, default=[50, 0],
                       help='Goal position [x, y] in meters')
    parser.add_argument('--timeout', type=float, default=60,
                       help='Navigation timeout in seconds')
    parser.add_argument('--altitude', type=float, default=None,
                       help='Target altitude in meters (positive value, e.g. 5 for 5m above ground). Default: 2m')
    parser.add_argument('--test', action='store_true',
                       help='Run test sequence with multiple goals')
    parser.add_argument('--mission', action='store_true',
                       help='Run multi-waypoint mission with return to base')
    parser.add_argument('--obstacle-test', action='store_true',
                       help='Run obstacle avoidance test with detailed feedback')
    parser.add_argument('--device', type=str, default=None,
                       help='Device: cuda or cpu')
    
    args = parser.parse_args()
    
    # Convert altitude to NED (negative = up)
    target_altitude = -abs(args.altitude) if args.altitude is not None else None
    
    # Initialize bridge
    bridge = NavRLAirSimBridge(device=args.device)
    
    if args.obstacle_test:
        # Run obstacle avoidance test
        goal = np.array(args.goal)
        bridge.test_obstacle_avoidance(goal, timeout=args.timeout)
    elif args.mission:
        # Run multi-waypoint mission with return to base
        # 10 waypoints scattered in a pattern
        mission_waypoints = [
            [15, 5],      # WP1: Forward-right
            [25, 15],     # WP2: Continue diagonal
            [20, 30],     # WP3: Turn left
            [5, 35],      # WP4: Continue left
            [-10, 25],    # WP5: Turn back
            [-20, 10],    # WP6: Continue back-left
            [-15, -5],    # WP7: Cross to negative Y
            [0, -15],     # WP8: Forward in negative Y
            [15, -10],    # WP9: Turn right
            [25, 5],      # WP10: Return toward start area
        ]
        bridge.run_multi_waypoint_mission(mission_waypoints, return_to_base=True,
                                          target_altitude=target_altitude)
    elif args.test:
        # Run test sequence
        test_goals = [
            [25, 0],    # Forward
            [25, 25],   # Diagonal
            [0, 30],    # Side
            [50, 0],    # Long distance
        ]
        bridge.run_test_sequence(test_goals)
    else:
        # Single navigation
        goal = np.array(args.goal)
        bridge.navigate_to_goal(goal, timeout=args.timeout, target_altitude=target_altitude)


if __name__ == "__main__":
    main()
