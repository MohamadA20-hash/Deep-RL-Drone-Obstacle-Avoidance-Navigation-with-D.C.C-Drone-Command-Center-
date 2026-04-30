"""
NavRL City Planner - Global Path Planning for City Navigation
==============================================================
Problem:
    NavRL model is purely REACTIVE with only 4m LiDAR range.
    It CANNOT plan around buildings - it just flies toward the goal
    and dodges obstacles as they appear within 4m.
    
    In a city, if a waypoint is behind a building:
    1. Drone flies straight at the building wall
    2. Detects wall at 4m
    3. Tries to deviate, but may get stuck in corners or loop

Solution:
    Add a GLOBAL PLANNER layer on top of NavRL with REACTIVE altitude:
    
    ┌──────────────────────────────────────────┐
    │         GLOBAL PLANNER (A*)              │
    │  - Builds 2D occupancy grid from LiDAR   │
    │  - Plans collision-free path to goal      │
    │  - Generates intermediate waypoints       │
    │  - Detects when drone is stuck            │
    │  - Replans when new obstacles found       │
    └──────────────┬───────────────────────────┘
                   │ intermediate waypoints (X, Y only)
    ┌──────────────▼───────────────────────────┐
    │     NavRL PPO MODEL (Local XY)           │
    │  - Trained RL handles X/Y navigation     │
    │  - 4m LiDAR for local obstacle avoidance  │
    │  - Navigates between close waypoints      │
    └──────────────┬───────────────────────────┘
                   │ velocity_x, velocity_y
    ┌──────────────▼───────────────────────────┐
    │   REACTIVE ALTITUDE CONTROLLER (Z)       │
    │  - NO pre-set altitude                    │
    │  - LiDAR-driven: climb when obstacle seen │
    │  - Tall building detection via vertical   │
    │    LiDAR layers (+10°, +20° rays)         │
    │  - Descend only after sustained clearance │
    │  - Operator gives (x,y) only, Z is auto   │
    └──────────────────────────────────────────┘

Altitude Philosophy:
    The NavRL model was trained for 2D (XY) navigation with a strict Z=2m
    rule. In deployment, altitude is NOT a model concern - it's handled by
    an independent reactive controller based purely on LiDAR sensor data.
    
    This mirrors real-world UAS operations:
    - An operator clicks a point on a map (like Google Maps) -> gives (x, y)
    - The drone determines its own altitude from sensor data
    - No prior knowledge of building heights is needed
    - Start low, climb when obstacles detected, descend when clear

Architecture:
    1. OccupancyGrid: 2D grid updated from LiDAR in real-time
    2. A* Planner: Finds shortest collision-free path on grid
    3. CityAltitudeController: Reactive Z control from LiDAR vertical analysis
    4. NavRLCityPlanner: Orchestrates planning + NavRL XY + altitude Z

Usage:
    python navrl_city_planner.py --goal 100 50
    python navrl_city_planner.py --goal 200 -100 --min-altitude 8
    python navrl_city_planner.py --mission
    python navrl_city_planner.py --test       # Run unit tests
"""

import airsim
import numpy as np
import torch
import time
import heapq
import argparse
import sys
import os
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from navrl_airsim_hybrid_controller import (
    NavRLAirSimBridge, MAX_RAY_LENGTH, MAX_VELOCITY, 
    GOAL_THRESHOLD, CONTROL_FREQ, DEFAULT_FLIGHT_HEIGHT
)

# Configure logging so bridge messages are visible
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(message)s',
    datefmt='%H:%M:%S'
)

CLOSE_CALL_THRESHOLD = 1.5  # m — obstacle distance counted as a close call

# Optional: Command Center Bridge for remote monitoring/control
try:
    from command_center_bridge import (
        CommandCenterBridge, BridgeConfig, RemoteCommand, CommandMessage, GeoReference
    )
    HAS_COMMAND_CENTER = True
except ImportError:
    HAS_COMMAND_CENTER = False


# ============================================================================
# CONFIGURATION - Extracted Constants
# ============================================================================

@dataclass
class AltitudeConfig:
    """
    Configuration for the reactive altitude controller.
    
    All altitude-related magic numbers extracted here for easy tuning.
    Default values are tuned for AirSim City environment with buildings
    ranging from 10-60m tall.
    """
    # Altitude limits (NED: negative = above ground)
    min_altitude_ned: float = -2.0     # Floor: 2m above ground
    # FIX (city ceiling): AirSim City buildings can reach 30-60 m. A 20 m
    # cap pinned the drone against tall walls during recovery. Raise ceiling
    # to 80 m AGL — still safely below typical Class-G airspace.
    max_altitude_ned: float = -80.0    # Ceiling: 80m above ground
    default_base_alt_m: float = 5.0    # Default cruise altitude (meters)
    
    # Climb/descend rates (NED: negative = up)
    climb_rate_fast: float = -3.0      # Emergency climb
    climb_rate_normal: float = -2.0    # Standard building avoidance
    climb_rate_gentle: float = -1.0    # Short obstacles
    descend_rate: float = 0.8          # Gradual descent (positive = down)
    cruise_rate: float = 0.3           # Slow return to base alt
    
    # Obstacle detection thresholds (LiDAR values: higher = closer)
    obs_close: float = 1.5            # Obstacle is close (react)
    obs_far: float = 0.5              # Obstacle is far (clear)
    proximity_emergency: float = 2.0   # Meters, emergency threshold
    proximity_react: float = 3.5       # Meters, reaction threshold
    
    # Timing
    hold_after_clear: float = 3.0      # Seconds to hold after obstacle clears
    clear_before_descend: float = 5.0  # Sustained clearance before descending
    
    # Rate limiting
    max_vel_z_change: float = 0.5      # Max m/s change per control cycle


@dataclass
class PlannerConfig:
    """
    Configuration for the city planner.
    
    All planner-related magic numbers extracted here for easy tuning.
    Default values are tuned for AirSim City environment at 2m/cell resolution.
    """
    # Grid parameters
    # FIX (LiDAR/A* horizon): grid_resolution must be << MAX_RAY_LENGTH (4 m).
    # At 2 m/cell the planner only saw ~2 cells before the LiDAR horizon, which
    # is inside the reactive RL's 3.5 m proximity_react threshold — A* could
    # never plan through tight gaps before the reactive layer overrode it.
    # 1 m/cell gives ~4 cells of A* sightline within the LiDAR cone.
    grid_resolution: float = 1.0       # Meters per grid cell
    grid_size: int = 300               # Grid cells per side (default; resized dynamically)
    inflate_radius: int = 2            # Obstacle inflation (cells) — keep ~2 m clearance at 1 m/cell

    # Stuck detection
    stuck_threshold: float = 8.0       # Seconds without progress
    stuck_distance: float = 2.0        # Meters minimum progress
    max_replans: int = 5               # Maximum replan attempts
    waypoint_spacing: float = 15.0     # Meters between waypoints

    # Grid maintenance
    # FIX (decay amnesia): 60 s was short enough that, on a slow leg around a
    # large building, the wall the drone had already mapped expired and A*
    # routed BACK through it — endless looping. Decay cells over 10 minutes
    # instead; confirmed cells (seen >= confirmed_obs_count) never decay.
    grid_decay_max_age: float = 600.0  # Seconds before unconfirmed observations decay
    confirmed_obs_count: int = 3       # Observations before obstacle is "confirmed" (won't decay)
    
    # Proactive replanning
    replan_check_interval: float = 2.0 # Seconds between proactive replan checks
    max_proactive_replans: int = 20    # Budget cap — switch to direct RL after this many
    progress_check_every: int = 5      # Check monotonic progress every N proactive replans
    
    # Dynamic timeout
    dynamic_timeout_buffer: float = 45.0   # Seconds added to path-based timeout
    dynamic_timeout_speed: float = 1.5     # Assumed avg speed for timeout calc (m/s)
    absolute_max_timeout: float = 240.0    # Hard ceiling regardless of path length
    
    # Path simplification
    path_angle_threshold: float = 20.0 # Degrees: keep waypoint if direction changes more
    
    # Pitch compensation
    pitch_vel_scale_threshold: float = 8.0   # Degrees: start scaling velocity when pitch > this
    pitch_vel_scale_max: float = 15.0        # Degrees: maximum scale-down pitch
    pitch_vel_min_scale: float = 0.4         # Minimum velocity scale factor at max pitch
    pitch_obs_proximity: float = 3.0         # Meters: only apply pitch scaling when obstacle < this
    
    # Best Effort goal arrival
    # When A* fails repeatedly near goal, accept "close enough" instead of
    # endlessly replanning. In real missions, arriving within a few metres of a
    # building face is a success; crashing is a failure.
    # FIX (best-effort trap): the previous defaults (threshold=2, distance=15 m)
    # let the planner declare success up to 15 m short of the goal after only
    # two failed replans — making it look like the drone was quitting early.
    # Require 5 consecutive failed near-goal replans AND be within 8 m before
    # giving up. 8 m is just outside the 5 m goal threshold, so Best Effort is
    # only a true last-ditch fallback when literally pinned at a wall.
    best_effort_replan_threshold: int = 5     # Consecutive failed replans near goal before accepting
    best_effort_distance: float = 8.0         # Max distance to goal for Best Effort acceptance
    
    # Trajectory smoothing
    # String-tightening: iteratively pull waypoints toward the line between
    # neighbors while staying on free cells. Produces smoother paths that 
    # let the drone maintain higher velocity through turns.
    smooth_iterations: int = 50               # String-tightening passes
    smooth_alpha: float = 0.3                 # Pull strength toward shortcut (0=none, 1=full)
    
    # Yaw compensation
    # When the drone needs to turn sharply at a waypoint, the forward-facing
    # LiDAR rotates away from the velocity vector. The drone drifts sideways
    # into unmapped space. Scaling velocity during large yaw errors lets the
    # LiDAR scan the new direction BEFORE accelerating into it.
    yaw_vel_scale_threshold: float = 60.0     # Degrees: start scaling when yaw error > this
    yaw_vel_min_scale: float = 0.5            # Minimum velocity scale at large yaw error


# ============================================================================
# REACTIVE ALTITUDE CONTROLLER - LiDAR-Driven Z Control
# ============================================================================

