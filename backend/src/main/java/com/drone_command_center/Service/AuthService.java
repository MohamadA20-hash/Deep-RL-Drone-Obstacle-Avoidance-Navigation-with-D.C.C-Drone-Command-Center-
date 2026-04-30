package com.drone_command_center.Service;

import com.drone_command_center.DTO.LoginRequest;
import com.drone_command_center.DTO.RegisterRequest;
import com.drone_command_center.DTO.response.AuthResponse;
import com.drone_command_center.DTO.response.UserDTO;
import com.drone_command_center.Entity.RefreshToken;
import com.drone_command_center.Entity.User;
import com.drone_command_center.config.RateLimiter;
import com.drone_command_center.exception.DuplicateResourceException;
import com.drone_command_center.exception.InvalidOperationException;
import com.drone_command_center.exception.ResourceNotFoundException;
import com.drone_command_center.exception.UnauthorizedException;
import com.drone_command_center.Repository.UserRepository;
import com.drone_command_center.Security.JwtUtil;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Slf4j
@Service
@RequiredArgsConstructor
public class AuthService {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtUtil jwtUtil;
    private final RateLimiter rateLimiter;
    private final RefreshTokenService refreshTokenService;

    @Transactional
    public UserDTO register(RegisterRequest request) {
        log.info("Registration attempt for username: {}", request.getUsername());

        if (userRepository.findByUsername(request.getUsername()).isPresent()) {
            throw new DuplicateResourceException("Username already exists");
        }

        if (userRepository.findByEmail(request.getEmail()).isPresent()) {
            throw new DuplicateResourceException("Email already exists");
        }

        User user = User.builder()
                .username(request.getUsername())
                .password(passwordEncoder.encode(request.getPassword()))
                .email(request.getEmail())
                .enabled(true)
                .build();

        User savedUser = userRepository.save(user);
        log.info("User registered successfully: {}", savedUser.getUsername());
        return mapToDTO(savedUser);
    }

    public AuthResponse login(LoginRequest request, String clientIp) {
        if (!rateLimiter.tryConsume(clientIp)) {
            log.warn("Rate limit exceeded for IP: {}", clientIp);
            throw new InvalidOperationException("Too many requests. Please try again later.");
        }

        if (rateLimiter.isLockedOut(request.getUsername())) {
            long remainingMinutes = rateLimiter.getRemainingLockoutMinutes(request.getUsername());
            log.warn("Login attempt for locked out user: {}", request.getUsername());
            throw new InvalidOperationException(
                    String.format("Account temporarily locked. Please try again in %d minutes.", remainingMinutes));
        }

        User user = userRepository.findByUsername(request.getUsername())
                .orElseThrow(() -> {
                    rateLimiter.recordFailedLogin(request.getUsername());
                    return new ResourceNotFoundException("User not found");
                });

        if (!user.isEnabled()) {
            throw new UnauthorizedException("User account is disabled");
        }

        if (!passwordEncoder.matches(request.getPassword(), user.getPassword())) {
            rateLimiter.recordFailedLogin(request.getUsername());
            int remaining = rateLimiter.getRemainingAttempts(request.getUsername());
            log.warn("Invalid password for user: {}. Remaining attempts: {}", request.getUsername(), remaining);
            throw new UnauthorizedException(
                    String.format("Invalid credentials. %d attempts remaining before lockout.", remaining));
        }

        rateLimiter.clearFailedAttempts(request.getUsername());

        String accessToken = jwtUtil.generateToken(user.getUsername());
        RefreshToken refreshToken = refreshTokenService.createRefreshToken(user);

        log.info("Login successful for user: {}", user.getUsername());

        return AuthResponse.builder()
                .token(accessToken)
                .refreshToken(refreshToken.getToken())
                .tokenType("Bearer")
                .username(user.getUsername())
                .email(user.getEmail())
                .userId(user.getId())
                .expiresIn(jwtUtil.getExpirationMs())
                .build();
    }

    @Transactional(readOnly = true)
    public AuthResponse refreshToken(String refreshTokenValue) {
        RefreshToken refreshToken = refreshTokenService.validateRefreshToken(refreshTokenValue);
        User user = refreshToken.getUser();

        String newAccessToken = jwtUtil.generateToken(user.getUsername());
        log.info("Token refreshed for user: {}", user.getUsername());

        return AuthResponse.builder()
                .token(newAccessToken)
                .refreshToken(refreshToken.getToken())
                .tokenType("Bearer")
                .username(user.getUsername())
                .email(user.getEmail())
                .userId(user.getId())
                .expiresIn(jwtUtil.getExpirationMs())
                .build();
    }

    public void logout(String refreshTokenValue) {
        refreshTokenService.revokeToken(refreshTokenValue);
        log.info("User logged out successfully");
    }

    public UserDTO getCurrentUser() {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null || !authentication.isAuthenticated()
                || !(authentication.getPrincipal() instanceof User)) {
            throw new UnauthorizedException("Not authenticated");
        }

        User principal = (User) authentication.getPrincipal();
        User user = userRepository.findById(principal.getId())
                .orElseThrow(() -> new ResourceNotFoundException("User not found"));

        return mapToDTO(user);
    }

    private UserDTO mapToDTO(User user) {
        return UserDTO.builder()
                .id(user.getId())
                .username(user.getUsername())
                .email(user.getEmail())
                .enabled(user.isEnabled())
                .createdAt(user.getCreatedAt())
                .build();
    }
}
