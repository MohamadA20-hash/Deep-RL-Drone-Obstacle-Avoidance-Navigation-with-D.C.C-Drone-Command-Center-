package com.drone_command_center.DTO.event;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.io.Serializable;
import java.time.Instant;
import java.util.UUID;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CommandEvent implements Serializable {
    private String eventType;
    private UUID commandId;
    private String commandType;
    private String status;
    private UUID droneId;
    private UUID userId;
    private Instant timestamp;
}
