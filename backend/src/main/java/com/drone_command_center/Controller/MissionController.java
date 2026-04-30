package com.drone_command_center.Controller;

import com.drone_command_center.DTO.request.MissionCreateRequest;
import com.drone_command_center.DTO.request.WaypointCreateRequest;
import com.drone_command_center.DTO.response.ApiResponse;
import com.drone_command_center.DTO.response.MissionDTO;
import com.drone_command_center.DTO.response.PagedResponse;
import com.drone_command_center.Entity.User;
import com.drone_command_center.Entity.enums.MissionStatus;
import com.drone_command_center.Service.MissionService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/missions")
@RequiredArgsConstructor
@Tag(name = "Mission Management", description = "APIs for managing drone missions")
@SecurityRequirement(name = "bearerAuth")
public class MissionController {

    private final MissionService missionService;

    @Operation(summary = "Create a new mission", description = "Create a new mission with optional waypoints")
    @ApiResponses(value = {
        @io.swagger.v3.oas.annotations.responses.ApiResponse(responseCode = "201", description = "Mission created successfully"),
        @io.swagger.v3.oas.annotations.responses.ApiResponse(responseCode = "400", description = "Invalid input"),
        @io.swagger.v3.oas.annotations.responses.ApiResponse(responseCode = "404", description = "Drone not found")
    })
    @PostMapping
    public ResponseEntity<ApiResponse<MissionDTO>> createMission(
            @Valid @RequestBody MissionCreateRequest request,
            @AuthenticationPrincipal User user) {
        MissionDTO mission = missionService.createMission(request, user.getId());
        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(ApiResponse.success("Mission created successfully", mission));
    }

    @Operation(summary = "Get mission by ID")
    @GetMapping("/{missionId}")
    public ResponseEntity<ApiResponse<MissionDTO>> getMissionById(
            @Parameter(description = "Mission ID") @PathVariable UUID missionId) {
        MissionDTO mission = missionService.getMissionById(missionId);
        return ResponseEntity.ok(ApiResponse.success(mission));
    }

    @Operation(summary = "Get all missions", description = "Retrieve all missions with pagination")
    @GetMapping
    public ResponseEntity<ApiResponse<PagedResponse<MissionDTO>>> getAllMissions(
            @Parameter(description = "Page number (0-based)") @RequestParam(defaultValue = "0") int page,
            @Parameter(description = "Page size") @RequestParam(defaultValue = "10") int size,
            @Parameter(description = "Sort field") @RequestParam(defaultValue = "createdAt") String sortBy,
            @Parameter(description = "Sort direction") @RequestParam(defaultValue = "desc") String sortDir) {
        
        PagedResponse<MissionDTO> missions = missionService.getAllMissions(page, size, sortBy, sortDir);
        return ResponseEntity.ok(ApiResponse.success(missions));
    }

    @Operation(summary = "Get missions by status")
    @GetMapping("/status/{status}")
    public ResponseEntity<ApiResponse<List<MissionDTO>>> getMissionsByStatus(
            @Parameter(description = "Mission status") @PathVariable MissionStatus status) {
        List<MissionDTO> missions = missionService.getMissionsByStatus(status);
        return ResponseEntity.ok(ApiResponse.success(missions));
    }

