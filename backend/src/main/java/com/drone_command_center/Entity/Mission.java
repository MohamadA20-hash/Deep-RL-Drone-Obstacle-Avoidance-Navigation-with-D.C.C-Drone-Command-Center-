package com.drone_command_center.Entity;

import com.drone_command_center.Entity.enums.MissionStatus;
import com.drone_command_center.Entity.enums.MissionType;
import jakarta.persistence.*;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.*;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Entity
@Table(name = "missions")
@Getter @Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Mission {

    @Id
    @GeneratedValue
    private UUID id;

    @NotBlank(message = "Mission name is required")
    @Size(min = 3, max = 100, message = "Name must be between 3 and 100 characters")
    @Column(nullable = false, length = 100)
    private String name;

    @Size(max = 500, message = "Description must be less than 500 characters")
    @Column(length = 500)
    private String description;

    @NotNull(message = "Mission type is required")
    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private MissionType missionType;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private MissionStatus status;

    private Instant createdAt;
    private Instant startedAt;
    private Instant completedAt;

    // Estimated duration in minutes
    private Integer estimatedDurationMinutes;

    // ─── NavRL navigation mission fields ───
    // Goal position in NED coordinates (meters) for NAVIGATION missions
    private Double goalNedX;
    private Double goalNedY;

    // Base altitude for the navigation (meters, positive = above ground)
    private Double baseAltitude;

    // NavRL planner configuration overrides (JSON)
    // e.g. {"grid_resolution": 2.0, "yaw_vel_min_scale": 0.5, ...}
    @Column(columnDefinition = "TEXT")
    private String plannerConfig;

    // Navigation result metrics
    private Double finalEfficiency;
    private Double totalPathLength;
    private Integer totalReplans;
    private Integer totalCollisions;

    // Who created this mission
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "created_by_user_id")
    private User createdBy;

    // Drone assigned to execute this mission
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "assigned_drone_id")
    private Drone assignedDrone;

    // Ordered list of waypoints for this mission
    @OneToMany(mappedBy = "mission", cascade = CascadeType.ALL, orphanRemoval = true, fetch = FetchType.LAZY)
    @OrderBy("sequenceOrder ASC")
    private List<Waypoint> waypoints;

    // Commands generated for this mission
    @OneToMany(mappedBy = "mission", cascade = CascadeType.ALL, fetch = FetchType.LAZY)
    private List<Command> commands;
}