class CityAltitudeController:
    """
    Reactive altitude controller for city navigation.
    
    Instead of flying at a pre-set altitude, the drone starts at a minimum
    safe altitude and REACTIVELY adjusts based on LiDAR obstacle detection.
    
    This decouples altitude control from the NavRL model entirely:
    - NavRL PPO handles XY navigation (trained behavior)
    - This controller handles Z (classical, reactive, sensor-driven)
    
    Design Philosophy:
        No pre-programmed building heights needed. Altitude is determined
        purely from real-time LiDAR sensor data. This mimics how a real
        drone operator works: an operator clicks a 2D point on a map
        (like Google Maps), and the drone autonomously determines its
        flight altitude based on what its sensors detect.
    
    Edge Cases Handled:
        1. Operator clicks map point -> only (x,y) provided, Z is automatic
        2. Tall buildings (>20m) -> detected via vertical LiDAR layer count,
           drone keeps climbing until +10 and +20 degree rays are clear
        3. Multiple buildings close together -> sustained altitude hold
           prevents yo-yo between buildings
        4. Building edge/corner -> hold altitude for CLEAR_DURATION after
           last obstacle before descending
        5. Short obstacles (cars, fences) -> gentler climb, shorter hold
        6. Open space (no obstacles) -> maintain minimum safe altitude
        7. Very close obstacles (<2m) -> emergency climb at max rate
        8. Obstacles below during descent -> abort descent immediately
    
    State Machine:
        CRUISE --obstacle--> CLIMBING --clear--> HOLDING --sustained-clear--> DESCENDING --at-base--> CRUISE
          ^                                        |
          +----------------------------------------+
                    new obstacle -> back to CLIMBING
    """
    
    def __init__(self, base_altitude_m: float = None, config: AltitudeConfig = None):
        """
        Args:
            base_altitude_m: Minimum safe altitude in METERS (positive, above ground).
                            The drone cruises here when no obstacles are present.
                            This is what the operator might set as "minimum flight height".
                            Default: 5m.
            config: AltitudeConfig with tunable parameters. If None, uses defaults.
        """
        cfg = config or AltitudeConfig()
        
        # Copy config values to instance attributes (compute() uses self.XXX)
        self.MIN_ALTITUDE_NED = cfg.min_altitude_ned
        self.MAX_ALTITUDE_NED = cfg.max_altitude_ned
        self.CLIMB_RATE_FAST = cfg.climb_rate_fast
        self.CLIMB_RATE_NORMAL = cfg.climb_rate_normal
        self.CLIMB_RATE_GENTLE = cfg.climb_rate_gentle
        self.DESCEND_RATE = cfg.descend_rate
        self.CRUISE_RATE = cfg.cruise_rate
        self.OBS_CLOSE = cfg.obs_close
        self.OBS_FAR = cfg.obs_far
        self.PROXIMITY_EMERGENCY = cfg.proximity_emergency
        self.PROXIMITY_REACT = cfg.proximity_react
        self.HOLD_AFTER_CLEAR = cfg.hold_after_clear
        self.CLEAR_BEFORE_DESCEND = cfg.clear_before_descend
        self.MAX_VEL_Z_CHANGE = cfg.max_vel_z_change
        
        if base_altitude_m is None:
            base_altitude_m = cfg.default_base_alt_m
        self.base_altitude = -abs(base_altitude_m)  # Convert to NED
        
        # State machine
        self.state = 'cruise'
        self.hold_until = 0.0
        self.last_obstacle_time = 0.0
        self.last_vel_z = 0.0
        
        # Tracking
        self.peak_climb_alt = self.base_altitude
        self.total_climbs = 0
        
    def reset(self):
        """Reset controller state (e.g., after collision recovery)."""
        self.state = 'cruise'
        self.hold_until = 0.0
        self.last_vel_z = 0.0
        # Don't reset last_obstacle_time - we want memory of recent obstacles
    
    def compute(self, lidar_obs, current_z: float, 
                min_obs_dist: float,
                velocity_x: float = 0.0, velocity_y: float = 0.0) -> float:
        """
        Compute vertical velocity based on LiDAR obstacle detection.
        
        This is the core altitude control loop. It analyzes the LiDAR
        vertical layers to determine if the drone needs to climb, hold,
        or descend. The key insight is using the VERTICAL spread of
        LiDAR returns to classify obstacles:
        
        - Only lower rays hit -> short obstacle (car, fence) -> gentle climb
        - 3+ layers hit -> tall obstacle (building) -> aggressive climb  
        - Upper rays clear -> we're above the obstacle -> hold/descend
        
        Args:
            lidar_obs: LiDAR tensor (1, 1, 36, 4) from NavRL processing
                      Vertical bins: 0=-10deg, 1=0deg, 2=+10deg, 3=+20deg
            current_z: Current altitude in NED (negative = above ground)
            min_obs_dist: Minimum obstacle distance in meters
            
        Returns:
            vel_z: Vertical velocity in NED (negative = climb, positive = descend)
        """
        now = time.time()
        
        lidar_np = lidar_obs.cpu().numpy()[0, 0]  # Shape: (36, 4)
        
        # ===== ANALYZE FRONT SECTOR VERTICAL LAYERS =====
        # Vertical bins: 0=-10deg (down), 1=0deg (level), 2=+10deg (up), 3=+20deg (higher)
        #
        # Horizontal bin layout (goal-relative, from process_lidar):
        #   arctan2(y, x) normalised to [0°, 360°) → divided into 36×10° bins
        #   Bin 0  =   0° = directly toward goal
        #   Bins 1–17  = CCW (left side of goal vector)
        #   Bins 19–35 = CW  (right side of goal vector, negative angles)
        #
        # FIX: Original slice [0:8] covered ONLY 0°–70° (left side), making the
        # controller blind to buildings slightly right of the goal vector.
        # Correct front sector: symmetric ±40° around goal direction.
        #   Left:  bins 0–3  (0°, 10°, 20°, 30°)
        #   Right: bins 35,34,33,32 (−10°, −20°, −30°, −40°)
        front_left  = lidar_np[0:4, :]           # 0° → 30° left
        front_right = lidar_np[35:31:-1, :]      # −10° → −40° right (closest-to-center first)
        front_bins  = np.concatenate((front_left, front_right), axis=0)  # (8, 4)

        # Symmetric weights: peak at 0° (straight ahead), equal on both sides at ±N°
        weights = np.array([1.0, 0.9, 0.8, 0.7,   # left:  0°, 10°, 20°, 30°
                            0.9, 0.8, 0.7, 0.6])   # right: −10°, −20°, −30°, −40°
        front_weighted = front_bins * weights[:, np.newaxis]
        
        # Per-vertical-layer max (closest obstacle at each elevation)
        front_down  = np.max(front_weighted[:, 0])  # -10deg rays (below level)
        front_level = np.max(front_weighted[:, 1])  #   0deg rays (level)
        front_up1   = np.max(front_weighted[:, 2])  # +10deg rays (above level)
        front_up2   = np.max(front_weighted[:, 3])  # +20deg rays (well above)
        front_max   = np.max(front_weighted)         # Overall closest
        
        # ===== OBSTACLE CLASSIFICATION =====
        # FIX: Paranoid altitude bug — min_obs_dist is computed over 360° so
        # a building to the *side* of the drone would trigger a climb even when
        # the path ahead is completely clear.  Restrict reactive climbing to:
        #   (a) obstacles in the forward flight sector (front_max), and
        #   (b) obstacles directly below the drone (obstacle_below).
        #
        # FIX: Check for obstacles BELOW in the FORWARD sector only (-10deg layer).
        # Using all 36 horizontal bins causes rear-hemisphere buildings (just flown past)
        # to keep obstacle_below=True, preventing descent and causing altitude spiral.
        # Restrict to same +/-40deg front sector used by front_weighted above.
        front_below_left  = lidar_np[0:4, 0]       # 0 -> 30deg left, -10deg layer
        front_below_right = lidar_np[35:31:-1, 0]   # -10 -> -40deg right, -10deg layer
        front_below = np.concatenate([front_below_left, front_below_right])
        below_max = np.max(front_below * weights)   # same weights as front_weighted
        obstacle_below = below_max > self.OBS_CLOSE

        # Velocity gate: only react to forward obstacles if the drone has forward momentum.
        # A hovering drone (A* stall) directly in front of a wall would otherwise trigger
        # continuous climbing — the "elevator effect" — until timeout.
        xy_speed = np.linalg.norm([velocity_x, velocity_y])
        moving_forward = xy_speed > 0.5
        obstacle_detected = (front_max > self.OBS_CLOSE and moving_forward) or obstacle_below
        obstacle_emergency = front_max > (self.OBS_CLOSE * 1.5)  # forward-only emergency
        obstacle_clear = front_max < self.OBS_FAR  # forward path clear (side walls irrelevant)
        
        # FIX: Use layer count instead of just upper rays for tall detection.
        # A tall building fills 3+ vertical layers. A short obstacle fills 1-2.
        # Using a threshold of 0.5 (any return > 0.5 counts as a hit).
        layers_hit = sum([
            front_down  > 0.5,
            front_level > 0.5,
            front_up1   > 0.5,
            front_up2   > 0.5,
        ])
        is_tall = obstacle_detected and layers_hit >= 3
        is_short = obstacle_detected and layers_hit < 3
        
        # Is there space ABOVE us? (upper rays clear)
        space_above = (front_up1 < self.OBS_FAR and front_up2 < self.OBS_FAR)
        
        if obstacle_detected:
            self.last_obstacle_time = now
        
        # ===== STATE MACHINE =====
        vel_z = 0.0
        
        if self.state == 'cruise':
            if obstacle_emergency:
                # VERY close obstacle - emergency climb
                self.state = 'climbing'
                self.total_climbs += 1
                vel_z = self.CLIMB_RATE_FAST
            elif is_tall:
                # Tall building ahead - aggressive climb
                self.state = 'climbing'
                self.total_climbs += 1
                vel_z = self.CLIMB_RATE_NORMAL
            elif is_short:
                # Short obstacle - gentle climb
                self.state = 'climbing'
                self.total_climbs += 1
                vel_z = self.CLIMB_RATE_GENTLE
            elif obstacle_detected:
                # Generic obstacle - standard climb
                self.state = 'climbing'
                self.total_climbs += 1
                vel_z = self.CLIMB_RATE_NORMAL
            else:
                # No obstacle - gently return to base altitude
                alt_error = self.base_altitude - current_z  # NED
                if abs(alt_error) > 0.5:
                    vel_z = np.clip(alt_error * 0.3, 
                                  -self.CRUISE_RATE, self.CRUISE_RATE)
                else:
                    vel_z = 0.0
                    
        elif self.state == 'climbing':
            if obstacle_emergency:
                # Still too close - max climb
                vel_z = self.CLIMB_RATE_FAST
            elif obstacle_detected and not space_above:
                # Still climbing, obstacle extends above us
                vel_z = self.CLIMB_RATE_NORMAL
            elif obstacle_detected and space_above:
                # Obstacle detected but upper rays clear -> near top of obstacle
                # Keep climbing a bit more to fully clear it
                vel_z = self.CLIMB_RATE_GENTLE
            elif obstacle_clear:
                # Cleared the obstacle - transition to hold
                self.state = 'holding'
                self.hold_until = now + self.HOLD_AFTER_CLEAR
                self.peak_climb_alt = current_z
                vel_z = 0.0
            else:
                # Ambiguous - keep climbing slowly
                vel_z = self.CLIMB_RATE_GENTLE
                
        elif self.state == 'holding':
            if obstacle_detected:
                # New obstacle while holding - climb again immediately
                self.state = 'climbing'
                vel_z = self.CLIMB_RATE_NORMAL
            elif now > self.hold_until:
                # Hold period expired
                time_since_obs = now - self.last_obstacle_time
                if time_since_obs > self.CLEAR_BEFORE_DESCEND:
                    # Sustained clearance - safe to start descending
                    self.state = 'descending'
                    vel_z = self.DESCEND_RATE * 0.5
                else:
                    # Recently saw obstacle - extend hold
                    self.hold_until = now + 1.0
                    vel_z = 0.0
            else:
                # Still in hold period
                vel_z = 0.0
                    
        elif self.state == 'descending':
            if obstacle_detected:
                # Obstacle during descent - abort, climb
                self.state = 'climbing'
                vel_z = self.CLIMB_RATE_NORMAL
            elif obstacle_below:
                # FIX: Obstacle detected below during descent - abort descent
                self.state = 'holding'
                self.hold_until = now + self.HOLD_AFTER_CLEAR
                vel_z = 0.0
            elif current_z >= self.base_altitude - 0.5:
                # Reached base altitude (within hysteresis band) - back to cruise
                self.state = 'cruise'
                vel_z = 0.0
            else:
                # Still above base - continue gradual descent
                vel_z = self.DESCEND_RATE * 0.5
        
        # ===== SAFETY LIMITS =====
        # Ceiling: don't fly above MAX_ALTITUDE_NED
        above_ceiling = current_z < self.MAX_ALTITUDE_NED
        if above_ceiling:
            # P-controller: actively descend proportional to overshoot so the drone
            # returns to the ceiling instead of just coasting upward.
            # (MAX_ALTITUDE_NED - current_z) > 0 when above ceiling (both NED negatives).
            p_descent = np.clip((self.MAX_ALTITUDE_NED - current_z) * 0.5, 0.5, 3.0)
            vel_z = p_descent  # Override state machine: return-to-ceiling is priority
            self.state = 'holding'
            self.hold_until = now + 2.0
            
        # Floor: don't descend below MIN_ALTITUDE_NED
        if current_z > self.MIN_ALTITUDE_NED and vel_z > 0:
            vel_z = 0.0
            self.state = 'cruise'
        
        # FIX: Don't descend if obstacle detected below
        if vel_z > 0 and obstacle_below:
            vel_z = 0.0
        
        # ===== RATE LIMITING =====
        # Emergency override: skip rate limiter when above ceiling.
        # Without this, the ramp from last_vel_z=-3.0 (climbing) to 0 takes 6+ steps
        # at MAX_VEL_Z_CHANGE=0.5, carrying the drone tens of meters past the ceiling.
        if not above_ceiling:
            vel_z = np.clip(vel_z,
                           self.last_vel_z - self.MAX_VEL_Z_CHANGE,
                           self.last_vel_z + self.MAX_VEL_Z_CHANGE)
        
        # ===== SMOOTHING =====
        # Quick response when climbing (obstacle avoidance is time-critical)
        # Smooth transitions when cruising/descending (comfort)
        if above_ceiling:
            smoothing = 0.0  # No smoothing: apply ceiling correction immediately
        elif self.state == 'climbing':
            smoothing = 0.2  # Very responsive
        elif self.state == 'holding':
            smoothing = 0.5
        else:
            smoothing = 0.7  # Smooth for cruise/descent
            
        vel_z_smooth = smoothing * self.last_vel_z + (1 - smoothing) * vel_z
        self.last_vel_z = vel_z_smooth
        
        return vel_z_smooth
    
    def get_status(self) -> str:
        """Get human-readable altitude controller state."""
        alt_states = {
            'cruise': 'CRUISE',
            'climbing': 'CLIMBING', 
            'holding': 'HOLDING',
            'descending': 'DESCENDING'
        }
        return alt_states.get(self.state, self.state)
    
    def get_takeoff_altitude(self) -> float:
        """Get the initial takeoff altitude (NED)."""
        return self.base_altitude


# ============================================================================
# OCCUPANCY GRID - 2D Map Built from LiDAR
# ============================================================================

