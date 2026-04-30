package com.drone_command_center.DTO.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.UUID;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class TelemetryDTO {
    
    private UUID id;
    private Instant timestamp;
    private double latitude;
    private double longitude;
    private double altitude;
    private double velocityX;
    private double velocityY;
    private double velocityZ;
    private double yaw;
    private double pitch;
    private double roll;
    private double batteryLevel;
    private double obstacleDistance;
    private UUID droneId;
    private String droneName;

    // NavRL NED coordinates
    private Double positionNedX;
    private Double positionNedY;
    private Double positionNedZ;

    // NavRL planner telemetry
    private String altitudeMode;
    private Integer stuckReplanCount;
    private Integer proactiveReplanCount;
    private Double navigationEfficiency;
    private Double pathLength;
    private Double optimalDistance;
    private Double distanceToGoal;
    private Integer mappedObstacleCells;
    private Double closestObstacleDistance;
    private Boolean bestEffortActive;
    private Integer collisionCount;
    private Integer currentPathWaypointCount;
    private Double navrlSpeed;

    // LiDAR radar scan (transient — not stored in DB)
    private String lidarScan;
}
