package com.drone_command_center.Service;

import com.drone_command_center.DTO.RegisterRequest;
import com.drone_command_center.DTO.response.PagedResponse;
import com.drone_command_center.DTO.response.UserDTO;
import com.drone_command_center.Entity.User;
import com.drone_command_center.Repository.UserRepository;
import com.drone_command_center.exception.DuplicateResourceException;
import com.drone_command_center.exception.InvalidOperationException;
import com.drone_command_center.exception.ResourceNotFoundException;
import com.drone_command_center.exception.UnauthorizedException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class UserService {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;

    /**
     * Create a new user
     */
    @Transactional
    public UserDTO createUser(RegisterRequest request) {
        log.info("Creating new user: {}", request.getUsername());
        
        if (userRepository.existsByUsername(request.getUsername())) {
            throw new DuplicateResourceException("User", "username", request.getUsername());
        }

        if (userRepository.existsByEmail(request.getEmail())) {
            throw new DuplicateResourceException("User", "email", request.getEmail());
        }

        User user = User.builder()
                .username(request.getUsername())
                .password(passwordEncoder.encode(request.getPassword()))
                .email(request.getEmail())
                .build();

        User savedUser = userRepository.save(user);
        log.info("User {} created successfully", savedUser.getId());
        return mapToDTO(savedUser);
    }

    /**
     * Get user by ID
     */
    public UserDTO getUserById(UUID userId) {
        User user = findUserOrThrow(userId);
        return mapToDTO(user);
    }

    /**
     * Get user by username
     */
    public UserDTO getUserByUsername(String username) {
        User user = userRepository.findByUsername(username)
                .orElseThrow(() -> new ResourceNotFoundException("User", "username", username));
        return mapToDTO(user);
    }

    /**
     * Get user entity by username (for internal use)
     */
    public User getUserEntityByUsername(String username) {
        return userRepository.findByUsername(username)
                .orElseThrow(() -> new ResourceNotFoundException("User", "username", username));
    }

    private static final Set<String> ALLOWED_SORT_FIELDS = Set.of("username", "email", "createdAt", "enabled");
    private static final int MAX_PAGE_SIZE = 100;

    /**
     * Get all users with pagination
     */
    public PagedResponse<UserDTO> getAllUsers(int page, int size, String sortBy, String sortDir) {
        if (!ALLOWED_SORT_FIELDS.contains(sortBy)) {
            throw new InvalidOperationException("Invalid sort field: " + sortBy + ". Allowed: " + ALLOWED_SORT_FIELDS);
        }
        size = Math.min(size, MAX_PAGE_SIZE);
        Sort sort = sortDir.equalsIgnoreCase("desc") 
            ? Sort.by(sortBy).descending() 
            : Sort.by(sortBy).ascending();
        Pageable pageable = PageRequest.of(page, size, sort);
        
        Page<User> userPage = userRepository.findAll(pageable);
        
        List<UserDTO> content = userPage.getContent().stream()
                .map(this::mapToDTO)
                .collect(Collectors.toList());
        
        return PagedResponse.<UserDTO>builder()
                .content(content)
                .page(userPage.getNumber())
                .size(userPage.getSize())
                .totalElements(userPage.getTotalElements())
                .totalPages(userPage.getTotalPages())
                .first(userPage.isFirst())
                .last(userPage.isLast())
                .build();
    }

    /**
     * Get all users with pagination (simplified overload)
     */
    public PagedResponse<UserDTO> getAllUsers(int page, int size) {
        return getAllUsers(page, size, "username", "asc");
    }

    /**
     * Update user (email)
     */
    @Transactional
    public UserDTO updateUser(UUID userId, String email) {
        User user = findUserOrThrow(userId);
        
        if (email != null && !email.equals(user.getEmail())) {
            if (userRepository.existsByEmail(email)) {
                throw new DuplicateResourceException("User", "email", email);
            }
            user.setEmail(email);
        }
        
        User savedUser = userRepository.save(user);
        log.info("User {} updated", userId);
        return mapToDTO(savedUser);
    }

    /**
     * Update user email
     */
    @Transactional
    public UserDTO updateUserEmail(UUID userId, String email) {
        User user = findUserOrThrow(userId);
        
        if (!user.getEmail().equals(email) && userRepository.existsByEmail(email)) {
            throw new DuplicateResourceException("User", "email", email);
        }
        
        user.setEmail(email);
        User savedUser = userRepository.save(user);
        log.info("User {} email updated", userId);
        return mapToDTO(savedUser);
    }

    /**
     * Change user password (requires current password verification)
     */
    @Transactional
    public void changePassword(UUID userId, String currentPassword, String newPassword) {
        User user = findUserOrThrow(userId);
        
        if (!passwordEncoder.matches(currentPassword, user.getPassword())) {
            throw new UnauthorizedException("Current password is incorrect");
        }
        
        user.setPassword(passwordEncoder.encode(newPassword));
        userRepository.save(user);
        log.info("User {} password changed", userId);
    }

    /**
     * Reset user password (admin operation, no current password required)
     */
    @Transactional
    public void resetPassword(UUID userId, String newPassword) {
        User user = findUserOrThrow(userId);
        user.setPassword(passwordEncoder.encode(newPassword));
        userRepository.save(user);
        log.info("User {} password reset by admin", userId);
    }

    /**
     * Enable or disable user
     */
    @Transactional
    public UserDTO setUserEnabled(UUID userId, boolean enabled) {
        User user = findUserOrThrow(userId);
        user.setEnabled(enabled);
        User savedUser = userRepository.save(user);
        log.info("User {} enabled status set to {}", userId, enabled);
        return mapToDTO(savedUser);
    }

    /**
     * Check if the given userId belongs to the currently authenticated user
     */
    public boolean isCurrentUser(UUID userId) {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth == null || !auth.isAuthenticated()) {
            return false;
        }
        
        String currentUsername = auth.getName();
        return userRepository.findById(userId)
                .map(user -> user.getUsername().equals(currentUsername))
                .orElse(false);
    }

    /**
     * Delete a user
     */
    @Transactional
    public void deleteUser(UUID userId) {
        User user = findUserOrThrow(userId);
        userRepository.delete(user);
        log.info("User {} deleted", userId);
    }

    /**
     * Check if user exists
     */
    public boolean userExists(String username) {
        return userRepository.existsByUsername(username);
    }

    // Helper methods
    private User findUserOrThrow(UUID userId) {
        return userRepository.findById(userId)
                .orElseThrow(() -> new ResourceNotFoundException("User", "id", userId));
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
