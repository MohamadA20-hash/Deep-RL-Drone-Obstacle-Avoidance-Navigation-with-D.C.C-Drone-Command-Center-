package com.drone_command_center.DTO.request;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.UUID;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Request to record telemetry data from a drone")
public class TelemetryCreateRequest {
    
    @NotNull(message = "Drone ID is required")
    @Schema(description = "ID of the drone sending telemetry")
    private UUID droneId;
    
    @Schema(description = "Latitude coordinate", example = "37.7749")
    private double latitude;
    
    @Schema(description = "Longitude coordinate", example = "-122.4194")
    private double longitude;
    
    @Schema(description = "Altitude in meters", example = "50.0")
    private double altitude;
    
    @Schema(description = "Velocity in X direction (m/s)", example = "2.5")
    private double velocityX;
    
    @Schema(description = "Velocity in Y direction (m/s)", example = "1.0")
    private double velocityY;
    
    @Schema(description = "Velocity in Z direction (m/s)", example = "0.5")
    private double velocityZ;
    
    @Schema(description = "Yaw angle (degrees)", example = "90.0")
    private double yaw;
    
    @Schema(description = "Pitch angle (degrees)", example = "5.0")
    private double pitch;
    
    @Schema(description = "Roll angle (degrees)", example = "2.0")
    private double roll;
    
    @Schema(description = "Battery level percentage", example = "85.5")
    private double batteryLevel;
    
    @Schema(description = "Distance to nearest obstacle (meters)", example = "10.0")
    private double obstacleDistance;

    // ─── NavRL NED coordinate system ───
    @Schema(description = "NED X position - North (meters from origin)", example = "15.5")
    private Double positionNedX;

    @Schema(description = "NED Y position - East (meters from origin)", example = "-8.3")
    private Double positionNedY;

    @Schema(description = "NED Z position - Down (meters, negative = above ground)", example = "-10.0")
    private Double positionNedZ;

    // ─── NavRL planner telemetry ───
    @Schema(description = "Altitude controller mode: CRUISE, CLIMBING, HOLDING, DESCENDING")
    private String altitudeMode;

    @Schema(description = "Number of stuck replans during navigation", example = "2")
    private Integer stuckReplanCount;

    @Schema(description = "Number of proactive replans", example = "11")
    private Integer proactiveReplanCount;

    @Schema(description = "Navigation efficiency percentage", example = "70.7")
    private Double navigationEfficiency;

    @Schema(description = "Total path length traveled (meters)", example = "42.5")
    private Double pathLength;

    @Schema(description = "Straight-line distance to goal (meters)", example = "30.0")
    private Double optimalDistance;

    @Schema(description = "Current distance to goal (meters)", example = "5.2")
    private Double distanceToGoal;

    @Schema(description = "Number of confirmed obstacle cells in occupancy grid", example = "145")
    private Integer mappedObstacleCells;

    @Schema(description = "Closest obstacle from LiDAR (meters)", example = "3.1")
    private Double closestObstacleDistance;

    @Schema(description = "Whether NavRL is in best-effort mode near goal", example = "false")
    private Boolean bestEffortActive;

    @Schema(description = "Number of collisions detected", example = "0")
    private Integer collisionCount;

    @Schema(description = "A* path waypoint count", example = "8")
    private Integer currentPathWaypointCount;

    @Schema(description = "NavRL model speed (m/s, max 2.0)", example = "1.8")
    private Double navrlSpeed;

    @Schema(description = "LiDAR radar scan — JSON array of 36 sector distances (metres)")
    private String lidarScan;
}
