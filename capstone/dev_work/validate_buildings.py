"""Quick validation: fly toward north building at (0.3, 29) and verify obstacles."""
import airsim
import numpy as np
import time

client = airsim.MultirotorClient()
client.confirmConnection()
client.enableApiControl(True)
client.armDisarm(True)

client.reset()
time.sleep(1)
client.enableApiControl(True)
client.armDisarm(True)
client.takeoffAsync().join()
client.moveToZAsync(-3.0, 2).join()
time.sleep(0.5)

print("Flying toward north building at (0.3, 29)...")
print("Current pos: (0, 0)")

# Fly north slowly, checking LiDAR every 5m
for target_y in range(5, 35, 5):
    client.moveToPositionAsync(0.0, float(target_y), -3.0, 2.0, timeout_sec=15).join()
    time.sleep(0.3)
    
    pos = client.getMultirotorState().kinematics_estimated.position
    lidar = client.getLidarData("LidarSensor1", "Drone1")
    
    min_dist = 999
    if len(lidar.point_cloud) >= 3:
        pts = np.array(lidar.point_cloud).reshape(-1, 3)
        dists = np.linalg.norm(pts[:, :2], axis=1)
        min_dist = float(np.min(dists))
    
    coll = client.simGetCollisionInfo()
    print(f"  Y={pos.y_val:5.1f}m | LiDAR pts={len(lidar.point_cloud)//3:4d} | "
          f"min_obs={min_dist:5.1f}m | collision={coll.has_collided}")

# Also check east toward OrnateWall area
print("\nFlying toward wall compound area...")
client.moveToPositionAsync(0.0, 0.0, -3.0, 5.0, timeout_sec=10).join()
time.sleep(0.5)

for target_x in range(20, 80, 10):
    client.moveToPositionAsync(float(target_x), -50.0, -3.0, 5.0, timeout_sec=15).join()
    time.sleep(0.3)
    
    pos = client.getMultirotorState().kinematics_estimated.position
    lidar = client.getLidarData("LidarSensor1", "Drone1")
    
    min_dist = 999
    if len(lidar.point_cloud) >= 3:
        pts = np.array(lidar.point_cloud).reshape(-1, 3)
        dists = np.linalg.norm(pts[:, :2], axis=1)
        min_dist = float(np.min(dists))
    
    coll = client.simGetCollisionInfo()
    print(f"  ({pos.x_val:5.1f},{pos.y_val:5.1f}) | LiDAR pts={len(lidar.point_cloud)//3:4d} | "
          f"min_obs={min_dist:5.1f}m | collision={coll.has_collided}")

# Check south building cluster
print("\nFlying toward south Building_C cluster...")
client.moveToPositionAsync(0.0, 0.0, -3.0, 5.0, timeout_sec=10).join()
time.sleep(0.5)

for target_y in range(-20, -100, -10):
    client.moveToPositionAsync(0.0, float(target_y), -3.0, 5.0, timeout_sec=15).join()
    time.sleep(0.3)
    
    pos = client.getMultirotorState().kinematics_estimated.position
    lidar = client.getLidarData("LidarSensor1", "Drone1")
    
    min_dist = 999
    if len(lidar.point_cloud) >= 3:
        pts = np.array(lidar.point_cloud).reshape(-1, 3)
        dists = np.linalg.norm(pts[:, :2], axis=1)
        min_dist = float(np.min(dists))
    
    coll = client.simGetCollisionInfo()
    print(f"  ({pos.x_val:5.1f},{pos.y_val:5.1f}) | LiDAR pts={len(lidar.point_cloud)//3:4d} | "
          f"min_obs={min_dist:5.1f}m | collision={coll.has_collided}")

client.landAsync().join()
print("\nDone!")
