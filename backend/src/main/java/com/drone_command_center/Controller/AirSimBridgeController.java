package com.drone_command_center.Controller;

import com.drone_command_center.DTO.response.ApiResponse;
import com.drone_command_center.Service.AirSimBridgeManager;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * REST controller for managing the AirSim Python bridge process.
 * The bridge auto-connects to AirSim and streams telemetry to the backend.
 */
@RestController
@RequestMapping("/api/airsim-bridge")
@RequiredArgsConstructor
@Tag(name = "AirSim Bridge", description = "Manage the AirSim telemetry bridge process")
@SecurityRequirement(name = "bearerAuth")
public class AirSimBridgeController {

    private final AirSimBridgeManager bridgeManager;

    @GetMapping("/status")
    @Operation(summary = "Get bridge status",
               description = "Returns current status of the AirSim bridge process")
    public ResponseEntity<ApiResponse<Map<String, Object>>> getStatus() {
        return ResponseEntity.ok(ApiResponse.success(bridgeManager.getStatusMap()));
    }

    @PostMapping("/start")
    @Operation(summary = "Start bridge",
               description = "Start the AirSim bridge process (auto-detects AirSim)")
    public ResponseEntity<ApiResponse<Map<String, Object>>> start() {
        boolean started = bridgeManager.start();
        String msg = started ? "Bridge started" : "Failed to start bridge";
        return ResponseEntity.ok(started
                ? ApiResponse.success(msg, bridgeManager.getStatusMap())
                : ApiResponse.error(msg));
    }

    @PostMapping("/stop")
    @Operation(summary = "Stop bridge",
               description = "Stop the AirSim bridge process")
    public ResponseEntity<ApiResponse<Map<String, Object>>> stop() {
        bridgeManager.stop();
        return ResponseEntity.ok(ApiResponse.success("Bridge stopped", bridgeManager.getStatusMap()));
    }

    @PostMapping("/restart")
    @Operation(summary = "Restart bridge",
               description = "Stop and restart the AirSim bridge process")
    public ResponseEntity<ApiResponse<Map<String, Object>>> restart() {
        bridgeManager.restart();
        return ResponseEntity.ok(ApiResponse.success("Bridge restarted", bridgeManager.getStatusMap()));
    }
}
