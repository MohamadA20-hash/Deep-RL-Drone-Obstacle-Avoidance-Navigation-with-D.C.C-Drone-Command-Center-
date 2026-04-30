"""
Survey the AirSim environment to find obstacle locations.
Flies the drone in a grid pattern and records LiDAR readings to map obstacles.
"""
import airsim
import numpy as np
import time
import json

client = airsim.MultirotorClient()
client.confirmConnection()
client.enableApiControl(True)
client.armDisarm(True)

# Reset and takeoff
client.reset()
time.sleep(1)
client.enableApiControl(True)
client.armDisarm(True)
client.takeoffAsync().join()
client.moveToZAsync(-5.0, 3).join()  # Fly at 5m altitude for survey
time.sleep(1)

print("Starting environment survey...")
print("Scanning grid from -50 to 150 in X, -100 to 100 in Y")

obstacles = []
survey_data = []

# Survey grid - fly to positions and check for nearby objects
grid_step = 10  # meters between survey points
x_range = range(-50, 160, grid_step)
y_range = range(-100, 110, grid_step)
total = len(x_range) * len(y_range)
count = 0

for x in x_range:
    for y in y_range:
        count += 1
        # Fly to position
        client.moveToPositionAsync(float(x), float(y), -5.0, 5,
                                    timeout_sec=15).join()
        time.sleep(0.3)
        
        # Get LiDAR
        lidar = client.getLidarData("LidarSensor1", "Drone1")
        
        if len(lidar.point_cloud) >= 3:
            pts = np.array(lidar.point_cloud).reshape(-1, 3)
            # Find closest point
            dists = np.linalg.norm(pts[:, :2], axis=1)  # 2D distance from drone
            min_dist = float(np.min(dists))
            
            if min_dist < 10.0:  # Something within 10m
                # Convert to world coordinates
                drone_pos = client.getMultirotorState().kinematics_estimated.position
                world_pts = pts + np.array([drone_pos.x_val, drone_pos.y_val, drone_pos.z_val])
                
                closest_idx = np.argmin(dists)
                obs_world = world_pts[closest_idx]
                
                entry = {
                    "survey_pos": [x, y],
                    "obstacle_world": [float(obs_world[0]), float(obs_world[1]), float(obs_world[2])],
                    "min_dist": round(min_dist, 2),
                    "num_points": len(pts)
                }
                survey_data.append(entry)
                
                if min_dist < 5.0:
                    print(f"[{count}/{total}] ({x:4d},{y:4d}) OBSTACLE at dist={min_dist:.1f}m "
                          f"world=({obs_world[0]:.0f},{obs_world[1]:.0f},{obs_world[2]:.0f}) pts={len(pts)}")
                    obstacles.append(entry)
        
        if count % 50 == 0:
            print(f"  Progress: {count}/{total} ({100*count/total:.0f}%)")

# Land
client.landAsync().join()

# Save results
results = {
    "grid_step": grid_step,
    "x_range": [x_range.start, x_range.stop],
    "y_range": [y_range.start, y_range.stop],
    "num_obstacles_found": len(obstacles),
    "obstacles": obstacles,
    "all_survey_data": survey_data
}

with open("environment_survey.json", "w") as f:
    json.dump(results, f, indent=2)

print(f"\n=== SURVEY COMPLETE ===")
print(f"Found {len(obstacles)} obstacle locations")
print(f"Survey data saved to environment_survey.json")

# Print obstacle summary
if obstacles:
    obs_positions = np.array([o["obstacle_world"][:2] for o in obstacles])
    print(f"\nObstacle X range: {obs_positions[:,0].min():.0f} to {obs_positions[:,0].max():.0f}")
    print(f"Obstacle Y range: {obs_positions[:,1].min():.0f} to {obs_positions[:,1].max():.0f}")
    
    # Cluster obstacles
    print("\nObstacle clusters (approx building locations):")
    from scipy.cluster.hierarchy import fcluster, linkage
    try:
        Z = linkage(obs_positions, method='complete', metric='euclidean')
        clusters = fcluster(Z, t=15, criterion='distance')
        for c in np.unique(clusters):
            mask = clusters == c
            center = obs_positions[mask].mean(axis=0)
            spread = obs_positions[mask].std(axis=0)
            print(f"  Building ~({center[0]:.0f}, {center[1]:.0f}) spread=({spread[0]:.0f},{spread[1]:.0f})")
    except ImportError:
        # Fallback: just print unique areas
        for o in obstacles:
            print(f"  ({o['obstacle_world'][0]:.0f}, {o['obstacle_world'][1]:.0f})")