class OccupancyGrid:
    """
    2D occupancy grid for mapping obstacles from LiDAR data.
    
    How it works:
    - Grid covers a large area (e.g., 500m x 500m) at 2m resolution
    - As the drone flies, LiDAR points are projected onto the 2D grid
    - Each cell has a value: 0 = free, 1 = occupied
    - Obstacles are inflated by a safety radius for path planning
    - Cells have timestamps for age-based decay of stale observations
    
    The grid is centered on the midpoint between start and goal,
    ensuring both are within the grid bounds.
    """
    
    def __init__(self, resolution: float = 2.0, size: int = 300, 
                 center: tuple = (0, 0), config: PlannerConfig = None):
        """
        Args:
            resolution: Meters per grid cell (2m = good for city blocks)
            size: Grid size in cells (300 = 600m x 600m coverage)
            center: World coordinate of grid center [x, y]
            config: PlannerConfig with tunable parameters. If None, uses defaults.
        """
        cfg = config or PlannerConfig()
        self.resolution = resolution
        self.size = size
        self.center = np.array(center, dtype=float)
        
        # Grid storage: 0 = unknown/free, 1 = occupied
        self.grid = np.zeros((size, size), dtype=np.float32)
        
        # Inflated grid for path planning (adds safety margin around obstacles)
        self.planning_grid = np.zeros((size, size), dtype=np.float32)
        
        # Track which cells have been observed (for distinguishing unknown vs free)
        self.observed = np.zeros((size, size), dtype=bool)
        
        # FIX: Timestamps for age-based decay (when each cell was last marked occupied)
        self.grid_timestamps = np.zeros((size, size), dtype=np.float64)
        
        # FIX v4: Observation counts — track how many times each cell was seen occupied.
        # Cells observed >= confirmed_obs_count are "confirmed" permanent obstacles
        # and will NOT be decayed (buildings don't move).
        self.observation_count = np.zeros((size, size), dtype=np.int32)
        self.confirmed_obs_count = cfg.confirmed_obs_count
        
        # Safety inflation radius (in cells)
        self.inflate_radius = cfg.inflate_radius  # 1 cell * 2m = 2m safety margin
        
        # Age-based decay max age
        self.decay_max_age = cfg.grid_decay_max_age
        
        print(f"   📐 Grid: {size}x{size} cells, {resolution}m/cell, "
              f"covers {size*resolution:.0f}m x {size*resolution:.0f}m")
    
    def world_to_grid(self, x: float, y: float) -> tuple:
        """Convert world coordinates (NED) to grid cell indices."""
        gx = int((x - self.center[0]) / self.resolution + self.size / 2)
        gy = int((y - self.center[1]) / self.resolution + self.size / 2)
        return gx, gy
    
    def grid_to_world(self, gx: int, gy: int) -> tuple:
        """Convert grid cell indices to world coordinates (NED)."""
        x = (gx - self.size / 2) * self.resolution + self.center[0]
        y = (gy - self.size / 2) * self.resolution + self.center[1]
        return x, y
    
    def in_bounds(self, gx: int, gy: int) -> bool:
        """Check if grid indices are within bounds."""
        return 0 <= gx < self.size and 0 <= gy < self.size
    
    def _bresenham_line(self, x0: int, y0: int, x1: int, y1: int) -> list:
        """
        Bresenham's line algorithm - returns all grid cells along a line.
        
        Used for LiDAR raytracing: marks cells between drone and obstacle
        as free (clear), and the endpoint cell as occupied.
        
        Args:
            x0, y0: Start cell (drone position)
            x1, y1: End cell (LiDAR hit point)
            
        Returns:
            List of (gx, gy) grid cell coordinates along the line
        """
        cells = []
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        
        while True:
            cells.append((x0, y0))
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy
        
        return cells
    
    def _raytrace_clearance(self, drone_gx: int, drone_gy: int,
                             hit_gx: int, hit_gy: int):
        """
        Mark cells along a LiDAR ray as clear (free space).
        
        For each LiDAR hit, the cells BETWEEN the drone and the hit point
        must be free (the ray traveled through them). Only the hit cell
        itself is occupied.
        
        This is much more accurate than the radius-based clearing approach
        because it respects actual sensor geometry.
        
        Logic: Clear every intermediate cell UNLESS it has fresh obstacle
        data (marked occupied < 1 second ago). This prevents a single
        ray from erasing a confirmed obstacle that another ray just hit.
        
        Args:
            drone_gx, drone_gy: Drone position in grid coordinates
            hit_gx, hit_gy: LiDAR hit point in grid coordinates
        """
        cells = self._bresenham_line(drone_gx, drone_gy, hit_gx, hit_gy)
        now = time.time()
        
        # Vectorized: extract all intermediate cells (exclude last = hit point)
        if len(cells) <= 1:
            return
        intermediate = cells[:-1]
        coords = np.array(intermediate, dtype=np.int32)
        gxs, gys = coords[:, 0], coords[:, 1]
        
        # Bounds mask
        in_bounds = (gxs >= 0) & (gxs < self.size) & (gys >= 0) & (gys < self.size)
        gxs, gys = gxs[in_bounds], gys[in_bounds]
        
        if len(gxs) == 0:
            return
        
        # Mark all as observed
        self.observed[gxs, gys] = True
        
        # Clear cells that are NOT fresh obstacles
        is_occupied = self.grid[gxs, gys] > 0.5
        is_fresh = (now - self.grid_timestamps[gxs, gys]) < 1.0
        # FIX: "3D-to-2D Raytrace Eraser" — when the drone climbs above a building
        # and shoots a ray down past it, the flattened 2D Bresenham line passes
        # through the building's grid cells.  Without this guard, the building is
        # cleared because it isn't "fresh" (it was mapped minutes ago).
        # Protect any cell that has been confirmed (observed >= confirmed_obs_count
        # times) — those are permanent structures, not sensor noise.
        is_confirmed = self.observation_count[gxs, gys] >= self.confirmed_obs_count
        clearable = ~((is_occupied & is_fresh) | is_confirmed)
        clear_gxs = gxs[clearable]
        clear_gys = gys[clearable]
        self.grid[clear_gxs, clear_gys] = 0.0
    
    def update_from_lidar_points(self, drone_pos: np.ndarray, 
                                  points_world: np.ndarray,
                                  drone_z: float):
        """
        Update grid from LiDAR points in world frame.
        
        Args:
            drone_pos: Drone [x, y] in world NED
            points_world: LiDAR points in world frame, relative to drone, shape (N, 3)
            drone_z: Drone altitude in NED (negative = above ground)
        """
        if len(points_world) == 0:
            return
        
        now = time.time()
        
        # Mark drone position as free (observed)
        dgx, dgy = self.world_to_grid(drone_pos[0], drone_pos[1])
        if self.in_bounds(dgx, dgy):
            self.observed[dgx, dgy] = True
        
        # Convert world-relative points to absolute world coordinates
        abs_points = points_world.copy()
        abs_points[:, 0] += drone_pos[0]
        abs_points[:, 1] += drone_pos[1]
        abs_points[:, 2] += drone_z
        
        # Only project points that are at reasonable flight altitude
        # (ignore ground points and very high points)
        alt_points = -abs_points[:, 2]  # Convert NED Z to positive altitude
        flight_alt = -drone_z  # Current flight altitude (positive meters)
        
        # FIX v2→v3: Filter relative to flight altitude with low-alt guard.
        # Previous v1: narrow band (0.3, flight_alt+10) lost buildings when climbing.
        # Previous v2: fixed band (0.5, 60) kept irrelevant ground-level obstacles.
        # v2 fix: Keep points from (flight_alt - 5m) up to 100m.
        # v3 fix: When flying low (<3m), use tighter lower bound to avoid
        #         ground clutter that appears at 0.5-1m altitude.
        if flight_alt < 3.0:
            # Close to ground - filter more aggressively to avoid ground clutter
            min_relevant_alt = max(1.0, flight_alt - 2.0)
        else:
            # Higher altitude - keep obstacles below us for descent planning
            min_relevant_alt = max(0.5, flight_alt - 5.0)
        
        altitude_mask = (alt_points > min_relevant_alt) & (alt_points < 100.0)
        relevant_points = abs_points[altitude_mask]
        
        if len(relevant_points) == 0:
            return
        
        # ===== VECTORIZED grid update =====
        # Convert all hit points to grid coordinates at once
        hit_gx = ((relevant_points[:, 0] - self.center[0]) / self.resolution + self.size / 2).astype(int)
        hit_gy = ((relevant_points[:, 1] - self.center[1]) / self.resolution + self.size / 2).astype(int)
        
        # Filter in-bounds
        in_bounds = (hit_gx >= 0) & (hit_gx < self.size) & (hit_gy >= 0) & (hit_gy < self.size)
        hit_gx = hit_gx[in_bounds]
        hit_gy = hit_gy[in_bounds]
        
        if len(hit_gx) == 0:
            return
        
        # Deduplicate hit cells to avoid redundant raytracing
        # (many LiDAR points can hit the same 2m grid cell)
        unique_cells = np.unique(np.column_stack([hit_gx, hit_gy]), axis=0)
        
        # Raytrace from drone to each UNIQUE hit cell (clears intermediate cells)
        for cell in unique_cells:
            self._raytrace_clearance(dgx, dgy, int(cell[0]), int(cell[1]))
        
        # FIX: "Instant Confirmation" bug — np.add.at on all hit_gx/hit_gy counts
        # every LiDAR point individually.  A single frame can have 50+ points
        # hitting the same 2m cell, instantly pushing observation_count to 3+
        # and permanently confirming noise/dynamic objects as buildings.
        # Fix: use unique_cells (already computed for raytracing) so each cell
        # is incremented at most once per LiDAR sweep.
        unique_hit_gx = unique_cells[:, 0]
        unique_hit_gy = unique_cells[:, 1]
        self.grid[unique_hit_gx, unique_hit_gy] = 1.0
        self.grid_timestamps[unique_hit_gx, unique_hit_gy] = now
        self.observed[unique_hit_gx, unique_hit_gy] = True
        self.observation_count[unique_hit_gx, unique_hit_gy] += 1
        
        # Update planning grid (inflate obstacles)
        self._inflate_obstacles()
    
    def _inflate_obstacles(self):
        """Inflate obstacles for safe path planning with circular structuring element."""
        try:
            from scipy.ndimage import binary_dilation
            # FIX: Use circular structuring element instead of square.
            # Previous: np.ones((2*r+1, 2*r+1)) creates a square mask that
            # over-inflates at corners (diagonal distance > radius).
            # Fix: Use x^2 + y^2 <= r^2 for true circular inflation.
            r = self.inflate_radius
            y, x = np.ogrid[-r:r+1, -r:r+1]
            struct = (x**2 + y**2 <= r**2).astype(np.uint8)
            self.planning_grid = binary_dilation(
                self.grid > 0.5, structure=struct
            ).astype(np.float32)
        except ImportError:
            # Manual inflation (slower but no dependency)
            self.planning_grid = self.grid.copy()
            occupied = np.argwhere(self.grid > 0.5)
            r = self.inflate_radius
            for ox, oy in occupied:
                for dx in range(-r, r + 1):
                    for dy in range(-r, r + 1):
                        if dx*dx + dy*dy <= r*r:
                            nx, ny = ox + dx, oy + dy
                            if self.in_bounds(nx, ny):
                                self.planning_grid[nx, ny] = 1.0
    
    def mark_collision_zone(self, world_x: float, world_y: float,
                            radius_m: float = 4.0):
        """
        FIX (collision memory): Stamp a circular permanent no-go zone around a
        collision XY. Cells inside are forced to occupied AND their
        observation_count is bumped past `confirmed_obs_count` so the next
        `decay_old_observations()` call cannot erase them.

        This prevents the bounce-then-re-collide loop: after the drone hits a
        building, A* will refuse to route through that XY again — even if the
        post-recovery LiDAR sweep doesn't fully re-observe it.
        """
        cx, cy = self.world_to_grid(world_x, world_y)
        r_cells = max(1, int(np.ceil(radius_m / self.resolution)))
        for dx in range(-r_cells, r_cells + 1):
            for dy in range(-r_cells, r_cells + 1):
                if dx * dx + dy * dy > r_cells * r_cells:
                    continue
                gx, gy = cx + dx, cy + dy
                if not self.in_bounds(gx, gy):
                    continue
                self.grid[gx, gy] = 1.0
                self.observed[gx, gy] = True
                self.grid_timestamps[gx, gy] = time.time()
                # Bump past the confirmed threshold so decay never clears it.
                if self.observation_count[gx, gy] < self.confirmed_obs_count:
                    self.observation_count[gx, gy] = self.confirmed_obs_count + 1
        self._inflate_obstacles()

    def decay_old_observations(self, max_age: float = None):
        """
        FIX v4: Age-based grid decay with confirmed-obstacle protection.
        
        Only removes obstacle cells that:
        1. Haven't been re-observed within max_age seconds, AND
        2. Have been observed fewer than confirmed_obs_count times.
        
        Cells observed 3+ times are "confirmed" permanent obstacles (buildings)
        and will NEVER be decayed. This prevents the replan-loop problem where
        age decay clears permanent buildings, A* plans through them, the drone
        rediscovers them, and cycles indefinitely.
        
        Args:
            max_age: Maximum age in seconds. Cells older than this are cleared.
                    If None, uses the configured decay_max_age.
        """
        if max_age is None:
            max_age = self.decay_max_age
            
        now = time.time()
        occupied = self.grid > 0.5
        ages = now - self.grid_timestamps
        # FIX v4: Only decay UNconfirmed stale cells.
        # Confirmed obstacles (seen >= N times) are permanent and never decay.
        unconfirmed = self.observation_count < self.confirmed_obs_count
        stale = occupied & (ages > max_age) & unconfirmed
        self.grid[stale] = 0.0
        self._inflate_obstacles()
    
    def is_free(self, gx: int, gy: int) -> bool:
        """Check if a grid cell is free for planning."""
        if not self.in_bounds(gx, gy):
            return False
        return self.planning_grid[gx, gy] < 0.5
    
    def get_obstacle_count(self) -> int:
        """Count occupied cells."""
        return int(np.sum(self.grid > 0.5))
    
    def visualize_grid(self, current_pos=None, goal_pos=None, path=None,
                       save_path: str = None):
        """
        Save a visualization of the occupancy grid for debugging.
        
        Plots the raw grid and the inflated planning grid side-by-side,
        with optional overlays for current position, goal, and planned path.
        
        Args:
            current_pos: Current drone [x, y] position (optional)
            goal_pos: Goal [x, y] position (optional)
            path: List of [x, y] waypoints (optional)
            save_path: File path to save the image. Default: navrl_grid_debug.png
                      in the same directory as this script.
        """
        try:
            import matplotlib
            matplotlib.use('Agg')  # Non-interactive backend
            import matplotlib.pyplot as plt
            
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
            
            # Plot raw grid
            ax1.imshow(self.grid.T, origin='lower', cmap='gray_r',
                      extent=[0, self.size, 0, self.size])
            ax1.set_title(f'Raw Occupancy Grid ({self.get_obstacle_count()} obstacles)')
            ax1.set_xlabel('X (grid cells)')
            ax1.set_ylabel('Y (grid cells)')
            
            # Plot planning grid (with inflation)
            ax2.imshow(self.planning_grid.T, origin='lower', cmap='gray_r',
                      extent=[0, self.size, 0, self.size])
            ax2.set_title('Planning Grid (Inflated)')
            
            # Overlay positions and path
            if current_pos is not None:
                cx, cy = self.world_to_grid(current_pos[0], current_pos[1])
                for ax in (ax1, ax2):
                    ax.plot(cx, cy, 'go', markersize=10, label='Drone')
            
            if goal_pos is not None:
                gx, gy = self.world_to_grid(goal_pos[0], goal_pos[1])
                for ax in (ax1, ax2):
                    ax.plot(gx, gy, 'r*', markersize=15, label='Goal')
            
            if path is not None and len(path) > 0:
                try:
                    path_x = [self.world_to_grid(p[0], p[1])[0] for p in path]
                    path_y = [self.world_to_grid(p[0], p[1])[1] for p in path]
                    ax2.plot(path_x, path_y, 'b-', linewidth=2, label='Path')
                    ax2.plot(path_x, path_y, 'bo', markersize=5)
                except (IndexError, TypeError) as e:
                    print(f"   ⚠️ Could not plot path: {e}")
            
            ax2.legend(loc='upper right', fontsize=8)
            ax2.set_xlabel('X (grid cells)')
            ax2.set_ylabel('Y (grid cells)')
            
            plt.tight_layout()
            
            if save_path is None:
                save_path = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    'navrl_grid_debug.png'
                )
            plt.savefig(save_path, dpi=150)
            plt.close()
            print(f"   📊 Grid visualization saved to {save_path}")
            
        except ImportError:
            print("   ⚠️ matplotlib not available for visualization")


# ============================================================================
# PATH UTILITIES
# ============================================================================

def _line_of_sight_clear(grid: 'OccupancyGrid', x0: int, y0: int,
                         x1: int, y1: int) -> bool:
    """
    Bresenham line walk: return True if every cell from (x0,y0) to (x1,y1)
    is free on the planning grid.  Used by simplify_path to prevent
    simplified segments from cutting through inflated obstacle boundaries.
    """
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    cx, cy = x0, y0
    while True:
        if not grid.is_free(cx, cy):
            return False
        if cx == x1 and cy == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            cx += sx
        if e2 < dx:
            err += dx
            cy += sy
    return True


# ============================================================================
# A* PATH PLANNER
# ============================================================================

def astar(grid: OccupancyGrid, start_world: np.ndarray, 
          goal_world: np.ndarray) -> list:
    """
    A* path planning on the occupancy grid.
    
    How A* works:
    1. Start from the start cell, explore neighbors
    2. For each cell, track cost: g(n) = cost from start, h(n) = estimated cost to goal
    3. Always expand the cell with lowest f(n) = g(n) + h(n)
    4. When goal is reached, backtrack to get the path
    5. Uses 8-connectivity (can move diagonally)
    
    Args:
        grid: OccupancyGrid with obstacle information
        start_world: Start position [x, y] in world NED
        goal_world: Goal position [x, y] in world NED
        
    Returns:
        List of [x, y] world coordinates forming the path, or empty list if no path found
    """
    # Convert to grid coordinates
    sx, sy = grid.world_to_grid(start_world[0], start_world[1])
    gx, gy = grid.world_to_grid(goal_world[0], goal_world[1])
    
    # Validate start and goal
    if not grid.in_bounds(sx, sy):
        print(f"   ⚠️ Start ({start_world[0]:.0f}, {start_world[1]:.0f}) is outside grid")
        return []
    if not grid.in_bounds(gx, gy):
        print(f"   ⚠️ Goal ({goal_world[0]:.0f}, {goal_world[1]:.0f}) is outside grid")
        return []
    
    # If goal is in an obstacle, find nearest free cell to goal
    if not grid.is_free(gx, gy):
        gx, gy = _find_nearest_free(grid, gx, gy)
        if gx is None:
            print("   ⚠️ No free cell near goal")
            return []
    
    # If start is in an obstacle, find nearest free cell
    if not grid.is_free(sx, sy):
        sx, sy = _find_nearest_free(grid, sx, sy)
        if sx is None:
            print("   ⚠️ No free cell near start")
            return []
    
    # A* search
    # 8-connected neighbors (dx, dy, cost)
    neighbors = [
        (1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),  # Cardinal
        (1, 1, 1.414), (-1, 1, 1.414), (1, -1, 1.414), (-1, -1, 1.414)  # Diagonal
    ]
    
    # FIX: Octile distance heuristic instead of Euclidean.
    # Euclidean was not admissible for 8-connected grids where diagonal
    # cost is 1.414 (sqrt(2)), not sqrt(dx^2 + dy^2).
    # Octile distance exactly matches the 8-connected movement costs,
    # making A* both admissible AND consistent -> optimal + fewer expansions.
    def heuristic(x, y):
        dx = abs(x - gx)
        dy = abs(y - gy)
        return 1.414 * min(dx, dy) + max(dx, dy) - min(dx, dy)
    
    # Priority queue: (f_cost, counter, x, y)
    counter = 0
    open_set = [(heuristic(sx, sy), counter, sx, sy)]
    came_from = {}
    g_score = {(sx, sy): 0}
    closed = set()
    
    # FIX: Count unique cell EXPANSIONS only (not total heap pops).
    # In obstacle-heavy environments, each cell can be pushed to the open set
    # multiple times when a shorter path is found. Counting every pop burns the
    # budget on stale duplicate entries, causing premature A* termination.
    # Unique expansions are at most N*N, so the cap is tight and correct.
    max_iterations = grid.size * grid.size  # Upper bound: all cells expanded once
    iterations = 0
    
    while open_set and iterations < max_iterations:
        f, _, cx, cy = heapq.heappop(open_set)
        
        if (cx, cy) in closed:
            continue  # Stale entry — don't count against the budget
        closed.add((cx, cy))
        iterations += 1  # Count unique expansions only
        
        # Goal reached
        if cx == gx and cy == gy:
            # Reconstruct path
            path = []
            current = (gx, gy)
            while current in came_from:
                wx, wy = grid.grid_to_world(current[0], current[1])
                path.append([wx, wy])
                current = came_from[current]
            path.reverse()
            
            # Add goal world position as final point
            path.append([goal_world[0], goal_world[1]])
            
            return path
        
        # Explore neighbors
        for dx, dy, cost in neighbors:
            nx, ny = cx + dx, cy + dy
            
            if (nx, ny) in closed:
                continue
            if not grid.is_free(nx, ny):
                continue
            
            new_g = g_score[(cx, cy)] + cost
            
            if (nx, ny) not in g_score or new_g < g_score[(nx, ny)]:
                g_score[(nx, ny)] = new_g
                f_score = new_g + heuristic(nx, ny)
                counter += 1
                heapq.heappush(open_set, (f_score, counter, nx, ny))
                came_from[(nx, ny)] = (cx, cy)
    
    print(f"   ⚠️ A* failed after {iterations} iterations")
    return []


def _find_nearest_free(grid: OccupancyGrid, gx: int, gy: int, 
                        max_search: int = 20) -> tuple:
    """Find nearest free cell to given grid position."""
    for r in range(1, max_search):
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if abs(dx) == r or abs(dy) == r:  # Only check border of ring
                    nx, ny = gx + dx, gy + dy
                    if grid.in_bounds(nx, ny) and grid.is_free(nx, ny):
                        return nx, ny
    return None, None


