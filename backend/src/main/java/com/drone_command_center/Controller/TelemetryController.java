package com.drone_command_center.Controller;

import com.drone_command_center.DTO.request.TelemetryCreateRequest;
import com.drone_command_center.DTO.response.ApiResponse;
import com.drone_command_center.DTO.response.FlightPathPointDTO;
import com.drone_command_center.DTO.response.PagedResponse;
import com.drone_command_center.DTO.response.TelemetryDTO;
import com.drone_command_center.Service.TelemetryService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/telemetry")
@RequiredArgsConstructor
@Tag(name = "Telemetry", description = "APIs for drone telemetry data")
@SecurityRequirement(name = "bearerAuth")
public class TelemetryController {

    private final TelemetryService telemetryService;

    @Operation(summary = "Ingest telemetry data", description = "Record telemetry data from a drone")
    @ApiResponses(value = {
        @io.swagger.v3.oas.annotations.responses.ApiResponse(responseCode = "201", description = "Telemetry recorded"),
        @io.swagger.v3.oas.annotations.responses.ApiResponse(responseCode = "404", description = "Drone not found")
    })
    @PostMapping
    public ResponseEntity<ApiResponse<TelemetryDTO>> ingestTelemetry(
            @Valid @RequestBody TelemetryCreateRequest request) {
        TelemetryDTO telemetry = telemetryService.ingestTelemetry(request);
        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(ApiResponse.success("Telemetry recorded", telemetry));
    }

    @Operation(summary = "Get latest telemetry for drone")
    @GetMapping("/drone/{droneId}/latest")
    public ResponseEntity<ApiResponse<TelemetryDTO>> getLatestTelemetry(
            @Parameter(description = "Drone ID") @PathVariable UUID droneId) {
        TelemetryDTO telemetry = telemetryService.getLatestTelemetry(droneId);
        return ResponseEntity.ok(ApiResponse.success(telemetry));
    }

    @Operation(summary = "Get telemetry history", description = "Get telemetry history for a drone with pagination")
    @GetMapping("/drone/{droneId}")
    public ResponseEntity<ApiResponse<PagedResponse<TelemetryDTO>>> getTelemetryHistory(
            @Parameter(description = "Drone ID") @PathVariable UUID droneId,
            @Parameter(description = "Page number (0-based)") @RequestParam(defaultValue = "0") int page,
            @Parameter(description = "Page size") @RequestParam(defaultValue = "50") int size) {
        
        PagedResponse<TelemetryDTO> telemetry = telemetryService.getTelemetryHistory(droneId, page, size);
        return ResponseEntity.ok(ApiResponse.success(telemetry));
    }

    @Operation(summary = "Get telemetry in time range")
    @GetMapping("/drone/{droneId}/range")
    public ResponseEntity<ApiResponse<List<TelemetryDTO>>> getTelemetryInRange(
            @Parameter(description = "Drone ID") @PathVariable UUID droneId,
            @Parameter(description = "Start time (ISO 8601)") @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) Instant start,
            @Parameter(description = "End time (ISO 8601)") @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) Instant end) {
        
        List<TelemetryDTO> telemetry = telemetryService.getTelemetryInRange(droneId, start, end);
        return ResponseEntity.ok(ApiResponse.success(telemetry));
    }

    @Operation(summary = "Get recent telemetry", description = "Get telemetry since a specific time")
    @GetMapping("/drone/{droneId}/since")
    public ResponseEntity<ApiResponse<List<TelemetryDTO>>> getTelemetrySince(
            @Parameter(description = "Drone ID") @PathVariable UUID droneId,
            @Parameter(description = "Since time (ISO 8601)") @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) Instant since) {
        
        List<TelemetryDTO> telemetry = telemetryService.getTelemetrySince(droneId, since);
        return ResponseEntity.ok(ApiResponse.success(telemetry));
    }

    @Operation(summary = "Get last N telemetry records")
    @GetMapping("/drone/{droneId}/last/{count}")
    public ResponseEntity<ApiResponse<List<TelemetryDTO>>> getLatestTelemetryRecords(
            @Parameter(description = "Drone ID") @PathVariable UUID droneId,
            @Parameter(description = "Number of records") @PathVariable int count) {
        
        List<TelemetryDTO> telemetry = telemetryService.getLatestTelemetryRecords(droneId, count);
        return ResponseEntity.ok(ApiResponse.success(telemetry));
    }

    @Operation(summary = "Get telemetry count for drone")
    @GetMapping("/drone/{droneId}/count")
    public ResponseEntity<ApiResponse<Long>> getTelemetryCount(
            @Parameter(description = "Drone ID") @PathVariable UUID droneId) {
        long count = telemetryService.getTelemetryCount(droneId);
        return ResponseEntity.ok(ApiResponse.success(count));
    }

    @Operation(summary = "Get flight path", description = "Get flight path coordinates for a drone in a time range")
    @GetMapping("/drone/{droneId}/flight-path")
    public ResponseEntity<ApiResponse<List<FlightPathPointDTO>>> getFlightPath(
            @Parameter(description = "Drone ID") @PathVariable UUID droneId,
            @Parameter(description = "Start time (ISO 8601)") @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) Instant start,
            @Parameter(description = "End time (ISO 8601)") @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) Instant end) {
        
        List<FlightPathPointDTO> path = telemetryService.getFlightPath(droneId, start, end);
        return ResponseEntity.ok(ApiResponse.success(path));
    }

    @Operation(summary = "Delete old telemetry", description = "Delete telemetry data older than specified days")
    @DeleteMapping("/drone/{droneId}/cleanup")
    public ResponseEntity<ApiResponse<Void>> deleteOldTelemetry(
            @Parameter(description = "Drone ID") @PathVariable UUID droneId,
            @Parameter(description = "Days to keep") @RequestParam(defaultValue = "30") int daysToKeep) {
        
        telemetryService.deleteOldTelemetry(droneId, daysToKeep);
        return ResponseEntity.ok(ApiResponse.success("Old telemetry deleted"));
    }
}

