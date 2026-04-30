package com.drone_command_center.Controller;

import com.drone_command_center.DTO.response.ApiResponse;
import com.drone_command_center.DTO.response.PagedResponse;
import com.drone_command_center.DTO.response.UserDTO;
import com.drone_command_center.Service.UserService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.UUID;

@RestController
@RequestMapping("/api/users")
@RequiredArgsConstructor
@Tag(name = "User Management", description = "APIs for managing users (Admin only)")
@SecurityRequirement(name = "bearerAuth")
public class UserController {

    private final UserService userService;

    @Operation(summary = "Get all users", description = "Get paginated list of all users")
    @GetMapping
    public ResponseEntity<ApiResponse<PagedResponse<UserDTO>>> getAllUsers(
            @Parameter(description = "Page number (0-based)") @RequestParam(defaultValue = "0") int page,
            @Parameter(description = "Page size") @RequestParam(defaultValue = "20") int size) {
        
        PagedResponse<UserDTO> users = userService.getAllUsers(page, size);
        return ResponseEntity.ok(ApiResponse.success(users));
    }

    @Operation(summary = "Get user by ID")
    @GetMapping("/{id}")
    public ResponseEntity<ApiResponse<UserDTO>> getUserById(
            @Parameter(description = "User ID") @PathVariable UUID id) {
        
        UserDTO user = userService.getUserById(id);
        return ResponseEntity.ok(ApiResponse.success(user));
    }

    @Operation(summary = "Get user by username")
    @GetMapping("/username/{username}")
    public ResponseEntity<ApiResponse<UserDTO>> getUserByUsername(
            @Parameter(description = "Username") @PathVariable String username) {
        
        UserDTO user = userService.getUserByUsername(username);
        return ResponseEntity.ok(ApiResponse.success(user));
    }

    @Operation(summary = "Update user profile")
    @ApiResponses(value = {
        @io.swagger.v3.oas.annotations.responses.ApiResponse(responseCode = "200", description = "User updated"),
        @io.swagger.v3.oas.annotations.responses.ApiResponse(responseCode = "404", description = "User not found"),
        @io.swagger.v3.oas.annotations.responses.ApiResponse(responseCode = "409", description = "Email already in use")
    })
    @PutMapping("/{id}")
    public ResponseEntity<ApiResponse<UserDTO>> updateUser(
            @Parameter(description = "User ID") @PathVariable UUID id,
            @Valid @RequestBody UpdateUserRequest request) {
        
        UserDTO user = userService.updateUser(id, request.email());
        return ResponseEntity.ok(ApiResponse.success("User updated", user));
    }

    @Operation(summary = "Enable user account")
    @PutMapping("/{id}/enable")
    public ResponseEntity<ApiResponse<UserDTO>> enableUser(
            @Parameter(description = "User ID") @PathVariable UUID id) {
        
        UserDTO user = userService.setUserEnabled(id, true);
        return ResponseEntity.ok(ApiResponse.success("User enabled", user));
    }

    @Operation(summary = "Disable user account")
    @PutMapping("/{id}/disable")
    public ResponseEntity<ApiResponse<UserDTO>> disableUser(
            @Parameter(description = "User ID") @PathVariable UUID id) {
        
        UserDTO user = userService.setUserEnabled(id, false);
        return ResponseEntity.ok(ApiResponse.success("User disabled", user));
    }

    @Operation(summary = "Change password", description = "User changes their own password")
    @PutMapping("/{id}/password")
    public ResponseEntity<ApiResponse<Void>> changePassword(
            @Parameter(description = "User ID") @PathVariable UUID id,
            @Valid @RequestBody ChangePasswordRequest request) {
        
        userService.changePassword(id, request.currentPassword(), request.newPassword());
        return ResponseEntity.ok(ApiResponse.success("Password changed"));
    }

    @Operation(summary = "Reset password", description = "Admin resets user password")
    @PutMapping("/{id}/reset-password")
    public ResponseEntity<ApiResponse<Void>> resetPassword(
            @Parameter(description = "User ID") @PathVariable UUID id,
            @Valid @RequestBody ResetPasswordRequest request) {
        
        userService.resetPassword(id, request.newPassword());
        return ResponseEntity.ok(ApiResponse.success("Password reset"));
    }

    @Operation(summary = "Delete user")
    @DeleteMapping("/{id}")
    public ResponseEntity<ApiResponse<Void>> deleteUser(
            @Parameter(description = "User ID") @PathVariable UUID id) {
        
        userService.deleteUser(id);
        return ResponseEntity.ok(ApiResponse.success("User deleted"));
    }

    // Inner record classes for request bodies
    public record UpdateUserRequest(
            @Email(message = "Invalid email format")
            String email
    ) {}

    public record ChangePasswordRequest(
            @NotBlank(message = "Current password is required")
            String currentPassword,
            
            @NotBlank(message = "New password is required")
            @Size(min = 6, message = "Password must be at least 6 characters")
            String newPassword
    ) {}

    public record ResetPasswordRequest(
            @NotBlank(message = "New password is required")
            @Size(min = 6, message = "Password must be at least 6 characters")
            String newPassword
    ) {}
}
