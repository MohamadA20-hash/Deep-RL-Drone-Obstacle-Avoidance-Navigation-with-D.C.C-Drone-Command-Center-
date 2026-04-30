package com.drone_command_center.Entity;

import com.drone_command_center.Entity.enums.AutonomyLevel;
import com.drone_command_center.Entity.enums.ConnectionStatus;
import com.drone_command_center.Entity.enums.FlightStatus;
import com.drone_command_center.Entity.enums.NavigationMode;
import jakarta.persistence.*;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.*;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Entity
@Table(name = "drones")
@Getter @Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Drone {

    @Id
    @GeneratedValue
    private UUID id;

    @NotBlank(message = "Serial number is required")
    @Size(min = 5, max = 50, message = "Serial number must be between 5 and 50 characters")
    @Column(unique = true, nullable = false, length = 50)
    private String serialNumber;

    @NotBlank(message = "Name is required")
    @Size(min = 2, max = 100, message = "Name must be between 2 and 100 characters")
    @Column(nullable = false, length = 100)
    private String name;

    @NotBlank(message = "Model type is required")
    @Column(nullable = false, length = 100)
    private String modelType;

    @Column(length = 50)
    private String firmwareVersion;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private ConnectionStatus connectionStatus;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private FlightStatus flightStatus;

    @Min(value = 0, message = "Battery level must be at least 0")
    @Max(value = 100, message = "Battery level must be at most 100")
    private double batteryLevel;

    @Min(value = -90, message = "Latitude must be between -90 and 90")
    @Max(value = 90, message = "Latitude must be between -90 and 90")
    private double latitude;

    @Min(value = -180, message = "Longitude must be between -180 and 180")
    @Max(value = 180, message = "Longitude must be between -180 and 180")
    private double longitude;

    @Min(value = 0, message = "Altitude must be at least 0")
    private double altitude;

    @Enumerated(EnumType.STRING)
    private AutonomyLevel autonomyLevel;

    @Enumerated(EnumType.STRING)
    private NavigationMode navigationMode;

    private boolean failsafeEnabled;
    private boolean obstacleDetected;

    private Instant lastHeartbeat;
    private Instant registeredAt;

    // Home position for return-to-home functionality
    private Double homeLatitude;
    private Double homeLongitude;
    private Double homeAltitude;

    // ─── NavRL NED coordinate system (meters from origin) ───
    // These are the drone's position in AirSim NED frame
    // x = North, y = East, z = Down
    private Double positionNedX;
    private Double positionNedY;
    private Double positionNedZ;

    // NavRL goal position (NED meters)
    private Double goalNedX;
    private Double goalNedY;

    // NavRL navigation state
    private Double navigationEfficiency;
    private Integer totalReplanCount;
    private Double distanceToGoal;
    private String altitudeMode;  // CRUISE, CLIMBING, HOLDING, DESCENDING

    // Relationships
    @OneToMany(mappedBy = "drone", cascade = CascadeType.ALL, fetch = FetchType.LAZY)
    private List<Telemetry> telemetryLogs;

    @OneToMany(mappedBy = "drone", cascade = CascadeType.ALL, fetch = FetchType.LAZY)
    private List<Command> commands;

    @OneToMany(mappedBy = "drone", cascade = CascadeType.ALL, fetch = FetchType.LAZY)
    private List<Sensor> sensors;

    @OneToMany(mappedBy = "assignedDrone", cascade = CascadeType.ALL, fetch = FetchType.LAZY)
    private List<Mission> missions;
}
