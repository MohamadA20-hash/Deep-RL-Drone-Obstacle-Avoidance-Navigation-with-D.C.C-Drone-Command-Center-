package com.drone_command_center.Controller;

import com.drone_command_center.DTO.response.ApiResponse;
import com.drone_command_center.DTO.response.SensorReadingDTO;
import com.drone_command_center.Service.SensorService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/drones/{droneId}/sensors")
@RequiredArgsConstructor
@Tag(name = "Drone Sensors", description = "Per-drone sensor suite with live readings")
@SecurityRequirement(name = "bearerAuth")
public class SensorController {

    private final SensorService sensorService;

    @Operation(summary = "List sensors for a drone with their latest live readings",
            description = "Each reading is derived from the drone's most recent telemetry row.")
    @GetMapping
    public ResponseEntity<ApiResponse<List<SensorReadingDTO>>> getSensors(
            @Parameter(description = "Drone ID") @PathVariable UUID droneId) {
        List<SensorReadingDTO> sensors = sensorService.getSensorsForDrone(droneId);
        return ResponseEntity.ok(ApiResponse.success(sensors));
    }
}