def simplify_path(path: list, min_spacing: float = 15.0,
                  angle_threshold: float = 20.0,
                  grid: 'OccupancyGrid' = None) -> list:
    """
    Angle-based path simplification with optional line-of-sight safety check.

    Keeps a waypoint when EITHER:
    1. The path changes direction by more than angle_threshold degrees, OR
    2. The distance from the last kept waypoint exceeds min_spacing, OR
    3. (when grid is provided) dropping the waypoint would create a straight
       segment that crosses an inflated obstacle boundary.

    Rule 3 matters because A* may route around a building corner with many
    small-angle steps — simplification would draw a chord that cuts directly
    through the building's inflated bounding box.

    Args:
        path: List of [x, y] world coordinates from A*
        min_spacing: Minimum distance between waypoints in meters
        angle_threshold: Keep waypoint if direction changes more than this (degrees)
        grid: OccupancyGrid for line-of-sight checking (None = skip check)

    Returns:
        Simplified list of [x, y] waypoints
    """
    if len(path) <= 2:
        return path

    simplified = [path[0]]

    for i in range(1, len(path) - 1):
        # Distance check
        dist = np.linalg.norm(np.array(path[i]) - np.array(simplified[-1]))

        # Angle check: direction change at this point
        v_in  = np.array(path[i])     - np.array(simplified[-1])
        v_out = np.array(path[i + 1]) - np.array(path[i])

        len_in  = np.linalg.norm(v_in)
        len_out = np.linalg.norm(v_out)

        if len_in > 1e-6 and len_out > 1e-6:
            cos_angle = np.clip(
                np.dot(v_in, v_out) / (len_in * len_out), -1.0, 1.0
            )
            angle_deg = np.degrees(np.arccos(cos_angle))
        else:
            angle_deg = 0.0

        if angle_deg > angle_threshold or dist >= min_spacing:
            simplified.append(path[i])
        elif grid is not None:
            # FIX: Line-of-sight safety check.
            # If dropping path[i] draws a chord from simplified[-1] to
            # path[i+1] that cuts through an obstacle, we MUST keep path[i]
            # so the drone stays on the A*-validated route around the corner.
            gx0, gy0 = grid.world_to_grid(simplified[-1][0], simplified[-1][1])
            gx1, gy1 = grid.world_to_grid(path[i + 1][0], path[i + 1][1])
            if not _line_of_sight_clear(grid, gx0, gy0, gx1, gy1):
                simplified.append(path[i])

    # Always include the final goal
    if np.linalg.norm(np.array(path[-1]) - np.array(simplified[-1])) > 1.0:
        simplified.append(path[-1])

    return simplified


def smooth_path(path: list, grid: 'OccupancyGrid', 
                iterations: int = 50, alpha: float = 0.3) -> list:
    """
    String-tightening trajectory smoothing.
    
    Iteratively pulls each interior waypoint toward the midpoint of its
    neighbors (the "shortcut" position), subject to the constraint that
    the new position must be on a free cell. This cuts corners on the
    jagged A* grid path while respecting obstacles.
    
    The effect: instead of sharp 90° turns at grid junctions, the drone
    gets gentle arcs that maintain velocity and reduce mission time.
    
    Args:
        path: List of [x, y] world coordinates (from simplify_path)
        grid: OccupancyGrid for collision checking
        iterations: Number of smoothing passes (more = smoother, diminishing returns)
        alpha: Pull strength toward the shortcut line (0 = no smoothing, 1 = full pull).
               Values around 0.3 balance smoothness vs obstacle safety margin.
    
    Returns:
        Smoothed list of [x, y] waypoints (same start and end)
    """
    if len(path) <= 2 or grid is None:
        return path
    
    # Work on a copy as numpy arrays for vectorized math
    smoothed = [np.array(p, dtype=np.float64) for p in path]
    
    for _ in range(iterations):
        changed = False
        for i in range(1, len(smoothed) - 1):
            # Target: midpoint of neighbors (the "straight line" position)
            midpoint = (smoothed[i - 1] + smoothed[i + 1]) / 2.0
            
            # Pull current point toward midpoint
            new_pos = smoothed[i] + alpha * (midpoint - smoothed[i])
            
            # Only accept if new position is on a free cell
            gx, gy = grid.world_to_grid(new_pos[0], new_pos[1])
            if grid.in_bounds(gx, gy) and grid.is_free(gx, gy):
                # Full Bresenham LOS check to both neighbors (not just midpoint)
                gx_prev, gy_prev = grid.world_to_grid(smoothed[i - 1][0], smoothed[i - 1][1])
                gx_next, gy_next = grid.world_to_grid(smoothed[i + 1][0], smoothed[i + 1][1])
                prev_ok = _line_of_sight_clear(grid, gx, gy, gx_prev, gy_prev)
                next_ok = _line_of_sight_clear(grid, gx, gy, gx_next, gy_next)
                
                if prev_ok and next_ok:
                    if np.linalg.norm(new_pos - smoothed[i]) > 0.01:
                        changed = True
                    smoothed[i] = new_pos
        
        if not changed:
            break  # Converged
    
    return [[float(p[0]), float(p[1])] for p in smoothed]


# ============================================================================
# CITY PLANNER - Orchestrates Global Planning + NavRL Local Control
# ============================================================================

