package com.drone_command_center.DTO.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class FlightPathPointDTO {
    private Instant timestamp;
    private double latitude;
    private double longitude;
    private double altitude;
}