    @Operation(summary = "Get missions by drone")
    @GetMapping("/drone/{droneId}")
    public ResponseEntity<ApiResponse<PagedResponse<MissionDTO>>> getMissionsByDrone(
            @Parameter(description = "Drone ID") @PathVariable UUID droneId,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "10") int size) {
        
        PagedResponse<MissionDTO> missions = missionService.getMissionsByDrone(droneId, page, size);
        return ResponseEntity.ok(ApiResponse.success(missions));
    }

    @Operation(summary = "Get my missions", description = "Get all missions created by the current user")
    @GetMapping("/my-missions")
    public ResponseEntity<ApiResponse<PagedResponse<MissionDTO>>> getMyMissions(
            @AuthenticationPrincipal User user,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "10") int size) {
        
        PagedResponse<MissionDTO> missions = missionService.getMissionsByUser(user.getId(), page, size);
        return ResponseEntity.ok(ApiResponse.success(missions));
    }

    @Operation(summary = "Assign drone to mission")
    @PatchMapping("/{missionId}/assign-drone/{droneId}")
    public ResponseEntity<ApiResponse<MissionDTO>> assignDroneToMission(
            @Parameter(description = "Mission ID") @PathVariable UUID missionId,
            @Parameter(description = "Drone ID") @PathVariable UUID droneId) {
        MissionDTO mission = missionService.assignDroneToMission(missionId, droneId);
        return ResponseEntity.ok(ApiResponse.success("Drone assigned to mission", mission));
    }

    @Operation(summary = "Start mission", description = "Start a created/planned mission")
    @PatchMapping("/{missionId}/start")
    public ResponseEntity<ApiResponse<MissionDTO>> startMission(
            @Parameter(description = "Mission ID") @PathVariable UUID missionId) {
        MissionDTO mission = missionService.startMission(missionId);
        return ResponseEntity.ok(ApiResponse.success("Mission started", mission));
    }

    @Operation(summary = "Pause mission", description = "Pause an active mission")
    @PatchMapping("/{missionId}/pause")
    public ResponseEntity<ApiResponse<MissionDTO>> pauseMission(
            @Parameter(description = "Mission ID") @PathVariable UUID missionId) {
        MissionDTO mission = missionService.pauseMission(missionId);
        return ResponseEntity.ok(ApiResponse.success("Mission paused", mission));
    }

    @Operation(summary = "Resume mission", description = "Resume a paused mission")
    @PatchMapping("/{missionId}/resume")
    public ResponseEntity<ApiResponse<MissionDTO>> resumeMission(
            @Parameter(description = "Mission ID") @PathVariable UUID missionId) {
        MissionDTO mission = missionService.resumeMission(missionId);
        return ResponseEntity.ok(ApiResponse.success("Mission resumed", mission));
    }

    @Operation(summary = "Complete mission", description = "Mark mission as completed")
    @PatchMapping("/{missionId}/complete")
    public ResponseEntity<ApiResponse<MissionDTO>> completeMission(
            @Parameter(description = "Mission ID") @PathVariable UUID missionId,
            @Parameter(description = "Whether mission was successful") @RequestParam(defaultValue = "true") boolean success) {
        MissionDTO mission = missionService.completeMission(missionId, success);
        String message = success ? "Mission completed successfully" : "Mission marked as failed";
        return ResponseEntity.ok(ApiResponse.success(message, mission));
    }

    @Operation(summary = "Abort mission", description = "Abort an active mission")
    @PatchMapping("/{missionId}/abort")
    public ResponseEntity<ApiResponse<MissionDTO>> abortMission(
            @Parameter(description = "Mission ID") @PathVariable UUID missionId) {
        MissionDTO mission = missionService.abortMission(missionId);
        return ResponseEntity.ok(ApiResponse.success("Mission aborted", mission));
    }

    @Operation(summary = "Add waypoint to mission")
    @PostMapping("/{missionId}/waypoints")
    public ResponseEntity<ApiResponse<MissionDTO>> addWaypoint(
            @Parameter(description = "Mission ID") @PathVariable UUID missionId,
            @Valid @RequestBody WaypointCreateRequest request) {
        MissionDTO mission = missionService.addWaypoint(missionId, request);
        return ResponseEntity.ok(ApiResponse.success("Waypoint added", mission));
    }

    @Operation(summary = "Remove waypoint from mission")
    @DeleteMapping("/{missionId}/waypoints/{waypointId}")
    public ResponseEntity<ApiResponse<MissionDTO>> removeWaypoint(
            @Parameter(description = "Mission ID") @PathVariable UUID missionId,
            @Parameter(description = "Waypoint ID") @PathVariable UUID waypointId) {
        MissionDTO mission = missionService.removeWaypoint(missionId, waypointId);
        return ResponseEntity.ok(ApiResponse.success("Waypoint removed", mission));
    }

    @Operation(summary = "Delete mission")
    @DeleteMapping("/{missionId}")
    public ResponseEntity<ApiResponse<Void>> deleteMission(
            @Parameter(description = "Mission ID") @PathVariable UUID missionId) {
        missionService.deleteMission(missionId);
        return ResponseEntity.ok(ApiResponse.success("Mission deleted successfully"));
    }

    @Operation(summary = "Get mission statistics")
    @GetMapping("/statistics")
    public ResponseEntity<ApiResponse<MissionService.MissionStatistics>> getMissionStatistics() {
        MissionService.MissionStatistics stats = missionService.getMissionStatistics();
        return ResponseEntity.ok(ApiResponse.success(stats));
    }
}

