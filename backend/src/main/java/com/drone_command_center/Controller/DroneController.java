package com.drone_command_center.Controller;

import com.drone_command_center.DTO.request.DroneCreateRequest;
import com.drone_command_center.DTO.request.DroneUpdateRequest;
import com.drone_command_center.DTO.response.ApiResponse;
import com.drone_command_center.DTO.response.DroneDTO;
import com.drone_command_center.DTO.response.PagedResponse;
import com.drone_command_center.Entity.enums.ConnectionStatus;
import com.drone_command_center.Entity.enums.FlightStatus;
import com.drone_command_center.Service.DroneService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/drones")
@RequiredArgsConstructor
@Tag(name = "Drone Management", description = "APIs for managing drones")
@SecurityRequirement(name = "bearerAuth")
public class DroneController {

    private final DroneService droneService;

    @Operation(summary = "Register a new drone", description = "Register a new drone in the system")
    @ApiResponses(value = {
        @io.swagger.v3.oas.annotations.responses.ApiResponse(responseCode = "201", description = "Drone registered successfully"),
        @io.swagger.v3.oas.annotations.responses.ApiResponse(responseCode = "400", description = "Invalid input"),
        @io.swagger.v3.oas.annotations.responses.ApiResponse(responseCode = "409", description = "Drone with serial number already exists")
    })
    @PostMapping
    public ResponseEntity<ApiResponse<DroneDTO>> registerDrone(@Valid @RequestBody DroneCreateRequest request) {
        DroneDTO drone = droneService.registerDrone(request);
        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(ApiResponse.success("Drone registered successfully", drone));
    }

    @Operation(summary = "Get all drones", description = "Retrieve all drones with pagination")
    @GetMapping
    public ResponseEntity<ApiResponse<PagedResponse<DroneDTO>>> getAllDrones(
            @Parameter(description = "Page number (0-based)") @RequestParam(defaultValue = "0") int page,
            @Parameter(description = "Page size") @RequestParam(defaultValue = "10") int size,
            @Parameter(description = "Sort field") @RequestParam(defaultValue = "name") String sortBy,
            @Parameter(description = "Sort direction (asc/desc)") @RequestParam(defaultValue = "asc") String sortDir) {
        
        PagedResponse<DroneDTO> drones = droneService.getAllDrones(page, size, sortBy, sortDir);
        return ResponseEntity.ok(ApiResponse.success(drones));
    }

    @Operation(summary = "Get all drones (simple list)", description = "Retrieve all drones without pagination")
    @GetMapping("/all")
    public ResponseEntity<ApiResponse<List<DroneDTO>>> getAllDronesSimple() {
        List<DroneDTO> drones = droneService.getAllDronesSimple();
        return ResponseEntity.ok(ApiResponse.success(drones));
    }

    @Operation(summary = "Get drone by ID", description = "Retrieve a specific drone by its ID")
    @ApiResponses(value = {
        @io.swagger.v3.oas.annotations.responses.ApiResponse(responseCode = "200", description = "Drone found"),
        @io.swagger.v3.oas.annotations.responses.ApiResponse(responseCode = "404", description = "Drone not found")
    })
    @GetMapping("/{droneId}")
    public ResponseEntity<ApiResponse<DroneDTO>> getDroneById(
            @Parameter(description = "Drone ID") @PathVariable UUID droneId) {
        DroneDTO drone = droneService.getDroneById(droneId);
        return ResponseEntity.ok(ApiResponse.success(drone));
    }

    @Operation(summary = "Get drones by connection status")
    @GetMapping("/status/connection/{status}")
    public ResponseEntity<ApiResponse<List<DroneDTO>>> getDronesByConnectionStatus(
            @Parameter(description = "Connection status") @PathVariable ConnectionStatus status) {
        List<DroneDTO> drones = droneService.getDronesByConnectionStatus(status);
        return ResponseEntity.ok(ApiResponse.success(drones));
    }

