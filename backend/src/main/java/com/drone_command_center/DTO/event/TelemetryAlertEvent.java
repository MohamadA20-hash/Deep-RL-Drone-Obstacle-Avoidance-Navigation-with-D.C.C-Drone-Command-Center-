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
public class TelemetryAlertEvent implements Serializable {
    private String alertType;
    private UUID droneId;
    private String droneName;
    private String message;
    private Double value;
    private Instant timestamp;
}
