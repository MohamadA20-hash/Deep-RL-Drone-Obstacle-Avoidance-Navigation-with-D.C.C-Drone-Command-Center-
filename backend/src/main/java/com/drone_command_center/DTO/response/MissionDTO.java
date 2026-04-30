package com.drone_command_center.DTO.response;

import com.drone_command_center.Entity.enums.MissionStatus;
import com.drone_command_center.Entity.enums.MissionType;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class MissionDTO {
    
    private UUID id;
    private String name;
    private String description;
    private MissionType missionType;
    private MissionStatus status;
    private Instant createdAt;
    private Instant startedAt;
    private Instant completedAt;
    private Integer estimatedDurationMinutes;
    private UUID createdByUserId;
    private String createdByUsername;
    private UUID assignedDroneId;
    private String assignedDroneName;
    private List<WaypointDTO> waypoints;

    // NavRL navigation fields
    private Double goalNedX;
    private Double goalNedY;
    private Double baseAltitude;
    private String plannerConfig;
    private Double finalEfficiency;
    private Double totalPathLength;
    private Integer totalReplans;
    private Integer totalCollisions;
}
