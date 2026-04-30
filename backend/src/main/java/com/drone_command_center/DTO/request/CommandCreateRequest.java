package com.drone_command_center.DTO.request;

import com.drone_command_center.Entity.enums.CommandType;
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
@Schema(description = "Request to send a command to a drone")
public class CommandCreateRequest {
    
    @NotNull(message = "Drone ID is required")
    @Schema(description = "ID of the drone to send the command to")
    private UUID droneId;
    
    @NotNull(message = "Command type is required")
    @Schema(description = "Type of command to execute", example = "TAKEOFF")
    private CommandType commandType;
    
    @Schema(description = "JSON parameters for the command", example = "{\"altitude\": 50, \"speed\": 5}")
    private String parameters;
}