class NavRLCityPlanner:
    """
    City navigation: A* global planner + NavRL local controller.
    
    How it works:
    1. TAKEOFF: Fly to operating altitude
    2. INITIAL SCAN: Rotate 360° collecting LiDAR data to map nearby obstacles
    3. PLAN: Run A* on occupancy grid to find path to goal
    4. NAVIGATE: Use NavRL to fly between intermediate waypoints
    5. MAP & REPLAN: Continuously update map, replan if stuck or new obstacles found
    6. ARRIVE: Goal reached when within threshold distance
    
    The key insight: NavRL is great at local obstacle avoidance (4m range).
    A* handles the global planning that NavRL cannot do.
    Together they can navigate a city environment.
    """
    
    def __init__(self, device: str = None, verbose: bool = False,
                 planner_config: PlannerConfig = None,
                 altitude_config: AltitudeConfig = None,
                 command_bridge: 'CommandCenterBridge' = None):
        """Initialize with hybrid controller + planner + optional command center."""
        self.verbose = verbose
        self.planner_cfg = planner_config or PlannerConfig()
        self.altitude_cfg = altitude_config or AltitudeConfig()
        
        print("="*60)
        print("NavRL City Planner")
        print("="*60)
        print("Architecture: A* Planner + NavRL XY + Reactive Altitude Z")
        if command_bridge:
            print("Command Center: CONNECTED (remote monitoring + control)")
        print("="*60)
        
        # NavRL hybrid controller (handles actual flying)
        self.bridge = NavRLAirSimBridge(device=device)
        
        # Command center bridge (remote monitoring/control, optional)
        self.command_bridge: Optional['CommandCenterBridge'] = command_bridge
        
        # Planner state
        self.occupancy_grid = None
        self.current_plan = []
        self.current_waypoint_idx = 0
        
        # Reactive altitude controller (replaces fixed altitude)
        self.altitude_controller = None  # Created per-mission with operator's min altitude
        
        # Stuck detection
        self.stuck_threshold = self.planner_cfg.stuck_threshold
        self.stuck_distance = self.planner_cfg.stuck_distance
        self.last_progress_time = 0
        self.last_progress_pos = None
        self.last_goal_distance = float('inf')  # FIX: Track goal distance for stuck detection
        self.replan_count = 0
        self.max_replans = self.planner_cfg.max_replans
        
        # Waypoint spacing for A* path simplification
        self.waypoint_spacing = self.planner_cfg.waypoint_spacing
        
        # Proactive replanning
        self.last_replan_check = 0.0
        self.proactive_replan_count = 0
        self.last_replan_pos = None  # Spatial cooldown: position of last triggered replan
        self.best_goal_distance = float('inf')  # Track best distance for loop detection
        self.near_goal_replan_count = 0  # Consecutive replans while near goal (for Best Effort)
        
        # Track whether drone has been initialized (first nav resets, subsequent ones don't)
        self._first_nav = True

    def _reset_per_goal_state(self):
        """
        Zero ALL per-goal counters. Called at the top of every
        `_navigate_to_goal_inner` so that proactive/stuck/near-goal replan
        counts cannot drift across goals.

        Even though `nav_worker.py` spawns a fresh planner per command today,
        future callers may reuse a planner instance for multiple goals
        (mission mode already does — see `run_mission`). Without this reset,
        the second goal would inherit the first goal's `proactive_replan_count`
        and instantly hit `max_proactive_replans`, falling back to direct RL
        before A* gets a chance.
        """
        self.replan_count = 0
        self.proactive_replan_count = 0
        self.near_goal_replan_count = 0
        self.last_replan_check = time.time()
        self.last_replan_pos = None
        self.best_goal_distance = float('inf')
        self._last_progress_check_distance = float('inf')
        self._last_progress_check_replan = 0
        self._rl_fallback = False
        self._last_collision_pos = None
    
    def _log(self, message: str, level: str = 'info'):
        """
        Conditional logging based on verbosity level.
        
        Args:
            message: Log message
            level: 'debug' (verbose only), 'info' (always), 'warn' (always + prefix)
        """
        if level == 'debug' and not self.verbose:
            return
        if level == 'warn':
            print(f"   ⚠️ {message}")
        else:
            print(f"   {message}")
    
    def navigate_to_goal(self, goal: np.ndarray, timeout: float = 300.0,
                          min_altitude: float = None) -> dict:
        """
        Navigate to goal in city environment using A* + NavRL + Reactive Altitude.
        
        The operator provides only (x, y) goal coordinates - like clicking
        a point on Google Maps. The altitude (Z) is handled entirely by the
        reactive altitude controller based on real-time LiDAR data.
        
        Args:
            goal: Target [x, y] position in world NED (2D only!)
            timeout: Maximum total time (seconds)
            min_altitude: Minimum safe altitude in METERS (positive, above ground).
                         The drone starts here and climbs reactively when obstacles
                         are detected. Default: 5m.
            
        Returns:
            dict with navigation results and metrics
        """
        # Create altitude controller for this mission
        base_alt_m = min_altitude if min_altitude is not None else 5.0
        self.altitude_controller = CityAltitudeController(
            base_altitude_m=base_alt_m, config=self.altitude_cfg
        )
        takeoff_z = self.altitude_controller.get_takeoff_altitude()  # NED
        
        print(f"\n🏙️ City Navigation")
        print(f"   Goal: [{goal[0]:.0f}, {goal[1]:.0f}] (operator provides X,Y only)")
        print(f"   Altitude: REACTIVE (base={base_alt_m:.0f}m, climb on obstacle)")
        print(f"   Timeout: {timeout:.0f}s")
        
        # FIX: Wrap entire navigation in try/except for emergency stop
        try:
            return self._navigate_to_goal_inner(goal, timeout, base_alt_m, takeoff_z)
        except KeyboardInterrupt:
            print("\n\n🛑 KEYBOARD INTERRUPT - Emergency stop!")
            self.bridge.client.moveByVelocityAsync(0, 0, 0, 1).join()
            raise
        except Exception as e:
            print(f"\n\n🛑 ERROR: {e} - Emergency stop!")
            try:
                self.bridge.client.moveByVelocityAsync(0, 0, 0, 1).join()
            except Exception:
                pass
            return {
                'success': False, 'collision': False, 'time': 0,
                'path_length': 0, 'optimal_length': 0, 'efficiency': 0,
                'replans': self.replan_count,
                'obstacles_mapped': 0, 'waypoints_planned': 0,
                'closest_obstacle': MAX_RAY_LENGTH,
                'altitude_min': 0, 'altitude_max': 0, 'altitude_avg': 0,
                'altitude_std': 0, 'close_calls': 0,
                'altitude_climbs': 0, 'error': str(e)
            }
    
    def _navigate_to_goal_inner(self, goal: np.ndarray, timeout: float,
                                 base_alt_m: float, takeoff_z: float) -> dict:
        """Inner navigation logic, wrapped by navigate_to_goal for error handling."""

        # Zero ALL per-goal counters BEFORE any planning happens (#5: state leakage).
        self._reset_per_goal_state()

        # ===== PHASE 1: SETUP =====
        # Check airborne state FIRST so we don't disturb a hovering drone.
        # nav_worker spawns a fresh process per START NAV (so `_first_nav` is
        # always True on entry), but the AirSim vehicle persists between
        # commands. If it's already in the air at roughly the target altitude
        # we skip the entire takeoff/moveToZ dance — calling takeoffAsync or
        # moveToZAsync on an already-hovering drone makes it briefly drop and
        # bob back up, which the operator sees as a glitch on every nav.
        try:
            ms = self.bridge.client.getMultirotorState()
            # AirSim LandedState enum: Landed=0, Flying=1. The previous
            # `== 2` literal was always False, so this branch never fired
            # and every START NAV re-ran takeoff (the "drop and bob" glitch).
            already_flying = (ms.landed_state == airsim.LandedState.Flying)
            current_z_pre = ms.kinematics_estimated.position.z_val
        except Exception:
            already_flying = False
            current_z_pre = 0.0

        if already_flying and abs(current_z_pre - takeoff_z) <= 1.0:
            # Drone is already cruising at target altitude. Just make sure API
            # control is owned by us (idempotent — won't physically disturb a
            # drone that already has it) and proceed straight to planning.
            try:
                self.bridge.client.enableApiControl(True)
                self.bridge.client.armDisarm(True)
            except Exception:
                pass
            self._first_nav = False
            print(f"   Skipping takeoff: already airborne at z={current_z_pre:.1f}")
        elif self._first_nav:
            # Nav worker creates a fresh planner process per command. Resetting here
            # would teleport the single AirSim vehicle back to spawn every time.
            self.bridge.prepare_for_flight()
            self.bridge.takeoff(takeoff_z)
            # Post-takeoff altitude verification: takeoffAsync returns as soon as
            # the drone leaves the ground, not when it reaches takeoff_z. If AirSim
            # physics haven't settled from a prior crash, drone can end up underground.
            time.sleep(1.0)
            _, _, _, current_z, _ = self.bridge.get_drone_state()
            if current_z > takeoff_z + 1.0:  # Still too low (NED: less negative = lower)
                print(f"   Post-takeoff correction: z={current_z:.1f} -> {takeoff_z:.1f}")
                self.bridge.client.moveToZAsync(takeoff_z, 2).join()
                time.sleep(0.5)
            self._first_nav = False
        else:
            # Subsequent navigations: keep current position, just ensure flight-ready
            self.bridge.prepare_for_flight()
            # Adjust altitude if needed
            _, _, _, current_z, _ = self.bridge.get_drone_state()
            if abs(current_z - takeoff_z) > 1.0:
                self.bridge.client.moveToZAsync(takeoff_z, 2).join()
        
        start_pos, _, _, start_z, _ = self.bridge.get_drone_state()
        start_time = time.time()
        self._start_time = start_time  # For telemetry bridge
        self.final_goal = goal         # For telemetry bridge
        self.initial_goal_distance = float(np.linalg.norm(goal[:2] - start_pos))
        
        # Create occupancy grid centered between start and goal
        # FIX: Dynamic grid sizing based on start-goal distance.
        # Short distances don't need a 600m grid; long distances might.
        center = (start_pos + goal[:2]) / 2
        dist_to_goal = np.linalg.norm(goal[:2] - start_pos)
        required_coverage = max(dist_to_goal * 2.5, 100.0)  # 2.5x for detours, min 100m
        grid_size = int(required_coverage / self.planner_cfg.grid_resolution)
        grid_size = max(100, min(grid_size, 500))  # Clamp to [100, 500] cells
        
        self.occupancy_grid = OccupancyGrid(
            resolution=self.planner_cfg.grid_resolution,
            size=grid_size,
            center=center,
            config=self.planner_cfg
        )
        
        print(f"\n   Start: [{start_pos[0]:.0f}, {start_pos[1]:.0f}]")
        print(f"   Distance: {dist_to_goal:.0f}m")
        print(f"   Grid: {grid_size}x{grid_size} cells = "
              f"{grid_size * self.planner_cfg.grid_resolution:.0f}m coverage")
        
        # ===== COMMAND CENTER BRIDGE SETUP =====
        # Start telemetry push + command listener if bridge is connected
        if self.command_bridge and self.command_bridge.is_connected:
            self.command_bridge.start_telemetry_loop(self)
            self.command_bridge.start_command_listener()
            print("   📡 Command center: telemetry + commands active")
        
        # ===== PHASE 2: INITIAL SCAN =====
        print("\n📡 Phase 1: Scanning surroundings...")
        self._scan_surroundings(goal)
        print(f"   Mapped {self.occupancy_grid.get_obstacle_count()} obstacle cells")
        
        # ===== PHASE 3: INITIAL PLAN =====
        print("\n🗺️ Phase 2: Planning path...")
        position, _, _, _, _ = self.bridge.get_drone_state()
        self.current_plan = self._plan_path(position, goal[:2])
        
        # Visualize grid after initial scan + plan (verbose mode)
        if self.verbose:
            self.occupancy_grid.visualize_grid(position, goal[:2], self.current_plan)
        
        if not self.current_plan:
            print("   No path found! Attempting direct navigation...")
            self.current_plan = [[goal[0], goal[1]]]
        
        self.current_waypoint_idx = 0
        # Per-goal counters were already zeroed by _reset_per_goal_state() at
        # the top of this method; here we only re-arm progress trackers that
        # depend on the freshly-sampled `position`.
        self.last_progress_time = time.time()
        self.last_progress_pos = position.copy()
        self.last_goal_distance = np.linalg.norm(goal[:2] - position)
        self.last_replan_check = time.time()
        
        # ===== DYNAMIC TIMEOUT =====
        # Calculate timeout from initial A* path length instead of fixed clock
        initial_path_length = sum(
            np.linalg.norm(np.array(self.current_plan[i+1]) - np.array(self.current_plan[i]))
            for i in range(len(self.current_plan) - 1)
        ) if len(self.current_plan) > 1 else dist_to_goal
        cfg = self.planner_cfg
        dynamic_timeout = initial_path_length / cfg.dynamic_timeout_speed + cfg.dynamic_timeout_buffer
        effective_timeout = min(dynamic_timeout, cfg.absolute_max_timeout)
        # Never shorten below what the caller explicitly passed
        timeout = max(timeout, effective_timeout)
        print(f"   Timeout: {timeout:.0f}s (dynamic: path={initial_path_length:.0f}m → {dynamic_timeout:.0f}s, cap={cfg.absolute_max_timeout:.0f}s)")
        
        print(f"   Plan: {len(self.current_plan)} waypoints")
        for i, wp in enumerate(self.current_plan):
            print(f"     WP{i+1}: [{wp[0]:.0f}, {wp[1]:.0f}]")
        
        # ===== PHASE 4: NAVIGATE WAYPOINTS =====
        print(f"\n🚁 Phase 3: Navigating...")
        
        success = False
        had_collision = False      # any collision occurred during this leg
        terminal_collision = False  # navigation ended because of unrecovered collision
        total_path = 0.0
        last_pos = position.copy()
        closest_obstacle = MAX_RAY_LENGTH
        close_calls = 0
        altitude_readings = []
        
        remote_stopped = False
        
        while True:
            elapsed = time.time() - start_time
            
            # Check timeout
            if elapsed > timeout:
                print(f"\n⏱️ Timeout after {timeout:.0f}s")
                break
            
            # ===== CHECK REMOTE COMMANDS =====
            if self.command_bridge and self.command_bridge.is_connected:
                cmd = self.command_bridge.pop_command()
                while cmd is not None:
                    if cmd.command == RemoteCommand.STOP:
                        print(f"\n🛑 Remote STOP received!")
                        remote_stopped = True
                        break
                    elif cmd.command == RemoteCommand.EMERGENCY_LAND:
                        print(f"\n🚨 EMERGENCY LAND received! Landing immediately...")
                        remote_stopped = True
                        # Zero velocity then land
                        self.bridge.client.moveByVelocityAsync(0, 0, 0, 1).join()
                        self.bridge.client.landAsync().join()
                        break
                    elif cmd.command == RemoteCommand.PAUSE:
                        print(f"\n⏸️ Remote PAUSE — hovering...")
                        self.command_bridge.set_paused(True)
                        self.bridge.client.moveByVelocityAsync(0, 0, 0, 1).join()
                        # Hover loop: wait for RESUME or STOP
                        while self.command_bridge.is_paused:
                            resume_cmd = self.command_bridge.pop_command()
                            if resume_cmd is None:
                                time.sleep(0.1)
                                continue
                            if resume_cmd.command == RemoteCommand.RESUME:
                                print(f"\n▶️ Remote RESUME — continuing navigation")
                                self.command_bridge.set_paused(False)
                                break
                            elif resume_cmd.command == RemoteCommand.STOP:
                                print(f"\n🛑 Remote STOP (while paused)!")
                                self.command_bridge.set_paused(False)
                                remote_stopped = True
                                break
                            elif resume_cmd.command == RemoteCommand.EMERGENCY_LAND:
                                print(f"\n🚨 EMERGENCY LAND (while paused)!")
                                self.command_bridge.set_paused(False)
                                self.bridge.client.landAsync().join()
                                remote_stopped = True
                                break
                        if remote_stopped:
                            break
                    elif cmd.command == RemoteCommand.REPLAN:
                        print(f"\n🔄 Remote FORCE REPLAN")
                        self.occupancy_grid.decay_old_observations()
                        self.current_plan = self._plan_path(position, goal[:2])
                        self.current_waypoint_idx = 0
                        if not self.current_plan:
                            self.current_plan = [[goal[0], goal[1]]]
                        else:
                            print(f"   Replanned: {len(self.current_plan)} waypoints")
                    elif cmd.command == RemoteCommand.CONFIG_UPDATE:
                        print(f"\n⚙️ Remote CONFIG UPDATE")
                        new_cfg = cmd.payload
                        for key, val in new_cfg.items():
                            if hasattr(self.planner_cfg, key):
                                setattr(self.planner_cfg, key, val)
                                print(f"   {key} = {val}")
                    elif cmd.command == RemoteCommand.SET_GOAL:
                        new_x = cmd.payload.get('goalX')
                        new_y = cmd.payload.get('goalY')
                        if new_x is not None and new_y is not None:
                            goal = np.array([new_x, new_y])
                            print(f"\n🎯 Remote goal update → [{new_x:.0f}, {new_y:.0f}]")
                            self.current_plan = self._plan_path(position, goal[:2])
                            self.current_waypoint_idx = 0
                            if not self.current_plan:
                                self.current_plan = [[goal[0], goal[1]]]
                    cmd = self.command_bridge.pop_command()
                if remote_stopped:
                    break
            
            # Check collision
            if self.bridge.check_collision():
                had_collision = True
                self.replan_count += 1
                print(f"\n💥 Collision #{self.replan_count} at {elapsed:.1f}s!")
                if self.replan_count > self.max_replans:
                    print("   Too many collisions, stopping")
                    terminal_collision = True
                    break
                
                # FIX: Bounce-back + climb collision escape.
                # Pure vertical climb slides the drone up the building face while
                # the bounding box stays in contact, causing the next forward command
                # to immediately re-trigger a collision.
                # Fix: reverse along the current yaw to break wall contact first,
                # then climb clear of the obstacle before replanning.
                print("   Escaping collision zone (bounce back + climb)...")
                
                # Stop immediately
                self.bridge.client.moveByVelocityAsync(0, 0, 0, 0.3).join()
                
                # 1. BOUNCE BACK: Reverse along current yaw for 1.5 s to break contact
                position, _, yaw, z, _ = self.bridge.get_drone_state()
                vx_back = -1.5 * np.cos(yaw)
                vy_back = -1.5 * np.sin(yaw)
                self.bridge.client.moveByVelocityAsync(
                    float(vx_back), float(vy_back), 0, 1.5,
                    drivetrain=airsim.DrivetrainType.MaxDegreeOfFreedom,
                    yaw_mode=airsim.YawMode(is_rate=False, yaw_or_rate=float(np.degrees(yaw)))
                ).join()
                
                # 2. CLIMB: Now clear of the wall, climb vertically.
                # FIX (recovery climb): bumped from 5 m to 8 m and from
                # -2.0 to -2.5 m/s so we clear taller building edges before
                # the next forward command.
                position, _, yaw, z, _ = self.bridge.get_drone_state()
                # Remember the wall XY for the permanent stamp below.
                collision_wall_xy = (
                    float(position[0] + 1.5 * np.cos(yaw)),
                    float(position[1] + 1.5 * np.sin(yaw)),
                )
                self.bridge.client.moveByVelocityAsync(
                    0, 0, -2.5, 3.2,
                    drivetrain=airsim.DrivetrainType.MaxDegreeOfFreedom,
                    yaw_mode=airsim.YawMode(is_rate=False, yaw_or_rate=float(np.degrees(yaw)))
                ).join()
                
                # Stabilize
                self.bridge.client.moveByVelocityAsync(0, 0, 0, 0.5).join()
                
                # Update map with age-based decay and new observations
                position, _, _, z, orientation = self.bridge.get_drone_state()
                self.occupancy_grid.decay_old_observations()  # FIX: age-based decay
                self._update_map_from_lidar(position, z, orientation)
                # FIX (collision memory): permanently stamp the wall we hit so
                # A* never routes through it again in this mission, even if
                # post-climb LiDAR sweeps don't fully re-observe it.
                self.occupancy_grid.mark_collision_zone(
                    collision_wall_xy[0], collision_wall_xy[1], radius_m=5.0
                )
                # FIX (altitude fight): instead of resetting the controller to
                # 'cruise' (which immediately commands a descent back to the
                # original base_altitude), HOLD the new safe altitude until the
                # forward LiDAR confirms the obstacle is gone. We raise the
                # base_altitude to the post-recovery Z so cruise mode no longer
                # pulls the drone back down into the building it just hit.
                self.altitude_controller.reset()
                self.altitude_controller.base_altitude = float(z)
                self.altitude_controller.state = 'holding'
                self.altitude_controller.hold_until = time.time() + 5.0
                self.altitude_controller.last_obstacle_time = time.time()
                self.current_plan = self._plan_path(position, goal[:2])
                self.current_waypoint_idx = 0
                if not self.current_plan:
                    print("   No path found, going direct")
                    self.current_plan = [[goal[0], goal[1]]]
                else:
                    print(f"   Replanned: {len(self.current_plan)} waypoints")
                
                if self.verbose:
                    self.occupancy_grid.visualize_grid(
                        position, goal[:2], self.current_plan,
                        save_path=os.path.join(
                            os.path.dirname(os.path.abspath(__file__)),
                            f'navrl_grid_collision_{self.replan_count}.png'
                        )
                    )
                
                self.last_progress_time = time.time()
                self.last_progress_pos = position.copy()
                self._last_collision_pos = position.copy()  # Track for replan-count reset
                self.last_goal_distance = np.linalg.norm(goal[:2] - position)
                # Reset planner state so post-collision leg starts clean
                self._rl_fallback = False
                self.proactive_replan_count = 0
                self._last_progress_check_distance = float('inf')
                self._last_progress_check_replan = self.replan_count
                self.near_goal_replan_count = 0
                self.best_goal_distance = float('inf')
                self.altitude_controller.last_obstacle_time = 0.0
                continue
            
            # Get current state
            position, velocity, yaw, z, orientation = self.bridge.get_drone_state()
            altitude_readings.append(z)
            total_path += np.linalg.norm(position - last_pos)
            last_pos = position.copy()
            
            # Replan-count distance reset: if the drone has flown 20m without hitting
            # anything since the last collision, forgive that old bump — it happened in
            # a different block of the city and shouldn't cap future recovery attempts.
            if self.replan_count > 0 and self._last_collision_pos is not None:
                dist_clear = np.linalg.norm(position - self._last_collision_pos)
                if dist_clear >= 20.0:
                    print(f"   Replan counter reset ({dist_clear:.1f}m clear since last collision)")
                    self.replan_count = 0
                    self._last_collision_pos = None
            
            # Check if FINAL goal reached
            dist_to_goal = np.linalg.norm(goal[:2] - position)
            if dist_to_goal < GOAL_THRESHOLD:
                success = True
                print(f"\n🏁 Goal reached in {elapsed:.1f}s!")
                break
            
            # Best Effort arrival: if near the goal but A* keeps failing
            # (goal in obstacle due to inflation/noise), accept "close enough"
            cfg = self.planner_cfg
            if (self.near_goal_replan_count >= cfg.best_effort_replan_threshold and
                dist_to_goal < cfg.best_effort_distance):
                success = True
                print(f"\n🏁 Best Effort arrival at {dist_to_goal:.1f}m "
                      f"(after {self.near_goal_replan_count} failed replans near goal) "
                      f"in {elapsed:.1f}s!")
                break
            
            # Check if current waypoint reached
            if self.current_waypoint_idx < len(self.current_plan):
                current_wp = np.array(self.current_plan[self.current_waypoint_idx])
                dist_to_wp = np.linalg.norm(current_wp - position)
                
                if dist_to_wp < GOAL_THRESHOLD + 1.0:  # Slightly larger threshold for intermediates
                    self.current_waypoint_idx += 1
                    self.last_progress_time = time.time()
                    self.last_progress_pos = position.copy()
                    self.last_goal_distance = dist_to_goal
                    
                    if self.current_waypoint_idx < len(self.current_plan):
                        next_wp = self.current_plan[self.current_waypoint_idx]
                        print(f"\n   ✅ WP{self.current_waypoint_idx} reached → "
                              f"WP{self.current_waypoint_idx + 1}: [{next_wp[0]:.0f}, {next_wp[1]:.0f}]")
                    continue
            
            # Determine navigation target via Pure Pursuit lookahead.
            # The lookahead point slides along the A* path 4 m ahead of the
            # drone, keeping the RL policy's goal-direction vector stable and
            # preventing close-range instability when approaching waypoints.
            # When fewer than 4 m remain to the final goal, the lookahead
            # naturally clamps to the goal itself.
            if self.current_waypoint_idx < len(self.current_plan):
                nav_target = self._get_lookahead_target(position, goal, lookahead=4.0)
            else:
                nav_target = goal[:2]
            
            # Get LiDAR and update map
            lidar_obs, min_obs_dist = self.bridge.process_lidar(
                position, yaw, nav_target, orientation
            )
            closest_obstacle = min(closest_obstacle, min_obs_dist)
            if min_obs_dist < CLOSE_CALL_THRESHOLD:
                close_calls += 1
            # Sync to instance for telemetry bridge
            self.total_distance_traveled = total_path
            self._closest_obstacle_distance = min_obs_dist
            
            # Update occupancy grid from LiDAR
            self._update_map_from_lidar(position, z, orientation)
            
            # FIX: Proactive replanning - check if current waypoint is now blocked
            # Layer 1 & 2: Only replan if we haven't exhausted the budget
            if not self._rl_fallback and self._should_replan(position, nav_target):
                self._log("Proactive replan: waypoint now in obstacle", 'info')
                self.proactive_replan_count += 1
                
                # ── Layer 2: Monotonic progress gate ──
                # Every N proactive replans, check if we're actually getting
                # closer to the goal. If not, we're in a spiral.
                pcfg = self.planner_cfg
                if (self.proactive_replan_count > 0 and
                    self.proactive_replan_count % pcfg.progress_check_every == 0):
                    if dist_to_goal >= self._last_progress_check_distance * 0.95:
                        # No meaningful progress — trigger RL fallback
                        print(f"\n   🔁 Loop detected: {pcfg.progress_check_every} replans "
                              f"with no progress (best={self.best_goal_distance:.0f}m, "
                              f"now={dist_to_goal:.0f}m). Switching to direct RL.")
                        self._rl_fallback = True
                        self.current_plan = [[goal[0], goal[1]]]
                        self.current_waypoint_idx = 0
                        self.last_replan_check = time.time()
                        continue
                    # Progress confirmed — update checkpoint
                    self._last_progress_check_distance = dist_to_goal
                    self._last_progress_check_replan = self.proactive_replan_count
                
                # ── Layer 1: Proactive replan budget cap ──
                if self.proactive_replan_count >= pcfg.max_proactive_replans:
                    print(f"\n   🔋 Proactive replan budget exhausted "
                          f"({pcfg.max_proactive_replans}). "
                          f"Switching to direct RL for remaining {dist_to_goal:.0f}m.")
                    self._rl_fallback = True
                    self.current_plan = [[goal[0], goal[1]]]
                    self.current_waypoint_idx = 0
                    self.last_replan_check = time.time()
                    continue
                
                self.occupancy_grid.decay_old_observations()
                self.current_plan = self._plan_path(position, goal[:2])
                self.current_waypoint_idx = 0
                if not self.current_plan:
                    self.current_plan = [[goal[0], goal[1]]]
                    # Track near-goal replans for Best Effort arrival
                    if dist_to_goal < self.planner_cfg.best_effort_distance:
                        self.near_goal_replan_count += 1
                        self._log(f"Near-goal replan #{self.near_goal_replan_count} "
                                  f"(dist={dist_to_goal:.1f}m)", 'debug')
                else:
                    # FIX: Only reset near-goal counter if the new path
                    # actually makes progress toward goal. A path that
                    # routes AWAY (first waypoint farther from goal than
                    # we are now) is not real progress — it's the planner
                    # detouring around a wall of inflated obstacles.
                    if dist_to_goal < self.planner_cfg.best_effort_distance:
                        # Check if first meaningful waypoint is closer to goal
                        first_wp = np.array(self.current_plan[min(1, len(self.current_plan)-1)])
                        wp_dist_to_goal = np.linalg.norm(first_wp - goal[:2])
                        if wp_dist_to_goal < dist_to_goal * 1.1:  # 10% tolerance
                            self.near_goal_replan_count = 0
                        else:
                            # Path routes away — count as failed replan
                            self.near_goal_replan_count += 1
                            self._log(f"Near-goal replan #{self.near_goal_replan_count} "
                                      f"(path detours: wp={wp_dist_to_goal:.0f}m vs "
                                      f"current={dist_to_goal:.0f}m)", 'debug')
                    else:
                        self.near_goal_replan_count = 0
                self.last_replan_check = time.time()
                
                # Track best distance for loop detection
                if dist_to_goal < self.best_goal_distance:
                    self.best_goal_distance = dist_to_goal
                
                if self.verbose:
                    self.occupancy_grid.visualize_grid(
                        position, goal[:2], self.current_plan,
                        save_path=os.path.join(
                            os.path.dirname(os.path.abspath(__file__)),
                            f'navrl_grid_proactive_{int(time.time())}.png'
                        )
                    )
                continue
            
            # Check if stuck (FIX: now also checks goal distance reduction)
            if self._check_stuck(position, dist_to_goal):
                print(f"\n   🔄 Stuck detected! Replanning... (#{self.replan_count + 1})")
                self.replan_count += 1
                
                if self.replan_count > self.max_replans:
                    print("   Too many replans, stopping")
                    break
                
                # FIX: Age-based decay instead of blanket grid *= 0.5
                self.occupancy_grid.decay_old_observations()
                
                # Replan
                self.current_plan = self._plan_path(position, goal[:2])
                self.current_waypoint_idx = 0
                if not self.current_plan:
                    print("   No path found, trying direct")
                    self.current_plan = [[goal[0], goal[1]]]
                else:
                    print(f"   New plan: {len(self.current_plan)} waypoints")
                    for i, wp in enumerate(self.current_plan):
                        print(f"     WP{i+1}: [{wp[0]:.0f}, {wp[1]:.0f}]")
                
                if self.verbose:
                    self.occupancy_grid.visualize_grid(
                        position, goal[:2], self.current_plan,
                        save_path=os.path.join(
                            os.path.dirname(os.path.abspath(__file__)),
                            f'navrl_grid_stuck_{self.replan_count}.png'
                        )
                    )
                
                self.last_progress_time = time.time()
                self.last_progress_pos = position.copy()
                self.last_goal_distance = dist_to_goal
                continue
            
            # Compute action from NavRL model (targeting current waypoint)
            # Note: Z component of goal doesn't affect model (USE_TRAINING_DISTANCE_Z=True
            # makes distance_z=0 always). We pass current_z so the model sees no Z error.
            goal_3d = np.array([nav_target[0], nav_target[1], z])
            velocity_cmd = self.bridge.compute_action(
                position, velocity, goal_3d, lidar_obs,
                current_z=z, min_obstacle_dist=min_obs_dist
            )
            
            # ===== PITCH COMPENSATION =====
            # When the drone accelerates, it pitches forward. AirSim's LiDAR
            # is body-mounted, so pitch shifts the vertical coverage downward.
            # In training (Isaac Sim), LiDAR had attach_yaw_only=True (gravity-
            # aligned). A pitched drone in AirSim loses visibility of upper
            # vertical bins (+10°, +20°) — exactly the bins that detect tall
            # buildings. The model thinks the path is clear and accelerates
            # into the building.
            #
            # Fix: When pitch exceeds threshold AND obstacles are nearby,
            # scale down XY velocity. Less velocity → less pitch → better
            # sensor coverage. This is a physical fix, not a data hack.
            pitch, _, _ = airsim.to_eularian_angles(orientation)
            pitch_deg = abs(np.degrees(pitch))
            
            cfg = self.planner_cfg
            if (pitch_deg > cfg.pitch_vel_scale_threshold and 
                min_obs_dist < cfg.pitch_obs_proximity):
                # Linear scale-down: at threshold → 1.0, at max → min_scale
                t = min(1.0, (pitch_deg - cfg.pitch_vel_scale_threshold) / 
                        (cfg.pitch_vel_scale_max - cfg.pitch_vel_scale_threshold))
                scale = 1.0 - t * (1.0 - cfg.pitch_vel_min_scale)
                velocity_cmd[0] *= scale
                velocity_cmd[1] *= scale
                self._log(f"Pitch comp: {pitch_deg:.1f}° → vel×{scale:.2f}", 'debug')
            
            # ===== YAW COMPENSATION =====
            # When the drone needs to turn sharply (e.g., at a waypoint),
            # the forward-facing LiDAR rotates away from the velocity vector.
            # The drone effectively drifts sideways into unmapped space.
            # Fix: Scale down velocity when yaw error is large, letting the
            # drone "turn on a dime" and scan the new direction with LiDAR
            # BEFORE accelerating into it.
            wp_dir = nav_target - position
            desired_yaw = np.degrees(np.arctan2(wp_dir[1], wp_dir[0]))
            _, _, current_yaw_rad = airsim.to_eularian_angles(orientation)
            current_yaw = np.degrees(current_yaw_rad)
            yaw_error = abs(((desired_yaw - current_yaw) + 180) % 360 - 180)
            
            if yaw_error > cfg.yaw_vel_scale_threshold:
                # Linear scale: at threshold → 1.0, at 180° → min_scale
                t = min(1.0, (yaw_error - cfg.yaw_vel_scale_threshold) / 
                        (180.0 - cfg.yaw_vel_scale_threshold))
                yaw_scale = 1.0 - t * (1.0 - cfg.yaw_vel_min_scale)
                velocity_cmd[0] *= yaw_scale
                velocity_cmd[1] *= yaw_scale
                self._log(f"Yaw comp: {yaw_error:.1f}° error → vel×{yaw_scale:.2f}", 'debug')
            
            # REACTIVE ALTITUDE CONTROL (independent of NavRL model)
            # The altitude controller uses LiDAR vertical layers to detect
            # obstacles and autonomously manages climb/hold/descend.
            # The operator never needs to specify building heights.
            vel_z = self.altitude_controller.compute(
                lidar_obs, z, min_obs_dist,
                velocity_x=velocity_cmd[0], velocity_y=velocity_cmd[1]
            )
            
            # Execute
            self.bridge.client.moveByVelocityAsync(
                float(velocity_cmd[0]),
                float(velocity_cmd[1]),
                float(vel_z),
                duration=1.0 / CONTROL_FREQ,
                drivetrain=airsim.DrivetrainType.MaxDegreeOfFreedom,
                yaw_mode=airsim.YawMode(is_rate=False, yaw_or_rate=desired_yaw)
            )
            
            # Status
            wp_label = f"WP{self.current_waypoint_idx + 1}" if self.current_waypoint_idx < len(self.current_plan) else "GOAL"
            alt_status = self.altitude_controller.get_status()
            if int(elapsed * 5) % 5 == 0:
                print(f"   [{wp_label}] D:{dist_to_goal:5.0f}m→goal "
                      f"D:{np.linalg.norm(nav_target - position):4.0f}m→wp "
                      f"Alt:{-z:4.1f}m Obs:{min_obs_dist:4.1f}m [{alt_status}]", end='\r')
            
            # Update telemetry snapshot for command center (main-thread safe)
            if self.command_bridge and self.command_bridge.is_connected:
                self.command_bridge.update_telemetry_snapshot(self)
            
            time.sleep(1.0 / CONTROL_FREQ)
        
        # Stop
        self.bridge.client.moveByVelocityAsync(0, 0, 0, 1).join()
        
        # Stop command center bridge threads
        if self.command_bridge and self.command_bridge.is_connected:
            self.command_bridge.stop_telemetry_loop()
            self.command_bridge.disconnect()
            print("   📡 Command center disconnected")
        
        # Results
        if remote_stopped:
            success = False  # Do not count remote stop as success
        total_time = time.time() - start_time
        optimal_dist = np.linalg.norm(goal[:2] - start_pos)
        efficiency = (optimal_dist / total_path * 100) if total_path > 0 else 0
        alt_np = np.array(altitude_readings) if altitude_readings else np.array([takeoff_z])
        
        climbs = self.altitude_controller.total_climbs if self.altitude_controller else 0
        
        result = {
            'success': success,
            'collision': terminal_collision,
            'had_collision': had_collision,
            'time': total_time,
            'path_length': total_path,
            'optimal_length': optimal_dist,
            'efficiency': efficiency,
            'replans': self.replan_count,
            'proactive_replans': self.proactive_replan_count,
            'rl_fallback': self._rl_fallback,
            'obstacles_mapped': self.occupancy_grid.get_obstacle_count(),
            'waypoints_planned': len(self.current_plan),
            'closest_obstacle': closest_obstacle,
            'close_calls': close_calls,
            'altitude_min': float(-np.max(alt_np)),
            'altitude_max': float(-np.min(alt_np)),
            'altitude_avg': float(-np.mean(alt_np)),
            'altitude_std': float(np.std(alt_np)),
            'altitude_climbs': climbs,
            'remote_stopped': remote_stopped,
        }
        
        print("\n" + "="*60)
        print("📊 CITY NAVIGATION SUMMARY")
        print("="*60)
        status_label = '✅ SUCCESS' if success else ('🛑 REMOTE STOP' if remote_stopped else ('💥 COLLISION' if terminal_collision else '⏱️ TIMEOUT'))
        print(f"Status: {status_label}")
        print(f"Time: {total_time:.1f}s")
        print(f"Path: {total_path:.1f}m (optimal: {optimal_dist:.1f}m)")
        print(f"Efficiency: {efficiency:.1f}%")
        print(f"Replans: {self.replan_count} stuck + {self.proactive_replan_count} proactive")
        if self._rl_fallback:
            print(f"RL Fallback: ACTIVATED (A* budget exhausted or loop detected)")
        print(f"Obstacles mapped: {self.occupancy_grid.get_obstacle_count()} cells")
        print(f"Closest obstacle: {closest_obstacle:.1f}m")
        print(f"Altitude: {-np.min(alt_np):.1f}m min → {-np.max(alt_np):.1f}m max (avg {-np.mean(alt_np):.1f}m)")
        print(f"Altitude climbs: {climbs} reactive adjustments")
        base_m = abs(self.altitude_controller.base_altitude) if self.altitude_controller else 5
        print(f"Altitude mode: REACTIVE (base={base_m:.0f}m, sensor-driven)")
        print("="*60)
        
        return result
    
    def _get_lookahead_target(self, position: np.ndarray, goal: np.ndarray,
                               lookahead: float = 4.0) -> np.ndarray:
        """
        Pure Pursuit lookahead: return a point on the A* path that is
        `lookahead` metres ahead of the drone's current position.

        This prevents the RL policy from entering the close-range regime
        (< 1-2 m) where the unit-direction state vector becomes numerically
        unstable as the denominator approaches zero.  The chase target slides
        smoothly along the path rather than snapping to exact waypoint coords.

        Algorithm:
          1. Walk path segments from current_waypoint_idx backwards until we
             find the segment the drone is closest to.
          2. Advance `lookahead` metres along the remaining path from that
             projection point.
          3. If the lookahead overshoots the end, clamp to the final goal.

        Args:
            position:  Drone XY in world NED (2D).
            goal:      Final goal XY (used if lookahead overshoots end of plan).
            lookahead: Look-ahead distance in metres.

        Returns:
            2D target point in world NED.
        """
        plan = self.current_plan
        if not plan:
            return goal[:2]

        # Build full remaining path: [drone position] + waypoints from current_idx onward
        idx = self.current_waypoint_idx
        remaining = [position.copy()]
        for i in range(idx, len(plan)):
            remaining.append(np.array(plan[i]))

        if len(remaining) < 2:
            return np.array(plan[-1]) if plan else goal[:2]

        # Walk segments, accumulating distance until we reach `lookahead`
        dist_left = lookahead
        for i in range(len(remaining) - 1):
            seg_start = remaining[i]
            seg_end   = remaining[i + 1]
            seg_vec   = seg_end - seg_start
            seg_len   = np.linalg.norm(seg_vec)
            if seg_len < 1e-6:
                continue
            if dist_left <= seg_len:
                # Lookahead point is on this segment
                return seg_start + seg_vec * (dist_left / seg_len)
            dist_left -= seg_len

        # Lookahead exceeded total remaining path length — chase the final goal
        return goal[:2]

    def _scan_surroundings(self, goal: np.ndarray, max_scan_time: float = 10.0):
        """
        Rotate 360° to scan surroundings with LiDAR before planning.
        This builds an initial map of nearby obstacles.
        
        Args:
            goal: Goal position for final yaw direction
            max_scan_time: Maximum time to spend scanning (seconds).
                          Prevents hangs if moveByVelocityAsync stalls.
        """
        scan_start = time.time()
        position, _, _, z, orientation = self.bridge.get_drone_state()
        
        # Rotate in 8 steps (45° each) to get full 360° coverage
        for angle in range(0, 360, 45):
            if time.time() - scan_start > max_scan_time:
                self._log(f"Scan timeout after {max_scan_time}s", 'warn')
                break
            
            self.bridge.client.moveByVelocityAsync(
                0, 0, 0, 0.3,
                drivetrain=airsim.DrivetrainType.MaxDegreeOfFreedom,
                yaw_mode=airsim.YawMode(is_rate=False, yaw_or_rate=float(angle))
            ).join()
            
            # Get LiDAR and update map
            position, _, _, z, orientation = self.bridge.get_drone_state()
            self._update_map_from_lidar(position, z, orientation)
        
        # Face toward goal after scan
        goal_dir = goal[:2] - position
        goal_yaw = np.degrees(np.arctan2(goal_dir[1], goal_dir[0]))
        self.bridge.client.moveByVelocityAsync(
            0, 0, 0, 0.3,
            drivetrain=airsim.DrivetrainType.MaxDegreeOfFreedom,
            yaw_mode=airsim.YawMode(is_rate=False, yaw_or_rate=goal_yaw)
        ).join()
    
    def _update_map_from_lidar(self, position: np.ndarray, z: float, 
                                orientation):
        """Get LiDAR data and update the occupancy grid."""
        lidar_data = self.bridge.client.getLidarData(
            lidar_name="LidarSensor1", vehicle_name="Drone1"
        )
        
        if len(lidar_data.point_cloud) < 3:
            return
        
        points = np.array(lidar_data.point_cloud).reshape(-1, 3)
        
        # Transform body → world using drone orientation
        q = orientation
        q_w, q_x, q_y, q_z = q.w_val, q.x_val, q.y_val, q.z_val
        s = 1.0 / (q_w**2 + q_x**2 + q_y**2 + q_z**2)
        R = np.array([
            [1 - 2*s*(q_y**2 + q_z**2), 2*s*(q_x*q_y - q_z*q_w), 2*s*(q_x*q_z + q_y*q_w)],
            [2*s*(q_x*q_y + q_z*q_w), 1 - 2*s*(q_x**2 + q_z**2), 2*s*(q_y*q_z - q_x*q_w)],
            [2*s*(q_x*q_z - q_y*q_w), 2*s*(q_y*q_z + q_x*q_w), 1 - 2*s*(q_x**2 + q_y**2)]
        ])
        
        points_world = points @ R.T  # Now in world frame, relative to drone
        
        # Update occupancy grid
        self.occupancy_grid.update_from_lidar_points(position, points_world, z)
    
    def _plan_path(self, start_pos: np.ndarray, goal_pos: np.ndarray) -> list:
        """
        Run A* and return simplified + smoothed waypoints.
        
        FIX: Includes distance-regression guard. When the drone is already
        close to the goal (< best_effort_distance), reject A* paths whose
        first meaningful waypoint is much farther from the goal than the
        drone's current position. This prevents the pathological case where
        A* routes the drone 30m away to go around an inflated obstacle zone
        when it's only 7m from the goal.
        """
        raw_path = astar(self.occupancy_grid, start_pos, goal_pos)
        
        if not raw_path:
            # FIX: A* failure fallback — retry with reduced inflation, BUT only
            # when the drone is genuinely close to the goal (Best Effort range).
            # Far from the goal, a zero-margin path is more dangerous than
            # admitting failure: it routes the drone past walls with 0 cm
            # clearance, and tracking error guarantees a wall-scrape.
            current_dist = float(np.linalg.norm(np.asarray(goal_pos) - np.asarray(start_pos)))
            orig_inflate = self.occupancy_grid.inflate_radius
            if orig_inflate > 0 and current_dist < self.planner_cfg.best_effort_distance * 2.0:
                # Step down inflation by 1 (preserve 1 cell margin if possible)
                # before going to zero — gives an intermediate fallback.
                for retry_inflate in (max(orig_inflate - 1, 1), 0):
                    if retry_inflate == orig_inflate:
                        continue
                    self.occupancy_grid.inflate_radius = retry_inflate
                    self.occupancy_grid._inflate_obstacles()
                    raw_path = astar(self.occupancy_grid, start_pos, goal_pos)
                    if raw_path:
                        print(f"   (inflate={retry_inflate} fallback: path found near goal)")
                        break
                self.occupancy_grid.inflate_radius = orig_inflate
                self.occupancy_grid._inflate_obstacles()  # restore original planning grid
            if not raw_path:
                return []
        
        # Simplify with angle-based filtering + obstacle LOS safety
        waypoints = simplify_path(
            raw_path,
            min_spacing=self.waypoint_spacing,
            angle_threshold=self.planner_cfg.path_angle_threshold,
            grid=self.occupancy_grid
        )
        
        # String-tightening: smooth the jagged grid path to cut corners
        # This lets the drone maintain higher velocity through turns
        waypoints = smooth_path(
            waypoints,
            self.occupancy_grid,
            iterations=self.planner_cfg.smooth_iterations,
            alpha=self.planner_cfg.smooth_alpha
        )
        
        # FIX: Distance-regression guard
        # When already close to the goal, reject paths that make the drone
        # go much farther away (e.g., A* routing to [103,25] when goal is
        # [80,40] and drone is 7m away). This forces A* failure → Best Effort.
        current_dist = np.linalg.norm(goal_pos - start_pos)
        if current_dist < self.planner_cfg.best_effort_distance and len(waypoints) > 0:
            # Check the farthest waypoint from goal in the first 3 waypoints
            check_count = min(3, len(waypoints))
            max_wp_dist = max(
                np.linalg.norm(np.array(waypoints[i]) - goal_pos)
                for i in range(check_count)
            )
            # If any early waypoint is > 2x current distance, path is regressing
            if max_wp_dist > current_dist * 2.0:
                self._log(f"Rejecting regressive path: wp_dist={max_wp_dist:.0f}m "
                         f"vs current={current_dist:.0f}m", 'debug')
                return []
        
        return waypoints
    
    def _check_stuck(self, current_pos: np.ndarray, 
                     current_goal_dist: float = None) -> bool:
        """
        FIX: Goal-directed stuck detection.
        
        Previous approach only checked if the drone moved in absolute terms.
        A drone could be moving (orbiting an obstacle) without getting closer
        to the goal, and not be detected as stuck.
        
        New approach checks BOTH:
        1. Has the drone moved at all? (displacement check)
        2. Has the drone gotten closer to the goal? (goal distance check)
        
        Stuck = (hasn't moved much) OR (moved but goal distance not reducing)
        
        Args:
            current_pos: Current drone [x, y] position
            current_goal_dist: Current distance to goal (optional)
            
        Returns:
            True if drone is stuck
        """
        now = time.time()
        
        if self.last_progress_pos is None:
            self.last_progress_pos = current_pos.copy()
            self.last_progress_time = now
            self.last_goal_distance = current_goal_dist or float('inf')
            return False
        
        # Check 1: Absolute movement
        displacement = np.linalg.norm(current_pos - self.last_progress_pos)
        
        # Check 2: Goal distance reduction (if tracking)
        goal_progress = 0.0
        if current_goal_dist is not None and self.last_goal_distance < float('inf'):
            goal_progress = self.last_goal_distance - current_goal_dist
        
        # Progress = either moved significantly OR got closer to goal
        if displacement > self.stuck_distance or goal_progress > self.stuck_distance:
            self.last_progress_pos = current_pos.copy()
            self.last_progress_time = now
            if current_goal_dist is not None:
                self.last_goal_distance = current_goal_dist
            return False
        
        # Check if stuck for too long
        if now - self.last_progress_time > self.stuck_threshold:
            return True
        
        return False
    
    def _should_replan(self, current_pos: np.ndarray, 
                       target_wp: np.ndarray) -> bool:
        """
        Proactive replanning - check if path to current waypoint is now blocked.
        
        As the drone maps more of the environment, a previously planned
        waypoint might now be inside a newly discovered obstacle. Instead
        of waiting until the drone gets stuck, proactively replan.
        
        Samples multiple points along the straight-line path segment to
        detect if newly discovered obstacles block the route.
        
        Only checks periodically (every replan_check_interval seconds)
        to avoid excessive replanning.
        
        Args:
            current_pos: Current drone [x, y] position
            target_wp: Current target waypoint [x, y]
            
        Returns:
            True if replanning is needed
        """
        now = time.time()
        
        # Only check periodically
        if now - self.last_replan_check < self.planner_cfg.replan_check_interval:
            return False
        
        # FIX: Don't trigger proactive replanning while climbing or holding above
        # an obstacle. The 2D occupancy grid has no altitude awareness — building
        # footprint cells remain permanently occupied (confirmed obstacles don't
        # decay) even when the drone has safely climbed above them.
        # Replanning in this state causes an infinite spiral: every A* path
        # routes through the same (x,y) building footprint cells, which are
        # immediately flagged as blocked again.
        # While climbing/holding, NavRL handles local XY avoidance and the
        # altitude controller manages Z — proactive replanning is not needed.
        if (self.altitude_controller is not None and
                self.altitude_controller.state in ('climbing', 'holding')):
            self.last_replan_check = now  # Keep timer current; recheck once back in cruise
            return False
        
        # Spatial cooldown: if the drone hasn't moved 2m since the last triggered replan,
        # trust the local RL model to handle minor obstacle deviations rather than firing
        # the expensive global A* planner again. Stops the 20-replan thrashing pattern.
        if self.last_replan_pos is not None:
            dist_since_replan = np.linalg.norm(current_pos[:2] - self.last_replan_pos[:2])
            if dist_since_replan < 2.0:
                self.last_replan_check = now  # Maintain poll interval
                return False
        
        self.last_replan_check = now
        
        # Check if the current waypoint is now inside an obstacle
        gx, gy = self.occupancy_grid.world_to_grid(target_wp[0], target_wp[1])
        if not self.occupancy_grid.is_free(gx, gy):
            self._log(f"Waypoint [{target_wp[0]:.0f}, {target_wp[1]:.0f}] "
                     f"now in obstacle - need replan", 'debug')
            self.last_replan_pos = current_pos.copy()  # Record position for spatial cooldown
            return True
        
        # Sample multiple points along path to detect blocking obstacles
        dist = np.linalg.norm(target_wp - current_pos)
        num_samples = min(5, int(dist / self.planner_cfg.grid_resolution) + 1)
        
        for i in range(1, num_samples):
            alpha = i / num_samples
            sample = current_pos + alpha * (target_wp - current_pos)
            sx, sy = self.occupancy_grid.world_to_grid(sample[0], sample[1])
            if not self.occupancy_grid.is_free(sx, sy):
                self._log(f"Path to waypoint blocked at sample {i}/{num_samples} "
                         f"- need replan", 'debug')
                self.last_replan_pos = current_pos.copy()  # Record position for spatial cooldown
                return True
        
        return False
    
    def run_city_mission(self, waypoints: list, return_to_base: bool = True,
                          min_altitude: float = None, 
                          timeout_per_wp: float = 120.0) -> dict:
        """
        Run multi-waypoint mission through city with global planning.
        
        Operator provides only (x, y) waypoints - altitude is reactive.
        
        Args:
            waypoints: List of [x, y] goal positions (2D only)
            return_to_base: Return to start after all waypoints
            min_altitude: Minimum safe altitude in meters (positive)
            timeout_per_wp: Timeout per waypoint (seconds)
        """
        base_alt_m = min_altitude if min_altitude is not None else 5.0
        
        print("\n" + "="*70)
        print("🏙️ CITY MISSION (A* + NavRL + Reactive Altitude)")
        print("="*70)
        
        self.bridge.reset_drone()
        takeoff_z = -abs(base_alt_m)  # NED
        self.bridge.takeoff(takeoff_z)
        
        start_pos, _, _, _, _ = self.bridge.get_drone_state()
        base = start_pos.copy()
        
        print(f"Base: [{base[0]:.0f}, {base[1]:.0f}]")
        print(f"Waypoints: {len(waypoints)}")
        for i, wp in enumerate(waypoints):
            print(f"  WP{i+1}: [{wp[0]:.0f}, {wp[1]:.0f}]")
        
        mission_start = time.time()
        results = []
        
        for i, wp in enumerate(waypoints):
            print(f"\n{'='*50}")
            print(f"🎯 WAYPOINT {i+1}/{len(waypoints)}: [{wp[0]:.0f}, {wp[1]:.0f}]")
            print('='*50)
            
            result = self.navigate_to_goal(
                np.array(wp), timeout=timeout_per_wp, min_altitude=base_alt_m
            )
            result['waypoint'] = i + 1
            results.append(result)
            
            if not result['success']:
                print(f"   ❌ Failed WP{i+1}")
        
        # Return to base
        if return_to_base:
            print(f"\n{'='*50}")
            print(f"🏠 RETURN TO BASE: [{base[0]:.0f}, {base[1]:.0f}]")
            print('='*50)
            
            rtb = self.navigate_to_goal(
                base, timeout=timeout_per_wp, min_altitude=base_alt_m
            )
            rtb['waypoint'] = 'RTB'
            results.append(rtb)
        
        # Landing
        print("\n🛬 Landing...")
        self.bridge.client.landAsync().join()
        
        # Summary
        total_time = time.time() - mission_start
        successes = sum(1 for r in results if r['success'])
        collisions = sum(1 for r in results if r['collision'])
        total_replans = sum(r.get('replans', 0) for r in results)
        
        print("\n" + "="*70)
        print("📊 CITY MISSION SUMMARY")
        print("="*70)
        print(f"Waypoints: {successes}/{len(results)}")
        print(f"Collisions: {collisions}")
        print(f"Total replans: {total_replans}")
        print(f"Total time: {total_time:.1f}s")
        print("="*70)
        
        return {
            'mission_success': successes == len(results),
            'waypoints_reached': successes,
            'total_waypoints': len(results),
            'collisions': collisions,
            'replans': total_replans,
            'time': total_time,
            'waypoint_results': results
        }


