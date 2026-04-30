"""
Simulated AirSim Feed — Sends fake telemetry to test the full pipeline
======================================================================
No AirSim needed. Simulates a drone navigating a simple path.

Usage:
    python simulate_airsim_feed.py

Pipeline tested:
    This script → Bridge → REST API → Backend → PostgreSQL DB
                                         ↓ WebSocket broadcast
                                      Frontend (Flutter)
"""

import time
import math
import logging
from command_center_bridge import CommandCenterBridge, BridgeConfig

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def main():
    print("=" * 60)
    print("Simulated AirSim Feed — Full Pipeline Test")
    print("=" * 60)

    config = BridgeConfig(
        base_url="http://localhost:8080/api",
        drone_id="auto",
        auth_username="navrl_bridge",
        auth_password="NavRL@2026!",
        telemetry_interval=1.0,
    )
    bridge = CommandCenterBridge(config)

    if not bridge.connect():
        print("✗ Cannot connect to backend. Is it running?")
        return

    drone_id = config.drone_id
    print(f"✓ Connected. Drone ID: {drone_id}")
    print(f"  Sending telemetry every 1 second...")
    print(f"  Simulating a circular flight path in NED coordinates")
    print(f"  Press Ctrl+C to stop\n")

    # Simulated flight params
    radius = 30.0        # Circle radius (meters)
    speed = 2.0          # m/s
    altitude_ned = -15.0  # -15 = 15m above ground in NED
    start_time = time.time()
    tick = 0
    total_sent = 0
    total_failed = 0

    # Goal position (center + offset)
    goal_x, goal_y = 50.0, 25.0

    try:
        while True:
            elapsed = time.time() - start_time
            angle = (speed / radius) * elapsed  # radians

            # Circular path
            ned_x = radius * math.cos(angle)
            ned_y = radius * math.sin(angle)
            ned_z = altitude_ned + 2.0 * math.sin(elapsed * 0.3)  # gentle altitude oscillation

            # Heading = tangent to circle
            heading_deg = math.degrees(angle + math.pi / 2) % 360

            # Velocity components
            vel_x = -speed * math.sin(angle)
            vel_y = speed * math.cos(angle)

            # Distance to goal
            dist_to_goal = math.sqrt((goal_x - ned_x)**2 + (goal_y - ned_y)**2)

            # Simulated battery drain
            battery = max(0.0, 100.0 - elapsed / 36.0)

            # Build telemetry
            telemetry = {
                'droneId': drone_id,
                'positionNedX': round(ned_x, 3),
                'positionNedY': round(ned_y, 3),
                'positionNedZ': round(ned_z, 3),
                'velocityX': round(vel_x, 4),
                'velocityY': round(vel_y, 4),
                'velocityZ': round(0.6 * math.cos(elapsed * 0.3), 4),
                'yaw': round(heading_deg, 2),
                'pitch': round(2.0 * math.sin(elapsed * 0.5), 2),
                'roll': round(5.0 * math.sin(elapsed * 0.7), 2),
                'batteryLevel': round(battery, 1),
                'altitude': round(-ned_z, 2),
                'obstacleDistance': round(3.0 + math.sin(elapsed * 0.2), 2),
                'altitudeMode': 'CRUISE',
                'stuckReplanCount': 0,
                'proactiveReplanCount': tick // 20,
                'navigationEfficiency': round(72.5 + 5 * math.sin(elapsed * 0.1), 1),
                'pathLength': round(speed * elapsed, 2),
                'optimalDistance': 55.0,
                'distanceToGoal': round(dist_to_goal, 2),
                'mappedObstacleCells': 142 + tick,
                'closestObstacleDistance': round(3.0 + math.sin(elapsed * 0.2), 2),
                'bestEffortActive': False,
                'collisionCount': 0,
                'currentPathWaypointCount': 5,
                'navrlSpeed': round(speed, 3),
                'heading': round(heading_deg, 2),
                'speed': round(speed, 3),
            }

            success = bridge.send_telemetry(telemetry)
            if success:
                total_sent += 1
            else:
                total_failed += 1

            # Print status
            lat = telemetry.get('latitude', 'N/A')
            lon = telemetry.get('longitude', 'N/A')
            print(f"  [{tick:4d}] NED({ned_x:7.2f}, {ned_y:7.2f}, {ned_z:6.2f}) "
                  f"GPS({lat}, {lon}) "
                  f"HDG={heading_deg:5.1f}° SPD={speed:.1f}m/s "
                  f"BAT={battery:4.1f}% "
                  f"{'✓' if success else '✗'} "
                  f"[sent:{total_sent} fail:{total_failed}]")

            tick += 1
            time.sleep(1.0)

    except KeyboardInterrupt:
        print(f"\n\nStopped after {tick} ticks ({total_sent} sent, {total_failed} failed)")
        bridge.disconnect()
        print("Disconnected.")


if __name__ == "__main__":
    main()
