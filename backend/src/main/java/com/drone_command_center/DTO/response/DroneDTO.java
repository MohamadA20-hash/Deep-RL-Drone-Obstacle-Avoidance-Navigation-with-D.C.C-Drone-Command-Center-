package com.drone_command_center.DTO.response;

import com.drone_command_center.Entity.enums.AutonomyLevel;
import com.drone_command_center.Entity.enums.ConnectionStatus;
import com.drone_command_center.Entity.enums.FlightStatus;
import com.drone_command_center.Entity.enums.NavigationMode;
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
public class DroneDTO {
    
    private UUID id;
    private String serialNumber;
    private String name;
    private String modelType;
    private String firmwareVersion;
    private ConnectionStatus connectionStatus;
    private FlightStatus flightStatus;
    private double batteryLevel;
    private double latitude;
    private double longitude;
    private double altitude;
    private AutonomyLevel autonomyLevel;
    private NavigationMode navigationMode;
    private boolean failsafeEnabled;
    private boolean obstacleDetected;
    private Instant lastHeartbeat;
    private Instant registeredAt;
    private Double homeLatitude;
    private Double homeLongitude;
    private Double homeAltitude;

    // NavRL NED position
    private Double positionNedX;
    private Double positionNedY;
    private Double positionNedZ;

    // NavRL navigation state
    private Double goalNedX;
    private Double goalNedY;
    private Double navigationEfficiency;
    private Integer totalReplanCount;
    private Double distanceToGoal;
    private String altitudeMode;
}
