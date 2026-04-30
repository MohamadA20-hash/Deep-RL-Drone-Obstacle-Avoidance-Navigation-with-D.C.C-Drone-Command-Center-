package com.drone_command_center.Entity;

import jakarta.persistence.*;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import lombok.*;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "telemetry", indexes = {
    @Index(name = "idx_telemetry_drone_timestamp", columnList = "drone_id, timestamp DESC")
})
@Getter @Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Telemetry {

    @Id
    @GeneratedValue
    private UUID id;

    @NotNull(message = "Timestamp is required")
    @Column(nullable = false)
    private Instant timestamp;

    @Min(value = -90, message = "Latitude must be between -90 and 90")
    @Max(value = 90, message = "Latitude must be between -90 and 90")
    private double latitude;

    @Min(value = -180, message = "Longitude must be between -180 and 180")
    @Max(value = 180, message = "Longitude must be between -180 and 180")
    private double longitude;

    @Min(value = 0, message = "Altitude must be at least 0")
    private double altitude;

    private double velocityX;
    private double velocityY;
    private double velocityZ;

    private double yaw;
    private double pitch;
    private double roll;

    @Min(value = 0, message = "Battery level must be at least 0")
    @Max(value = 100, message = "Battery level must be at most 100")
    private double batteryLevel;

    @Min(value = 0, message = "Obstacle distance must be at least 0")
    private double obstacleDistance;

    // ─── NavRL NED coordinate system (meters from origin) ───
    // x = North, y = East, z = Down (AirSim NED convention)
    private Double positionNedX;
    private Double positionNedY;
    private Double positionNedZ;

    // ─── NavRL planner telemetry fields ───
    // Altitude controller state: CRUISE, CLIMBING, HOLDING, DESCENDING
    private String altitudeMode;

    // Number of stuck replans triggered during navigation
    private Integer stuckReplanCount;

    // Number of proactive replans (periodic path refresh)
    private Integer proactiveReplanCount;

    // Navigation efficiency: optimalDistance / actualPathLength * 100
    private Double navigationEfficiency;

    // Total path length traveled (meters)
    private Double pathLength;

    // Straight-line distance to goal (meters)
    private Double optimalDistance;

    // Distance remaining to current goal (meters)
    private Double distanceToGoal;

    // Number of confirmed obstacle cells in occupancy grid
    private Integer mappedObstacleCells;

    // Closest obstacle distance from LiDAR (meters)
    private Double closestObstacleDistance;

    // Whether NavRL is operating in best-effort mode near goal
    private Boolean bestEffortActive;

    // Number of collisions detected
    private Integer collisionCount;

    // Current A* path waypoint count
    private Integer currentPathWaypointCount;

    // NavRL model speed (m/s, max 2.0)
    private Double navrlSpeed;

    @NotNull(message = "Drone is required")
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "drone_id", nullable = false)
    private Drone drone;
}