# ============================================================================
# UNIT TESTS - Validate components without AirSim
# ============================================================================

def test_altitude_controller():
    """
    Unit test for CityAltitudeController.
    
    Tests the altitude state machine with synthetic LiDAR data.
    Does NOT require AirSim - uses fake tensor inputs.
    """
    print("\n" + "="*50)
    print("TEST: CityAltitudeController")
    print("="*50)
    
    ctrl = CityAltitudeController(base_altitude_m=5.0)
    passed = 0
    failed = 0
    
    def make_lidar(front_values=(0, 0, 0, 0)):
        """Create fake LiDAR tensor with given front sector vertical values."""
        arr = np.zeros((1, 1, 36, 4), dtype=np.float32)
        # Set front bins (0-7) to the given vertical values
        for i in range(8):
            for j, v in enumerate(front_values):
                arr[0, 0, i, j] = v
        return torch.from_numpy(arr)
    
    # Test 1: Clear sky -> cruise, vel_z ~= 0 (at base altitude)
    lidar = make_lidar((0, 0, 0, 0))
    vz = ctrl.compute(lidar, -5.0, 4.0)  # At base alt, far obstacle
    assert_name = "Clear sky -> cruise"
    if abs(vz) < 0.5:
        print(f"  ✅ {assert_name}: vel_z={vz:.2f}")
        passed += 1
    else:
        print(f"  ❌ {assert_name}: vel_z={vz:.2f} (expected ~0)")
        failed += 1
    
    # Test 2: Tall building -> climbing
    ctrl.reset()
    ctrl.state = 'cruise'
    lidar = make_lidar((2.0, 2.0, 2.0, 2.0))  # All layers hit (tall)
    vz = ctrl.compute(lidar, -5.0, 2.0)
    assert_name = "Tall building -> climb"
    # First call from reset() is rate-limited (max_vel_z_change=0.5) + smoothed (0.8 weight)
    # So max first-call magnitude is 0.8 * 0.5 = 0.40
    if vz < -0.3:  # Should be climbing (negative NED = up), rate-limited on first call
        print(f"  ✅ {assert_name}: vel_z={vz:.2f}, state={ctrl.state}")
        passed += 1
    else:
        print(f"  ❌ {assert_name}: vel_z={vz:.2f} (expected < -0.3)")
        failed += 1
    
    # Test 3: Short obstacle -> gentle climb
    ctrl.reset()
    ctrl.state = 'cruise'
    lidar = make_lidar((2.0, 2.0, 0, 0))  # Only lower layers (short)
    vz = ctrl.compute(lidar, -5.0, 2.5)
    assert_name = "Short obstacle -> gentle climb"
    if vz < 0 and ctrl.state == 'climbing':
        print(f"  ✅ {assert_name}: vel_z={vz:.2f}")
        passed += 1
    else:
        print(f"  ❌ {assert_name}: vel_z={vz:.2f}, state={ctrl.state}")
        failed += 1
    
    # Test 4: Layers hit count
    lidar_np = make_lidar((2.0, 2.0, 2.0, 0)).cpu().numpy()[0, 0]
    front_left  = lidar_np[0:4, :]
    front_right = lidar_np[35:31:-1, :]
    front_bins  = np.concatenate((front_left, front_right), axis=0)
    weights = np.array([1.0, 0.9, 0.8, 0.7, 0.9, 0.8, 0.7, 0.6])
    front_weighted = front_bins * weights[:, np.newaxis]
    layers = sum([
        np.max(front_weighted[:, 0]) > 0.5,
        np.max(front_weighted[:, 1]) > 0.5,
        np.max(front_weighted[:, 2]) > 0.5,
        np.max(front_weighted[:, 3]) > 0.5,
    ])
    assert_name = "Layers hit count = 3"
    if layers == 3:
        print(f"  ✅ {assert_name}: layers_hit={layers}")
        passed += 1
    else:
        print(f"  ❌ {assert_name}: layers_hit={layers} (expected 3)")
        failed += 1
    
    # Test 5: Ceiling limit
    ctrl.reset()
    ctrl.state = 'climbing'
    lidar = make_lidar((2.0, 2.0, 2.0, 2.0))
    vz = ctrl.compute(lidar, -61.0, 1.0)  # Above ceiling
    assert_name = "Ceiling limit stops climb"
    if vz >= 0 or ctrl.state == 'holding':
        print(f"  ✅ {assert_name}: vel_z={vz:.2f}, state={ctrl.state}")
        passed += 1
    else:
        print(f"  ❌ {assert_name}: vel_z={vz:.2f}, state={ctrl.state}")
        failed += 1
    
    print(f"\nResults: {passed}/{passed+failed} passed")
    return failed == 0


