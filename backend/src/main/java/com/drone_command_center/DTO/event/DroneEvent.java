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
public class DroneEvent implements Serializable {
    private String eventType;
    private UUID droneId;
    private String serialNumber;
    private String droneName;
    private String status;
    private String previousStatus;
    private Double batteryLevel;
    private Instant timestamp;
}
