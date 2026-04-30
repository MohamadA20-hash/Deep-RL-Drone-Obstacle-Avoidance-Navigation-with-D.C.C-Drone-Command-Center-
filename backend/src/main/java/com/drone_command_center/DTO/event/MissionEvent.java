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
public class MissionEvent implements Serializable {
    private String eventType;
    private UUID missionId;
    private String missionName;
    private String status;
    private UUID droneId;
    private UUID userId;
    private Instant timestamp;
}