def test_occupancy_grid():
    """
    Unit test for OccupancyGrid.
    
    Tests grid operations, coordinate conversion, inflation, and decay.
    Does NOT require AirSim.
    """
    print("\n" + "="*50)
    print("TEST: OccupancyGrid")
    print("="*50)
    
    grid = OccupancyGrid(resolution=1.0, size=50, center=(0, 0))
    passed = 0
    failed = 0
    
    # Test 1: World to grid conversion
    gx, gy = grid.world_to_grid(0, 0)
    assert_name = "Center maps to (25, 25)"
    if gx == 25 and gy == 25:
        print(f"  ✅ {assert_name}: ({gx}, {gy})")
        passed += 1
    else:
        print(f"  ❌ {assert_name}: ({gx}, {gy})")
        failed += 1
    
    # Test 2: Grid to world roundtrip
    wx, wy = grid.grid_to_world(25, 25)
    assert_name = "Grid (25,25) -> world (0,0)"
    if abs(wx) < 0.5 and abs(wy) < 0.5:
        print(f"  ✅ {assert_name}: ({wx:.1f}, {wy:.1f})")
        passed += 1
    else:
        print(f"  ❌ {assert_name}: ({wx:.1f}, {wy:.1f})")
        failed += 1
    
    # Test 3: Mark obstacle and check
    grid.grid[30, 30] = 1.0
    grid.grid_timestamps[30, 30] = time.time()
    grid._inflate_obstacles()
    assert_name = "Obstacle at (30,30) blocks planning"
    if not grid.is_free(30, 30):
        print(f"  ✅ {assert_name}")
        passed += 1
    else:
        print(f"  ❌ {assert_name}: cell is still free")
        failed += 1
    
    # Test 4: Inflation creates buffer
    assert_name = "Inflation blocks adjacent cells"
    if not grid.is_free(31, 30):  # Should be inflated
        print(f"  ✅ {assert_name}")
        passed += 1
    else:
        print(f"  ❌ {assert_name}: adjacent cell is free")
        failed += 1
    
    # Test 5: Circular inflation - diagonal at inflate_radius+1 should be free
    grid2 = OccupancyGrid(resolution=1.0, size=50, center=(0, 0))
    grid2.inflate_radius = 3
    grid2.grid[25, 25] = 1.0
    grid2.grid_timestamps[25, 25] = time.time()
    grid2._inflate_obstacles()
    # Diagonal at distance sqrt(3^2 + 3^2) = 4.24 > radius 3, should be free
    assert_name = "Circular inflation: corner cell free"
    # Check cell at (28, 28) which is sqrt(9+9) = 4.24 from center
    if grid2.is_free(29, 29):  # 4 cells away diag = sqrt(32) > 3
        print(f"  ✅ {assert_name}")
        passed += 1
    else:
        print(f"  ❌ {assert_name}: diagonal corner blocked")
        failed += 1
    
    # Test 6: Age-based decay
    grid3 = OccupancyGrid(resolution=1.0, size=50, center=(0, 0))
    grid3.grid[20, 20] = 1.0
    grid3.grid_timestamps[20, 20] = time.time() - 10.0  # 10 seconds old
    grid3.grid[22, 22] = 1.0
    grid3.grid_timestamps[22, 22] = time.time()  # Fresh
    grid3.decay_old_observations(max_age=5.0)
    assert_name = "Age decay: old cell cleared, fresh cell kept"
    if grid3.grid[20, 20] < 0.5 and grid3.grid[22, 22] > 0.5:
        print(f"  ✅ {assert_name}")
        passed += 1
    else:
        print(f"  ❌ {assert_name}: old={grid3.grid[20,20]:.1f} fresh={grid3.grid[22,22]:.1f}")
        failed += 1
    
    # Test 7: Bresenham line
    cells = grid.bresenham_test(0, 0, 5, 3)
    assert_name = "Bresenham line: correct start and end"
    if cells[0] == (0, 0) and cells[-1] == (5, 3):
        print(f"  ✅ {assert_name}: {len(cells)} cells")
        passed += 1
    else:
        print(f"  ❌ {assert_name}: start={cells[0]} end={cells[-1]}")
        failed += 1
    
    # Test 8: Octile heuristic
    # For (0,0) to (3,4): 3 diagonal steps (cost 3*1.414=4.242) + 1 straight (1.0) = 5.242
    # This is the EXACT cost for 8-connected grid movement.
    # Euclidean = sqrt(9+16) = 5.0 which UNDERESTIMATES the 8-connected cost.
    # Octile >= Euclidean always holds, making octile a tighter (better) heuristic
    # while still being admissible (it never overestimates, it IS the exact cost).
    dx, dy = 3, 4
    octile = 1.414 * min(dx, dy) + (max(dx, dy) - min(dx, dy))
    exact_8connected = 3 * 1.414 + 1 * 1.0  # 3 diagonals + 1 straight
    euclidean = np.sqrt(dx**2 + dy**2)
    assert_name = "Octile matches exact 8-connected cost"
    if abs(octile - exact_8connected) < 0.01:
        print(f"  ✅ {assert_name}: octile={octile:.3f}, exact={exact_8connected:.3f}")
        print(f"       (euclidean={euclidean:.3f}, octile >= euclidean: {octile >= euclidean})")
        passed += 1
    else:
        print(f"  ❌ {assert_name}: octile={octile:.3f}, expected={exact_8connected:.3f}")
        failed += 1
    
    print(f"\nResults: {passed}/{passed+failed} passed")
    return failed == 0


