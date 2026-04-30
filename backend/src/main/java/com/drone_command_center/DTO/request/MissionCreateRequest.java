package com.drone_command_center.DTO.request;

import com.drone_command_center.Entity.enums.MissionType;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.UUID;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Request to create a new mission")
public class MissionCreateRequest {
    
    @NotBlank(message = "Mission name is required")
    @Size(min = 3, max = 100, message = "Name must be between 3 and 100 characters")
    @Schema(description = "Name of the mission", example = "Perimeter Survey Alpha")
    private String name;
    
    @Size(max = 500, message = "Description must be less than 500 characters")
    @Schema(description = "Description of the mission", example = "Survey the north perimeter of the facility")
    private String description;
    
    @NotNull(message = "Mission type is required")
    @Schema(description = "Type of mission", example = "SURVEILLANCE")
    private MissionType missionType;
    
    @Schema(description = "ID of the drone to assign to this mission")
    private UUID assignedDroneId;
    
    @Schema(description = "Estimated duration in minutes", example = "30")
    private Integer estimatedDurationMinutes;
    
    @Valid
    @Schema(description = "List of waypoints for this mission")
    private List<WaypointCreateRequest> waypoints;

    // ─── NavRL navigation fields ───
    @Schema(description = "Goal X position in NED meters (North)", example = "50.0")
    private Double goalNedX;

    @Schema(description = "Goal Y position in NED meters (East)", example = "25.0")
    private Double goalNedY;

    @Schema(description = "Base altitude for navigation (meters)", example = "10.0")
    private Double baseAltitude;

    @Schema(description = "NavRL planner config overrides (JSON)", 
            example = "{\"grid_resolution\": 2.0, \"yaw_vel_min_scale\": 0.5}")
    private String plannerConfig;

}
