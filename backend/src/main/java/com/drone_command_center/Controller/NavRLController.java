package com.drone_command_center.Controller;

import com.drone_command_center.DTO.response.CommandDTO;
import com.drone_command_center.Entity.User;
import com.drone_command_center.Service.NavRLBridgeService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.Map;
import java.util.UUID;

/**
 * REST controller for NavRL autonomous navigation operations.
 * 
 * All coordinates use AirSim NED (North-East-Down) in meters:
 *   goalX = North position (meters from origin)
 *   goalY = East position (meters from origin)
 * 
 * The NavRL planner uses PPO+CNN for local obstacle avoidance and
 * A* for global path planning. Max velocity: 2.0 m/s.
 */
@RestController
@RequestMapping("/api/navrl")
@RequiredArgsConstructor
@Tag(name = "NavRL Navigation", description = "Autonomous navigation using the NavRL RL-based planner")
@SecurityRequirement(name = "bearerAuth")
public class NavRLController {

    private final NavRLBridgeService navRLBridgeService;

    @PostMapping("/drones/{droneId}/goal")
    @Operation(summary = "Set navigation goal",
               description = "Set a goal position in NED meters for the NavRL planner")
    public ResponseEntity<CommandDTO> setGoal(
            @PathVariable UUID droneId,
            @RequestBody GoalRequest request,
            @AuthenticationPrincipal User user) {
        CommandDTO command = navRLBridgeService.setNavigationGoal(
                droneId, request.getGoalX(), request.getGoalY(), user.getId());
        return ResponseEntity.ok(command);
    }

    @PostMapping("/drones/{droneId}/start")
    @Operation(summary = "Start autonomous navigation",
               description = "Start NavRL autonomous navigation to a goal with optional planner config")
    public ResponseEntity<CommandDTO> startNavigation(
            @PathVariable UUID droneId,
            @RequestBody StartNavigationRequest request,
            @AuthenticationPrincipal User user) {
        CommandDTO command = navRLBridgeService.startAutonomousNavigation(
                droneId,
                request.getGoalX(),
                request.getGoalY(),
                request.getBaseAltitude() != null ? request.getBaseAltitude() : 10.0,
                request.getPlannerConfig(),
                user.getId());
        return ResponseEntity.ok(command);
    }

    @PostMapping("/drones/{droneId}/stop")
    @Operation(summary = "Stop autonomous navigation",
               description = "Stop NavRL navigation and switch drone to manual/hover")
    public ResponseEntity<CommandDTO> stopNavigation(
            @PathVariable UUID droneId,
            @AuthenticationPrincipal User user) {
        CommandDTO command = navRLBridgeService.stopNavigation(droneId, user.getId());
        return ResponseEntity.ok(command);
    }

    @PostMapping("/drones/{droneId}/emergency-land")
    @Operation(summary = "Emergency land",
               description = "Stop navigation and land the drone immediately")
    public ResponseEntity<CommandDTO> emergencyLand(
            @PathVariable UUID droneId,
            @AuthenticationPrincipal User user) {
        CommandDTO command = navRLBridgeService.emergencyLand(droneId, user.getId());
        return ResponseEntity.ok(command);
    }

    @PostMapping("/drones/{droneId}/pause")
    @Operation(summary = "Pause navigation",
               description = "Pause NavRL navigation — drone will hover in place")
    public ResponseEntity<CommandDTO> pauseNavigation(
            @PathVariable UUID droneId,
            @AuthenticationPrincipal User user) {
        CommandDTO command = navRLBridgeService.pauseNavigation(droneId, user.getId());
        return ResponseEntity.ok(command);
    }

    @PostMapping("/drones/{droneId}/resume")
    @Operation(summary = "Resume navigation",
               description = "Resume a previously paused NavRL navigation")
    public ResponseEntity<CommandDTO> resumeNavigation(
            @PathVariable UUID droneId,
            @AuthenticationPrincipal User user) {
        CommandDTO command = navRLBridgeService.resumeNavigation(droneId, user.getId());
        return ResponseEntity.ok(command);
    }

    @PostMapping("/drones/{droneId}/replan")
    @Operation(summary = "Force path replan",
               description = "Force the NavRL A* planner to recompute the global path")
    public ResponseEntity<CommandDTO> forceReplan(
            @PathVariable UUID droneId,
            @AuthenticationPrincipal User user) {
        CommandDTO command = navRLBridgeService.forceReplan(droneId, user.getId());
        return ResponseEntity.ok(command);
    }

    @PutMapping("/drones/{droneId}/config")
    @Operation(summary = "Update planner configuration",
               description = "Update NavRL planner parameters on a running navigation session")
    public ResponseEntity<CommandDTO> updateConfig(
            @PathVariable UUID droneId,
            @RequestBody Map<String, Object> configOverrides,
            @AuthenticationPrincipal User user) {
        CommandDTO command = navRLBridgeService.updatePlannerConfig(
                droneId, configOverrides, user.getId());
        return ResponseEntity.ok(command);
    }

    @GetMapping("/drones/{droneId}/status")
    @Operation(summary = "Get navigation status",
               description = "Get current NavRL navigation status including position, goal, efficiency")
    public ResponseEntity<NavRLBridgeService.NavRLStatus> getStatus(@PathVariable UUID droneId) {
        NavRLBridgeService.NavRLStatus status = navRLBridgeService.getNavigationStatus(droneId);
        return ResponseEntity.ok(status);
    }

    @PostMapping("/drones/{droneId}/nav-complete")
    @Operation(summary = "Report navigation completion",
               description = "Called by the auto-bridge when NavRL navigation finishes")
    public ResponseEntity<Map<String, Object>> navComplete(
            @PathVariable UUID droneId,
            @RequestBody NavCompleteRequest request) {
        navRLBridgeService.completeNavigation(droneId, request.isSuccess(), request.getMetrics());
        return ResponseEntity.ok(Map.of("status", "ok"));
    }

    @GetMapping("/config/defaults")
    @Operation(summary = "Get default planner config",
               description = "Get the default NavRL planner configuration parameters")
    public ResponseEntity<Map<String, Object>> getDefaultConfig() {
        return ResponseEntity.ok(navRLBridgeService.getDefaultPlannerConfig());
    }

    // ─── Request DTOs ───

    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    public static class GoalRequest {
        /** Goal X position — North (NED meters) */
        private double goalX;
        /** Goal Y position — East (NED meters) */
        private double goalY;
    }

    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    public static class StartNavigationRequest {
        /** Goal X position — North (NED meters). Null = use existing goal. */
        private Double goalX;
        /** Goal Y position — East (NED meters). Null = use existing goal. */
        private Double goalY;
        /** Base flight altitude in meters (default: 10.0) */
        private Double baseAltitude;
        /** Optional planner config overrides */
        private Map<String, Object> plannerConfig;
    }

    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    public static class NavCompleteRequest {
        /** Whether navigation reached the goal successfully */
        private boolean success;
        /** Navigation result metrics (time, efficiency, replans, etc.) */
        private Map<String, Object> metrics;
    }
}