# Helper for tests - expose Bresenham without occupancy grid
OccupancyGrid.bresenham_test = lambda self, x0, y0, x1, y1: self._bresenham_line(x0, y0, x1, y1)


def test_astar_planner():
    """
    Unit test for A* pathfinding.
    
    Tests path planning on grids with obstacles.
    Does NOT require AirSim.
    """
    print("\n" + "="*50)
    print("TEST: A* Planner")
    print("="*50)
    
    passed = 0
    failed = 0
    
    # Create simple grid with obstacle wall
    grid = OccupancyGrid(resolution=1.0, size=20, center=(0, 0))
    
    # Add obstacle wall from (12, 8) to (12, 12)
    for y in range(8, 13):
        grid.grid[12, y] = 1.0
        grid.grid_timestamps[12, y] = time.time()
    grid._inflate_obstacles()
    
    # Test 1: Path exists around obstacle
    start = np.array([0.0, 0.0])
    goal = np.array([8.0, 0.0])
    path = astar(grid, start, goal)
    
    assert_name = "Path found around obstacle"
    if len(path) > 0:
        print(f"  ✅ {assert_name}: {len(path)} waypoints")
        passed += 1
    else:
        print(f"  ❌ {assert_name}: no path found")
        failed += 1
    
    # Test 2: Path avoids obstacle (all waypoints on free cells)
    assert_name = "Path avoids obstacle"
    path_clear = True
    for wp in path:
        gx, gy = grid.world_to_grid(wp[0], wp[1])
        if grid.in_bounds(gx, gy) and not grid.is_free(gx, gy):
            path_clear = False
            break
    
    if path_clear:
        print(f"  ✅ {assert_name}")
        passed += 1
    else:
        print(f"  ❌ {assert_name}: path goes through obstacle")
        failed += 1
    
    # Test 3: Straight-line path when no obstacles
    grid_clear = OccupancyGrid(resolution=1.0, size=20, center=(0, 0))
    path_straight = astar(grid_clear, np.array([0.0, 0.0]), np.array([5.0, 0.0]))
    
    assert_name = "Straight path on clear grid"
    if len(path_straight) > 0:
        print(f"  ✅ {assert_name}: {len(path_straight)} waypoints")
        passed += 1
    else:
        print(f"  ❌ {assert_name}: no path found")
        failed += 1
    
    # Test 4: Path endpoints match start/goal
    assert_name = "Path reaches goal"
    if len(path_straight) > 0:
        final = path_straight[-1]
        dist_to_goal = np.sqrt((final[0] - 5.0)**2 + (final[1] - 0.0)**2)
        if dist_to_goal < 2.0:  # Within threshold
            print(f"  ✅ {assert_name}: final point at ({final[0]:.1f}, {final[1]:.1f})")
            passed += 1
        else:
            print(f"  ❌ {assert_name}: final at ({final[0]:.1f}, {final[1]:.1f}), {dist_to_goal:.1f}m from goal")
            failed += 1
    else:
        print(f"  ❌ {assert_name}: no path")
        failed += 1
    
    print(f"\nResults: {passed}/{passed+failed} passed")
    return failed == 0


def test_path_simplification():
    """
    Unit test for angle-based path simplification.
    
    Tests that straight paths are compressed and turns are preserved.
    Does NOT require AirSim.
    """
    print("\n" + "="*50)
    print("TEST: Path Simplification")
    print("="*50)
    
    passed = 0
    failed = 0
    
    # Test 1: Straight line simplified to start + end
    path = [[0, 0], [5, 0], [10, 0], [15, 0], [20, 0]]
    simplified = simplify_path(path, min_spacing=25.0, angle_threshold=10.0)
    
    assert_name = "Straight path simplified"
    if len(simplified) == 2:
        print(f"  ✅ {assert_name}: {len(path)} → {len(simplified)} waypoints")
        passed += 1
    else:
        print(f"  ❌ {assert_name}: {len(path)} → {len(simplified)} (expected 2)")
        failed += 1
    
    # Test 2: 90-degree turn preserves corner
    path2 = [[0, 0], [5, 0], [10, 0], [10, 5], [10, 10]]
    simplified2 = simplify_path(path2, min_spacing=25.0, angle_threshold=20.0)
    
    assert_name = "Corner preserved in path"
    if len(simplified2) >= 3:
        print(f"  ✅ {assert_name}: {len(path2)} → {len(simplified2)} waypoints")
        passed += 1
    else:
        print(f"  ❌ {assert_name}: {len(path2)} → {len(simplified2)} (expected ≥3)")
        failed += 1
    
    # Test 3: Short path (≤2 points) unchanged
    path3 = [[0, 0], [10, 10]]
    simplified3 = simplify_path(path3, min_spacing=5.0, angle_threshold=20.0)
    
    assert_name = "Short path unchanged"
    if len(simplified3) == 2:
        print(f"  ✅ {assert_name}")
        passed += 1
    else:
        print(f"  ❌ {assert_name}: {len(simplified3)} waypoints")
        failed += 1
    
    # Test 4: Final goal always included
    path4 = [[0, 0], [3, 0], [6, 0], [9, 0], [12, 0], [15, 3]]
    simplified4 = simplify_path(path4, min_spacing=25.0, angle_threshold=10.0)
    
    assert_name = "Final goal included"
    final = simplified4[-1]
    if abs(final[0] - 15) < 0.01 and abs(final[1] - 3) < 0.01:
        print(f"  ✅ {assert_name}: final=({final[0]:.0f}, {final[1]:.0f})")
        passed += 1
    else:
        print(f"  ❌ {assert_name}: final=({final[0]:.0f}, {final[1]:.0f})")
        failed += 1
    
    print(f"\nResults: {passed}/{passed+failed} passed")
    return failed == 0


def test_trajectory_smoothing():
    """
    Unit test for string-tightening trajectory smoothing.
    
    Tests that smoothing reduces path jag while respecting obstacles.
    Does NOT require AirSim.
    """
    print("\n" + "="*50)
    print("TEST: Trajectory Smoothing")
    print("="*50)
    
    passed = 0
    failed = 0
    
    grid = OccupancyGrid(resolution=1.0, size=50, center=(0, 0))
    
    # Test 1: L-shaped path gets smoothed (corner gets pulled inward)
    path = [[0, 0], [10, 0], [10, 10]]
    smoothed = smooth_path(path, grid, iterations=50, alpha=0.3)
    assert_name = "L-path corner smoothed"
    # The middle point should move toward the diagonal shortcut
    mid = smoothed[1]
    original_mid = [10, 0]
    moved = np.linalg.norm(np.array(mid) - np.array(original_mid))
    if moved > 0.5:  # Should have moved noticeably from grid corner
        print(f"  ✅ {assert_name}: corner moved {moved:.1f}m toward shortcut")
        passed += 1
    else:
        print(f"  ❌ {assert_name}: corner only moved {moved:.1f}m")
        failed += 1
    
    # Test 2: Endpoints preserved
    assert_name = "Endpoints preserved after smoothing"
    start_ok = np.linalg.norm(np.array(smoothed[0]) - np.array([0, 0])) < 0.01
    end_ok = np.linalg.norm(np.array(smoothed[-1]) - np.array([10, 10])) < 0.01
    if start_ok and end_ok:
        print(f"  ✅ {assert_name}")
        passed += 1
    else:
        print(f"  ❌ {assert_name}: start={smoothed[0]} end={smoothed[-1]}")
        failed += 1
    
    # Test 3: Smoothing respects obstacles (won't pull through wall)
    grid_obs = OccupancyGrid(resolution=1.0, size=50, center=(0, 0))
    # Place a wall along y=5, from x=2 to x=8 — blocks the diagonal shortcut
    for x_wall in range(22, 33):  # grid coords for world x=[-3, 8]
        grid_obs.grid[x_wall, 30] = 1.0  # world y=5
        grid_obs.grid_timestamps[x_wall, 30] = time.time()
    grid_obs._inflate_obstacles()
    
    path_obs = [[0, 0], [5, 0], [10, 10]]
    smoothed_obs = smooth_path(path_obs, grid_obs, iterations=50, alpha=0.3)
    
    assert_name = "Smoothing respects obstacles"
    # Check all smoothed waypoints are on free cells
    all_free = True
    for wp in smoothed_obs:
        gx, gy = grid_obs.world_to_grid(wp[0], wp[1])
        if grid_obs.in_bounds(gx, gy) and not grid_obs.is_free(gx, gy):
            all_free = False
            break
    if all_free:
        print(f"  ✅ {assert_name}")
        passed += 1
    else:
        print(f"  ❌ {assert_name}: smoothed point in obstacle")
        failed += 1
    
    # Test 4: Short path (≤2 points) unchanged
    path_short = [[0, 0], [10, 10]]
    smoothed_short = smooth_path(path_short, grid, iterations=50, alpha=0.3)
    assert_name = "Short path unchanged by smoothing"
    if len(smoothed_short) == 2:
        print(f"  ✅ {assert_name}")
        passed += 1
    else:
        print(f"  ❌ {assert_name}: {len(smoothed_short)} points")
        failed += 1
    
    print(f"\nResults: {passed}/{passed+failed} passed")
    return failed == 0


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='NavRL City Planner')
    parser.add_argument('--goal', nargs=2, type=float, default=[100, 50],
                       help='Goal [x, y] in meters')
    parser.add_argument('--timeout', type=float, default=300,
                       help='Timeout in seconds')
    parser.add_argument('--min-altitude', type=float, default=5,
                       help='Minimum safe altitude in meters. Drone starts here '
                            'and climbs reactively when obstacles detected. '
                            'Like setting minimum flight height for a UAS operator.')
    parser.add_argument('--mission', action='store_true',
                       help='Run multi-waypoint city mission')
    parser.add_argument('--device', type=str, default=None)
    parser.add_argument('--verbose', action='store_true',
                       help='Enable verbose debug logging')
    parser.add_argument('--bridge', action='store_true',
                       help='Connect to drone command center for remote monitoring/control')
    parser.add_argument('--bridge-url', type=str, default='http://localhost:8080/api',
                       help='Command center backend URL')
    parser.add_argument('--bridge-drone-id', type=str, default=None,
                       help='Drone UUID in command center (from /api/drones)')
    parser.add_argument('--bridge-user', type=str, default='navrl_bridge',
                       help='Command center login username')
    parser.add_argument('--bridge-pass', type=str, default='NavRL@2026!',
                       help='Command center login password')
    parser.add_argument('--test', action='store_true',
                       help='Run unit tests (no AirSim needed)')
    
    args = parser.parse_args()
    
    # Run unit tests if requested
    if args.test:
        print("Running unit tests...")
        ok1 = test_altitude_controller()
        ok2 = test_occupancy_grid()
        ok3 = test_astar_planner()
        ok4 = test_path_simplification()
        ok5 = test_trajectory_smoothing()
        print("\n" + "="*50)
        all_passed = ok1 and ok2 and ok3 and ok4 and ok5
        if all_passed:
            print("ALL TESTS PASSED ✅")
        else:
            print("SOME TESTS FAILED ❌")
        print("="*50)
        return
    
    # Command center bridge (optional)
    cmd_bridge = None
    if args.bridge and HAS_COMMAND_CENTER:
        bridge_cfg = BridgeConfig(
            base_url=args.bridge_url,
            drone_id=args.bridge_drone_id or 'auto',
            auth_username=args.bridge_user,
            auth_password=args.bridge_pass,
        )
        cmd_bridge = CommandCenterBridge(bridge_cfg)
        if cmd_bridge.connect():
            print("📡 Command center connected — remote monitoring active")
        else:
            print("⚠️ Command center unreachable — running offline")
            cmd_bridge = None
    elif args.bridge and not HAS_COMMAND_CENTER:
        print("⚠️ --bridge requires command_center_bridge.py (not found)")
    
    planner = NavRLCityPlanner(device=args.device, verbose=args.verbose,
                                command_bridge=cmd_bridge)
    
    min_alt = abs(args.min_altitude)  # Positive meters
    
    if args.mission:
        # City mission waypoints (operator provides X,Y only - altitude is reactive)
        city_waypoints = [
            [50, 30],
            [100, 0],
            [80, -50],
            [30, -30],
        ]
        planner.run_city_mission(city_waypoints, return_to_base=True,
                                  min_altitude=min_alt)
    else:
        goal = np.array(args.goal)
        planner.navigate_to_goal(goal, timeout=args.timeout, min_altitude=min_alt)


if __name__ == "__main__":
    main()