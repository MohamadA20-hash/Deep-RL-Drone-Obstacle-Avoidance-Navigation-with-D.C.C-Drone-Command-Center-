package com.drone_command_center.DTO.request;

import com.drone_command_center.Entity.enums.AutonomyLevel;
import com.drone_command_center.Entity.enums.NavigationMode;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Request to update drone information")
public class DroneUpdateRequest {
    
    @Size(min = 2, max = 100, message = "Name must be between 2 and 100 characters")
    @Schema(description = "Display name for the drone", example = "Alpha Scout Updated")
    private String name;
    
    @Schema(description = "Firmware version", example = "v2.6.0")
    private String firmwareVersion;
    
    @Schema(description = "Autonomy level", example = "FULLY_AUTONOMOUS")
    private AutonomyLevel autonomyLevel;
    
    @Schema(description = "Navigation mode", example = "GPS")
    private NavigationMode navigationMode;
    
    @Schema(description = "Enable failsafe mode", example = "true")
    private Boolean failsafeEnabled;
    
    @Schema(description = "Home latitude for return-to-home", example = "37.7749")
    private Double homeLatitude;
    
    @Schema(description = "Home longitude for return-to-home", example = "-122.4194")
    private Double homeLongitude;
    
    @Schema(description = "Home altitude for return-to-home", example = "10.0")
    private Double homeAltitude;
}
