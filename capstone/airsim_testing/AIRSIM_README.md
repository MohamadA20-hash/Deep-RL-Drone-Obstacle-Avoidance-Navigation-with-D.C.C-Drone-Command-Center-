# AirSim Integration for NavRL

This guide explains how to test the NavRL pretrained model in Microsoft AirSim.

## Prerequisites

1. **AirSim Installed**: Download from [AirSim Releases](https://github.com/microsoft/AirSim/releases)
   - For quick testing, use pre-built binaries like `AirSimNH` (Neighborhood environment)
   
2. **Python Environment**: Same environment used for NavRL quick-demos

## Installation

```bash
# Navigate to quick-demos folder
cd quick-demos

# Install AirSim Python package
pip install airsim msgpack-rpc-python
```

## AirSim Configuration

Before running, configure AirSim with proper drone and LiDAR settings.

### Step 1: Create/Edit settings.json

Location: `C:\Users\<YourUsername>\Documents\AirSim\settings.json`

```json
{
    "SeeDocsAt": "https://microsoft.github.io/AirSim/settings/",
    "SettingsVersion": 1.2,
    "SimMode": "Multirotor",
    "ClockSpeed": 1.0,
    "Vehicles": {
        "Drone1": {
            "VehicleType": "SimpleFlight",
            "X": 0, "Y": 0, "Z": -2,
            "Sensors": {
                "LidarSensor1": {
                    "SensorType": 6,
                    "Enabled": true,
                    "NumberOfChannels": 4,
                    "RotationsPerSecond": 10,
                    "PointsPerSecond": 10000,
                    "X": 0, "Y": 0, "Z": -0.5,
                    "Roll": 0, "Pitch": 0, "Yaw": 0,
                    "VerticalFOVUpper": 20,
                    "VerticalFOVLower": -10,
                    "HorizontalFOVStart": 0,
                    "HorizontalFOVEnd": 360,
                    "DrawDebugPoints": true,
                    "DataFrame": "SensorLocalFrame"
                }
            }
        }
    }
}
```

### Step 2: Launch AirSim

1. Run `AirSimNH.exe` (or your preferred AirSim environment)
2. Wait for the simulation to fully load
3. You should see a drone spawned in the scene

## Running the Navigation

```bash
# Basic usage (default goal at x=50, y=50)
python airsim-navigation.py

# Custom goal position
python airsim-navigation.py --goal-x 30 --goal-y 40

# Adjust flight height
python airsim-navigation.py --goal-x 50 --goal-y 50 --height 5
```

## Expected Behavior

1. The drone will take off and hover at the specified height
2. The NavRL policy will control the drone toward the goal
3. Progress will be printed every 10 steps
4. When the goal is reached (within 2 meters), the drone will land

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Connection refused" | Make sure AirSim is running before the script |
| Drone doesn't move | Check if API control is enabled in AirSim (press `B` key) |
| Poor obstacle avoidance | Verify LiDAR is configured in settings.json |
| Drone flies erratically | Reduce `MAX_VELOCITY` in the script (default: 2.0 m/s) |

## Limitations

- **No depth camera support**: The script uses LiDAR only. If you prefer camera-based navigation, you'll need to modify `process_lidar()` to use depth images.
- **2D navigation**: The policy outputs XY velocity only; height is maintained automatically.
- **Single robot**: Multi-robot scenarios require additional detection logic.

## Extending for Multiple Drones

To test multi-robot navigation, add more vehicles in `settings.json`:

```json
"Vehicles": {
    "Drone1": { ... },
    "Drone2": {
        "VehicleType": "SimpleFlight",
        "X": 10, "Y": 0, "Z": -2,
        ...
    }
}
```

Then modify the `get_dynamic_obstacles()` method to query other drone positions using `client.getMultirotorState(vehicle_name="Drone2")`.
