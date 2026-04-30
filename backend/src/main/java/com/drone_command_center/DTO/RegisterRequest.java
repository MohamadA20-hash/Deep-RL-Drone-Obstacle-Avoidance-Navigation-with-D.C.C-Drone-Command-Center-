package com.drone_command_center.DTO;

import com.drone_command_center.validation.ValidPassword;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
@Schema(description = "User registration request")
public class RegisterRequest {

    @NotBlank(message = "Username is required")
    @Size(min = 3, max = 50, message = "Username must be between 3 and 50 characters")
    @Schema(description = "Unique username", example = "researcher")
    private String username;

    @NotBlank(message = "Password is required")
    @ValidPassword
    @Schema(description = "Password (min 8 chars, must include uppercase, lowercase, digit, special char)", example = "SecurePass@123")
    private String password;

    @NotBlank(message = "Email is required")
    @Email(message = "Email must be valid")
    @Schema(description = "Email address", example = "researcher@droneops.com")
    private String email;
}

