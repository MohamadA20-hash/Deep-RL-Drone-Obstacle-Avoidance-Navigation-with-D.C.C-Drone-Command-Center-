package com.drone_command_center.DTO.request;

import com.drone_command_center.Entity.enums.AutonomyLevel;
import com.drone_command_center.Entity.enums.NavigationMode;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Request to register a new drone")
public class DroneCreateRequest {
    
    @NotBlank(message = "Serial number is required")
    @Size(min = 5, max = 50, message = "Serial number must be between 5 and 50 characters")
    @Schema(description = "Unique serial number of the drone", example = "DJI-M300-001")
    private String serialNumber;
    
    @NotBlank(message = "Name is required")
    @Size(min = 2, max = 100, message = "Name must be between 2 and 100 characters")
    @Schema(description = "Display name for the drone", example = "Alpha Scout")
    private String name;
    
    @NotBlank(message = "Model type is required")
    @Schema(description = "Model type of the drone", example = "DJI Matrice 300 RTK")
    private String modelType;
    
    @Schema(description = "Firmware version", example = "v2.5.1")
    private String firmwareVersion;
    
    @Schema(description = "Autonomy level", example = "MANUAL")
    private AutonomyLevel autonomyLevel;
    
    @Schema(description = "Navigation mode", example = "MANUAL")
    private NavigationMode navigationMode;
    
    @Schema(description = "Enable failsafe mode", example = "true")
    private Boolean failsafeEnabled = true;
    
    @Schema(description = "Home latitude for return-to-home", example = "37.7749")
    private Double homeLatitude;
    
    @Schema(description = "Home longitude for return-to-home", example = "-122.4194")
    private Double homeLongitude;
    
    @Schema(description = "Home altitude for return-to-home", example = "10.0")
    private Double homeAltitude;
}