    @Operation(summary = "Get drones by flight status")
    @GetMapping("/status/flight/{status}")
    public ResponseEntity<ApiResponse<List<DroneDTO>>> getDronesByFlightStatus(
            @Parameter(description = "Flight status") @PathVariable FlightStatus status) {
        List<DroneDTO> drones = droneService.getDronesByFlightStatus(status);
        return ResponseEntity.ok(ApiResponse.success(drones));
    }

    @Operation(summary = "Get drones with low battery")
    @GetMapping("/low-battery")
    public ResponseEntity<ApiResponse<List<DroneDTO>>> getDronesWithLowBattery(
            @Parameter(description = "Battery threshold percentage") @RequestParam(defaultValue = "20") double threshold) {
        List<DroneDTO> drones = droneService.getDronesWithLowBattery(threshold);
        return ResponseEntity.ok(ApiResponse.success(drones));
    }

    @Operation(summary = "Update drone", description = "Update drone information")
    @ApiResponses(value = {
        @io.swagger.v3.oas.annotations.responses.ApiResponse(responseCode = "200", description = "Drone updated successfully"),
        @io.swagger.v3.oas.annotations.responses.ApiResponse(responseCode = "404", description = "Drone not found")
    })
    @PutMapping("/{droneId}")
    public ResponseEntity<ApiResponse<DroneDTO>> updateDrone(
            @Parameter(description = "Drone ID") @PathVariable UUID droneId,
            @Valid @RequestBody DroneUpdateRequest request) {
        DroneDTO drone = droneService.updateDrone(droneId, request);
        return ResponseEntity.ok(ApiResponse.success("Drone updated successfully", drone));
    }

    @Operation(summary = "Delete drone", description = "Delete a drone from the system")
    @ApiResponses(value = {
        @io.swagger.v3.oas.annotations.responses.ApiResponse(responseCode = "200", description = "Drone deleted successfully"),
        @io.swagger.v3.oas.annotations.responses.ApiResponse(responseCode = "400", description = "Cannot delete drone in flight"),
        @io.swagger.v3.oas.annotations.responses.ApiResponse(responseCode = "404", description = "Drone not found")
    })
    @DeleteMapping("/{droneId}")
    public ResponseEntity<ApiResponse<Void>> deleteDrone(
            @Parameter(description = "Drone ID") @PathVariable UUID droneId) {
        droneService.deleteDrone(droneId);
        return ResponseEntity.ok(ApiResponse.success("Drone deleted successfully"));
    }

    @Operation(summary = "Update connection status")
    @PatchMapping("/{droneId}/connection-status")
    public ResponseEntity<ApiResponse<Void>> updateConnectionStatus(
            @Parameter(description = "Drone ID") @PathVariable UUID droneId,
            @Parameter(description = "New connection status") @RequestParam ConnectionStatus status) {
        droneService.updateConnectionStatus(droneId, status);
        return ResponseEntity.ok(ApiResponse.success("Connection status updated"));
    }

    @Operation(summary = "Update flight status")
    @PatchMapping("/{droneId}/flight-status")
    public ResponseEntity<ApiResponse<Void>> updateFlightStatus(
            @Parameter(description = "Drone ID") @PathVariable UUID droneId,
            @Parameter(description = "New flight status") @RequestParam FlightStatus status) {
        droneService.updateFlightStatus(droneId, status);
        return ResponseEntity.ok(ApiResponse.success("Flight status updated"));
    }

    @Operation(summary = "Check if drone is connected")
    @GetMapping("/{droneId}/is-connected")
    public ResponseEntity<ApiResponse<Boolean>> isDroneConnected(
            @Parameter(description = "Drone ID") @PathVariable UUID droneId) {
        boolean connected = droneService.isDroneConnected(droneId);
        return ResponseEntity.ok(ApiResponse.success(connected));
    }

    @Operation(summary = "Get drone count by connection status")
    @GetMapping("/count/connection/{status}")
    public ResponseEntity<ApiResponse<Long>> countByConnectionStatus(
            @Parameter(description = "Connection status") @PathVariable ConnectionStatus status) {
        long count = droneService.countByConnectionStatus(status);
        return ResponseEntity.ok(ApiResponse.success(count));
    }
}
