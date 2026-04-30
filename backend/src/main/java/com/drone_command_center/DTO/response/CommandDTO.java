package com.drone_command_center.DTO.response;

import com.drone_command_center.Entity.enums.CommandStatus;
import com.drone_command_center.Entity.enums.CommandType;
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
public class CommandDTO {
    
    private UUID id;
    private CommandType commandType;
    private String parameters;
    private CommandStatus status;
    private Instant createdAt;
    private Instant executedAt;
    private UUID issuedByUserId;
    private String issuedByUsername;
    private UUID droneId;
    private String droneName;
    private UUID missionId;
}
