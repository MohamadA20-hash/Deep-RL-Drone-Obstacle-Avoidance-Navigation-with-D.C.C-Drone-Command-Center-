package com.drone_command_center.Controller;

import com.drone_command_center.DTO.request.CommandCreateRequest;
import com.drone_command_center.DTO.response.ApiResponse;
import com.drone_command_center.DTO.response.CommandDTO;
import com.drone_command_center.DTO.response.PagedResponse;
import com.drone_command_center.Entity.User;
import com.drone_command_center.Service.CommandService;
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
@RequestMapping("/api/commands")
@RequiredArgsConstructor
@Tag(name = "Command Management", description = "APIs for sending commands to drones")
@SecurityRequirement(name = "bearerAuth")
public class CommandController {

    private final CommandService commandService;

    @Operation(summary = "Send command to drone", description = "Send a command to a specific drone")
    @ApiResponses(value = {
        @io.swagger.v3.oas.annotations.responses.ApiResponse(responseCode = "201", description = "Command sent successfully"),
        @io.swagger.v3.oas.annotations.responses.ApiResponse(responseCode = "400", description = "Invalid command or drone state"),
        @io.swagger.v3.oas.annotations.responses.ApiResponse(responseCode = "404", description = "Drone not found"),
        @io.swagger.v3.oas.annotations.responses.ApiResponse(responseCode = "503", description = "Drone not connected")
    })
    @PostMapping
    public ResponseEntity<ApiResponse<CommandDTO>> sendCommand(
            @Valid @RequestBody CommandCreateRequest request,
            @AuthenticationPrincipal User user) {
        CommandDTO command = commandService.sendCommand(request, user.getId());
        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(ApiResponse.success("Command sent successfully", command));
    }

    @Operation(summary = "Get command by ID")
    @GetMapping("/{commandId}")
    public ResponseEntity<ApiResponse<CommandDTO>> getCommandById(
            @Parameter(description = "Command ID") @PathVariable UUID commandId) {
        CommandDTO command = commandService.getCommandById(commandId);
        return ResponseEntity.ok(ApiResponse.success(command));
    }

    @Operation(summary = "Get all commands", description = "Retrieve all commands with pagination")
    @GetMapping
    public ResponseEntity<ApiResponse<PagedResponse<CommandDTO>>> getAllCommands(
            @Parameter(description = "Page number (0-based)") @RequestParam(defaultValue = "0") int page,
            @Parameter(description = "Page size") @RequestParam(defaultValue = "20") int size,
            @Parameter(description = "Sort field") @RequestParam(defaultValue = "createdAt") String sortBy,
            @Parameter(description = "Sort direction") @RequestParam(defaultValue = "desc") String sortDir) {
        
        PagedResponse<CommandDTO> commands = commandService.getAllCommands(page, size, sortBy, sortDir);
        return ResponseEntity.ok(ApiResponse.success(commands));
    }

    @Operation(summary = "Get commands by drone", description = "Get all commands sent to a specific drone")
    @GetMapping("/drone/{droneId}")
    public ResponseEntity<ApiResponse<PagedResponse<CommandDTO>>> getCommandsByDrone(
            @Parameter(description = "Drone ID") @PathVariable UUID droneId,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        
        PagedResponse<CommandDTO> commands = commandService.getCommandsByDrone(droneId, page, size);
        return ResponseEntity.ok(ApiResponse.success(commands));
    }

    @Operation(summary = "Get pending commands for drone")
    @GetMapping("/drone/{droneId}/pending")
    public ResponseEntity<ApiResponse<List<CommandDTO>>> getPendingCommands(
            @Parameter(description = "Drone ID") @PathVariable UUID droneId) {
        List<CommandDTO> commands = commandService.getPendingCommands(droneId);
        return ResponseEntity.ok(ApiResponse.success(commands));
    }

    @Operation(summary = "Get commands by user", description = "Get all commands issued by a specific user")
    @GetMapping("/user/{userId}")
    public ResponseEntity<ApiResponse<PagedResponse<CommandDTO>>> getCommandsByUser(
            @Parameter(description = "User ID") @PathVariable UUID userId,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        
        PagedResponse<CommandDTO> commands = commandService.getCommandsByUser(userId, page, size);
        return ResponseEntity.ok(ApiResponse.success(commands));
    }

    @Operation(summary = "Get my commands", description = "Get all commands issued by the current user")
    @GetMapping("/my-commands")
    public ResponseEntity<ApiResponse<PagedResponse<CommandDTO>>> getMyCommands(
            @AuthenticationPrincipal User user,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        
        PagedResponse<CommandDTO> commands = commandService.getCommandsByUser(user.getId(), page, size);
        return ResponseEntity.ok(ApiResponse.success(commands));
    }

    @Operation(summary = "Mark command as sent", description = "Update command status to SENT")
    @PatchMapping("/{commandId}/sent")
    public ResponseEntity<ApiResponse<CommandDTO>> markCommandAsSent(
            @Parameter(description = "Command ID") @PathVariable UUID commandId) {
        CommandDTO command = commandService.markCommandAsSent(commandId);
        return ResponseEntity.ok(ApiResponse.success("Command marked as sent", command));
    }

    @Operation(summary = "Acknowledge command", description = "Mark command as acknowledged or failed")
    @PatchMapping("/{commandId}/acknowledge")
    public ResponseEntity<ApiResponse<CommandDTO>> acknowledgeCommand(
            @Parameter(description = "Command ID") @PathVariable UUID commandId,
            @Parameter(description = "Whether execution was successful") @RequestParam boolean success) {
        CommandDTO command = commandService.acknowledgeCommand(commandId, success);
        String message = success ? "Command acknowledged successfully" : "Command failed";
        return ResponseEntity.ok(ApiResponse.success(message, command));
    }

    @Operation(summary = "Cancel command", description = "Cancel a pending command")
    @DeleteMapping("/{commandId}")
    public ResponseEntity<ApiResponse<Void>> cancelCommand(
            @Parameter(description = "Command ID") @PathVariable UUID commandId) {
        commandService.cancelCommand(commandId);
        return ResponseEntity.ok(ApiResponse.success("Command cancelled successfully"));
    }

    @Operation(summary = "Get command statistics")
    @GetMapping("/statistics")
    public ResponseEntity<ApiResponse<CommandService.CommandStatistics>> getCommandStatistics() {
        CommandService.CommandStatistics stats = commandService.getCommandStatistics();
        return ResponseEntity.ok(ApiResponse.success(stats));
    }
}

