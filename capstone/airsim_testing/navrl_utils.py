"""
NavRL Shared Utilities
======================
Common constants, frame-transform functions, and state computation
used by both the pure-RL bridge and the hybrid controller.
Extracted to eliminate duplication.

Training-derived constants and frame transforms must NOT be modified.
"""

import numpy as np
import torch


# ============================================================================
# CRITICAL: These parameters MUST match the Isaac Sim training configuration
# ============================================================================
MAX_RAY_LENGTH = 4.0          # Model trained with 4m LiDAR range
HRES_DEG = 10.0               # Horizontal resolution: 360/10 = 36 bins
VFOV_ANGLES_DEG = [-10.0, 0.0, 10.0, 20.0]  # 4 vertical bins
MAX_VELOCITY = 2.0            # Maximum velocity (m/s)
DEFAULT_FLIGHT_HEIGHT = -2.0  # Default starting altitude in NED (negative = up)
GOAL_THRESHOLD = 2.0          # Distance to consider goal reached (m)
CONTROL_FREQ = 20             # Control loop frequency (Hz)


def vec_to_new_frame(vec: torch.Tensor, goal_direction: torch.Tensor) -> torch.Tensor:
    """
    Transform a vector into a goal-relative coordinate frame.
    This is the EXACT function used in Isaac Sim training.

    The goal frame is defined as:
    - X axis: direction toward goal (normalized goal_direction)
    - Y axis: perpendicular to X, in horizontal plane (cross with Z)
    - Z axis: world up direction

    Args:
        vec: Vector to transform, shape (n, 3) or (n, m, 3)
        goal_direction: Goal direction vector, shape (n, 3)

    Returns:
        Transformed vector in goal-relative frame
    """
    if len(vec.size()) == 1:
        vec = vec.unsqueeze(0)

    # Goal direction X (normalized)
    goal_direction_x = goal_direction / goal_direction.norm(dim=-1, keepdim=True).clamp(min=1e-6)
    z_direction = torch.tensor([0, 0, 1.], device=vec.device)

    # Goal direction Y (perpendicular, in horizontal plane)
    goal_direction_y = torch.cross(z_direction.expand_as(goal_direction_x), goal_direction_x)
    goal_direction_y = goal_direction_y / goal_direction_y.norm(dim=-1, keepdim=True).clamp(min=1e-6)

    # Goal direction Z (cross of X and Y)
    goal_direction_z = torch.cross(goal_direction_x, goal_direction_y)
    goal_direction_z = goal_direction_z / goal_direction_z.norm(dim=-1, keepdim=True).clamp(min=1e-6)

    n = vec.size(0)
    if len(vec.size()) == 3:
        vec_x_new = torch.bmm(vec.view(n, vec.shape[1], 3), goal_direction_x.view(n, 3, 1))
        vec_y_new = torch.bmm(vec.view(n, vec.shape[1], 3), goal_direction_y.view(n, 3, 1))
        vec_z_new = torch.bmm(vec.view(n, vec.shape[1], 3), goal_direction_z.view(n, 3, 1))
    else:
        vec_x_new = torch.bmm(vec.view(n, 1, 3), goal_direction_x.view(n, 3, 1))
        vec_y_new = torch.bmm(vec.view(n, 1, 3), goal_direction_y.view(n, 3, 1))
        vec_z_new = torch.bmm(vec.view(n, 1, 3), goal_direction_z.view(n, 3, 1))

    vec_new = torch.cat((vec_x_new, vec_y_new, vec_z_new), dim=-1)
    return vec_new


def vec_to_world(vec: torch.Tensor, goal_direction: torch.Tensor) -> torch.Tensor:
    """
    Transform a vector from goal-relative frame back to world frame.
    This is the EXACT inverse transform used in Isaac Sim training.

    Args:
        vec: Vector in goal-relative frame
        goal_direction: Goal direction vector in world frame

    Returns:
        Vector in world frame
    """
    world_dir = torch.tensor([1., 0, 0], device=vec.device).expand_as(goal_direction)

    # Directional vector of world coordinate expressed in the local frame
    world_frame_new = vec_to_new_frame(world_dir, goal_direction)

    # Convert the velocity in the local target coordinate to the world coordinate
    world_frame_vel = vec_to_new_frame(vec, world_frame_new)
    return world_frame_vel


def get_robot_state(pos: np.ndarray, goal: np.ndarray, vel: np.ndarray,
                    target_dir: np.ndarray, device,
                    distance_z: float = None) -> torch.Tensor:
    """
    Compute robot state for the NavRL model.

    State tensor shape: (8,) = [rpos_clipped_g(3), distance_2d(1), distance_z(1), vel_g(3)]

    Args:
        pos: Robot position [x, y, z] in world frame (ENU)
        goal: Goal position [x, y, z] in world frame (ENU)
        vel: Robot velocity [vx, vy, vz] in world frame (ENU)
        target_dir: Direction to goal [dx, dy, dz]
        device: Torch device
        distance_z: Vertical distance override.  Pass ``0.0`` to replicate
            the 2D training assumption (pure-RL baseline).  Pass ``None``
            to compute the real vertical distance (hybrid controller).
    """
    rpos = goal - pos
    distance = np.linalg.norm(rpos)
    distance_2d = np.linalg.norm(rpos[:2])

    if distance_z is None:
        distance_z = rpos[2]

    target_dir_2d = np.array([target_dir[0], target_dir[1], 0.0])
    rpos_clipped = rpos / max(distance, 1e-6)

    rpos_clipped_g = vec_to_new_frame(
        torch.tensor(rpos_clipped, dtype=torch.float32, device=device),
        torch.tensor(target_dir_2d, dtype=torch.float32, device=device)
    )

    vel_g = vec_to_new_frame(
        torch.tensor(vel, dtype=torch.float32, device=device),
        torch.tensor(target_dir_2d, dtype=torch.float32, device=device)
    )

    d2 = torch.tensor(distance_2d, dtype=torch.float32, device=device).view(1, 1, 1)
    dz = torch.tensor(distance_z, dtype=torch.float32, device=device).view(1, 1, 1)

    state = torch.cat([rpos_clipped_g, d2, dz, vel_g], dim=-1).squeeze(0)
    return state
