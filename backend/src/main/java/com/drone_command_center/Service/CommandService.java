package com.drone_command_center.Service;

import com.drone_command_center.DTO.event.CommandEvent;
import com.drone_command_center.DTO.request.CommandCreateRequest;
import com.drone_command_center.DTO.response.CommandDTO;
import com.drone_command_center.DTO.response.PagedResponse;
import com.drone_command_center.Entity.Command;
import com.drone_command_center.Entity.Drone;
import com.drone_command_center.Entity.Mission;
import com.drone_command_center.Entity.User;
import com.drone_command_center.Entity.enums.CommandStatus;
import com.drone_command_center.Entity.enums.CommandType;
import com.drone_command_center.Entity.enums.ConnectionStatus;
import com.drone_command_center.Entity.enums.FlightStatus;
import com.drone_command_center.Entity.enums.NavigationMode;
import com.drone_command_center.Repository.CommandRepository;
import com.drone_command_center.Repository.DroneRepository;
import com.drone_command_center.Repository.MissionRepository;
import com.drone_command_center.Repository.UserRepository;
import com.drone_command_center.exception.DroneNotConnectedException;
import com.drone_command_center.exception.InvalidOperationException;
import com.drone_command_center.exception.ResourceNotFoundException;
import com.drone_command_center.websocket.TelemetryWebSocketHandler;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class CommandService {

    private final CommandRepository commandRepository;
    private final DroneRepository droneRepository;
    private final UserRepository userRepository;
    private final MissionRepository missionRepository;
    private final Optional<EventPublisher> eventPublisher;
    private final TelemetryWebSocketHandler webSocketHandler;

    /**
     * Send a command to a drone
     */
    @Transactional
    public CommandDTO sendCommand(CommandCreateRequest request, UUID userId) {
        log.info("User {} sending {} command to drone {}", userId, request.getCommandType(), request.getDroneId());
        
        Drone drone = droneRepository.findById(request.getDroneId())
                .orElseThrow(() -> new ResourceNotFoundException("Drone", "id", request.getDroneId()));

        User user = userRepository.findById(userId)
                .orElseThrow(() -> new ResourceNotFoundException("User", "id", userId));

        // Log a warning if the drone is not ONLINE (may happen in simulation before the
        // NavRL bridge has established its first telemetry heartbeat).
        if (drone.getConnectionStatus() != ConnectionStatus.ONLINE) {
            log.warn("Drone {} is not ONLINE (status={}). Allowing command in simulation mode.",
                    drone.getSerialNumber(), drone.getConnectionStatus());
        }

        // Validate command based on current flight status
        validateCommand(drone, request.getCommandType());

        Command command = Command.builder()
                .drone(drone)
                .issuedBy(user)
                .commandType(request.getCommandType())
                .parameters(request.getParameters())
                .status(CommandStatus.PENDING)
                .createdAt(Instant.now())
                .build();

        Command savedCommand = commandRepository.save(command);
        log.info("Command {} created successfully", savedCommand.getId());
        
        // Update drone status based on command
        updateDroneStatusForCommand(drone, request.getCommandType());

        // Broadcast command via WebSocket so the Python bridge receives it instantly
        webSocketHandler.broadcastCommand(
                drone.getId(),
                request.getCommandType().name(),
                request.getParameters()
        );

        eventPublisher.ifPresent(ep -> ep.publish("command.sent", CommandEvent.builder()
                .eventType("SENT")
                .commandId(savedCommand.getId())
                .commandType(savedCommand.getCommandType().name())
                .status(savedCommand.getStatus().name())
                .droneId(drone.getId())
                .userId(userId)
                .timestamp(Instant.now())
                .build()));

        return mapToDTO(savedCommand);
    }

    /**
     * Send a command as part of a mission
     */
    @Transactional
    public CommandDTO sendMissionCommand(UUID droneId, UUID missionId, CommandType commandType, 
                                         String parameters, UUID userId) {
        Drone drone = droneRepository.findById(droneId)
                .orElseThrow(() -> new ResourceNotFoundException("Drone", "id", droneId));

        User user = userRepository.findById(userId)
                .orElseThrow(() -> new ResourceNotFoundException("User", "id", userId));

        Mission mission = missionRepository.findById(missionId)
                .orElseThrow(() -> new ResourceNotFoundException("Mission", "id", missionId));

        if (drone.getConnectionStatus() != ConnectionStatus.ONLINE) {
            log.warn("Drone {} is not ONLINE for mission command. Allowing in simulation mode.",
                    drone.getSerialNumber());
        }

        Command command = Command.builder()
                .drone(drone)
                .issuedBy(user)
                .mission(mission)
                .commandType(commandType)
                .parameters(parameters)
                .status(CommandStatus.PENDING)
                .createdAt(Instant.now())
                .build();

        Command savedCommand = commandRepository.save(command);
        return mapToDTO(savedCommand);
    }

    /**
     * Get command by ID
     */
    public CommandDTO getCommandById(UUID commandId) {
        Command command = findCommandOrThrow(commandId);
        return mapToDTO(command);
    }

    private static final Set<String> ALLOWED_SORT_FIELDS = Set.of("createdAt", "commandType", "status", "sentAt");
    private static final int MAX_PAGE_SIZE = 100;

    /**
     * Get all commands with pagination
     */
    public PagedResponse<CommandDTO> getAllCommands(int page, int size, String sortBy, String sortDir) {
        if (!ALLOWED_SORT_FIELDS.contains(sortBy)) {
            throw new InvalidOperationException("Invalid sort field: " + sortBy + ". Allowed: " + ALLOWED_SORT_FIELDS);
        }
        size = Math.min(size, MAX_PAGE_SIZE);
        Sort sort = sortDir.equalsIgnoreCase("desc") 
            ? Sort.by(sortBy).descending() 
            : Sort.by(sortBy).ascending();
        Pageable pageable = PageRequest.of(page, size, sort);
        
        Page<Command> commandPage = commandRepository.findAll(pageable);
        
        List<CommandDTO> content = commandPage.getContent().stream()
                .map(this::mapToDTO)
                .collect(Collectors.toList());
        
        return PagedResponse.<CommandDTO>builder()
                .content(content)
                .page(commandPage.getNumber())
                .size(commandPage.getSize())
                .totalElements(commandPage.getTotalElements())
                .totalPages(commandPage.getTotalPages())
                .first(commandPage.isFirst())
                .last(commandPage.isLast())
                .build();
    }

    /**
     * Get commands by drone
     */
    public PagedResponse<CommandDTO> getCommandsByDrone(UUID droneId, int page, int size) {
        Pageable pageable = PageRequest.of(page, size, Sort.by("createdAt").descending());
        Page<Command> commandPage = commandRepository.findByDroneId(droneId, pageable);
        
        List<CommandDTO> content = commandPage.getContent().stream()
                .map(this::mapToDTO)
                .collect(Collectors.toList());
        
        return PagedResponse.<CommandDTO>builder()
                .content(content)
                .page(commandPage.getNumber())
                .size(commandPage.getSize())
                .totalElements(commandPage.getTotalElements())
                .totalPages(commandPage.getTotalPages())
                .first(commandPage.isFirst())
                .last(commandPage.isLast())
                .build();
    }

    /**
     * Get pending commands for a drone
     */
    public List<CommandDTO> getPendingCommands(UUID droneId) {
        return commandRepository.findByDroneIdAndStatus(droneId, CommandStatus.PENDING).stream()
                .map(this::mapToDTO)
                .collect(Collectors.toList());
    }

    /**
     * Get commands by user
     */
    public PagedResponse<CommandDTO> getCommandsByUser(UUID userId, int page, int size) {
        Pageable pageable = PageRequest.of(page, size, Sort.by("createdAt").descending());
        Page<Command> commandPage = commandRepository.findByIssuedById(userId, pageable);
        
        List<CommandDTO> content = commandPage.getContent().stream()
                .map(this::mapToDTO)
                .collect(Collectors.toList());
        
        return PagedResponse.<CommandDTO>builder()
                .content(content)
                .page(commandPage.getNumber())
                .size(commandPage.getSize())
                .totalElements(commandPage.getTotalElements())
                .totalPages(commandPage.getTotalPages())
                .first(commandPage.isFirst())
                .last(commandPage.isLast())
                .build();
    }

    /**
     * Acknowledge command (mark as sent to drone)
     */
    @Transactional
    public CommandDTO markCommandAsSent(UUID commandId) {
        Command command = findCommandOrThrow(commandId);
        
        if (command.getStatus() != CommandStatus.PENDING) {
            throw new InvalidOperationException("Can only mark PENDING commands as sent");
        }
        
        command.setStatus(CommandStatus.SENT);
        Command savedCommand = commandRepository.save(command);
        log.info("Command {} marked as SENT", commandId);
        return mapToDTO(savedCommand);
    }

    /**
     * Acknowledge command execution
     */
    @Transactional
    public CommandDTO acknowledgeCommand(UUID commandId, boolean success) {
        Command command = findCommandOrThrow(commandId);
        
        if (success) {
            command.setStatus(CommandStatus.ACKNOWLEDGED);
            command.setExecutedAt(Instant.now());
            log.info("Command {} acknowledged successfully", commandId);
        } else {
            command.setStatus(CommandStatus.FAILED);
            log.warn("Command {} failed", commandId);
        }
        
        Command savedCommand = commandRepository.save(command);
        return mapToDTO(savedCommand);
    }

    /**
     * Cancel a pending command
     */
    @Transactional
    public void cancelCommand(UUID commandId) {
        Command command = findCommandOrThrow(commandId);
        
        if (command.getStatus() != CommandStatus.PENDING) {
            throw new InvalidOperationException("Can only cancel PENDING commands");
        }
        
        commandRepository.delete(command);
        log.info("Command {} cancelled", commandId);
    }

    /**
     * Get command statistics
     */
    public CommandStatistics getCommandStatistics() {
        return CommandStatistics.builder()
                .totalCommands(commandRepository.count())
                .pendingCommands(commandRepository.countByStatus(CommandStatus.PENDING))
                .sentCommands(commandRepository.countByStatus(CommandStatus.SENT))
                .acknowledgedCommands(commandRepository.countByStatus(CommandStatus.ACKNOWLEDGED))
                .failedCommands(commandRepository.countByStatus(CommandStatus.FAILED))
                .build();
    }

    // Validate command based on drone state
    private void validateCommand(Drone drone, CommandType commandType) {
        FlightStatus currentStatus = drone.getFlightStatus();
        
        switch (commandType) {
            case TAKEOFF:
                if (currentStatus != FlightStatus.IDLE && currentStatus != FlightStatus.LANDED) {
                    throw new InvalidOperationException("Cannot takeoff: Drone is not idle or landed. Current status: " + currentStatus);
                }
                if (drone.getBatteryLevel() < 20) {
                    throw new InvalidOperationException("Cannot takeoff: Battery level too low (" + drone.getBatteryLevel() + "%)");
                }
                break;
            case LAND:
                if (currentStatus != FlightStatus.IN_FLIGHT && currentStatus != FlightStatus.HOVERING
                    && currentStatus != FlightStatus.NAVIGATING) {
                    throw new InvalidOperationException("Cannot land: Drone is not in flight. Current status: " + currentStatus);
                }
                break;
            case MOVE:
                if (currentStatus != FlightStatus.IN_FLIGHT && currentStatus != FlightStatus.HOVERING) {
                    throw new InvalidOperationException("Cannot move: Drone is not in flight. Current status: " + currentStatus);
                }
                break;
            case SET_GOAL:
            case START_AUTONOMOUS_NAV:
                if (currentStatus != FlightStatus.IN_FLIGHT && currentStatus != FlightStatus.HOVERING
                    && currentStatus != FlightStatus.NAVIGATING && currentStatus != FlightStatus.GOAL_REACHED
                    && currentStatus != FlightStatus.IDLE && currentStatus != FlightStatus.LANDED) {
                    throw new InvalidOperationException("Cannot start navigation: Drone must be airborne or idle. Current status: " + currentStatus);
                }
                if (drone.getBatteryLevel() < 15) {
                    throw new InvalidOperationException("Cannot start navigation: Battery too low (" + drone.getBatteryLevel() + "%)");
                }
                break;
            case STOP_AUTONOMOUS_NAV:
            case PAUSE_NAV:
                if (currentStatus != FlightStatus.NAVIGATING && currentStatus != FlightStatus.REPLANNING) {
                    throw new InvalidOperationException("Cannot stop/pause nav: Drone is not navigating. Current status: " + currentStatus);
                }
                break;
            case RESUME_NAV:
                if (currentStatus != FlightStatus.HOVERING && currentStatus != FlightStatus.IN_FLIGHT) {
                    throw new InvalidOperationException("Cannot resume nav: Drone must be airborne. Current status: " + currentStatus);
                }
                break;
            case FORCE_REPLAN:
                if (currentStatus != FlightStatus.NAVIGATING) {
                    throw new InvalidOperationException("Cannot force replan: Drone is not navigating. Current status: " + currentStatus);
                }
                break;
            case SET_PLANNER_CONFIG:
                // Config changes are always allowed
                break;
            case EMERGENCY_STOP:
                // Emergency stop is always allowed
                break;
            case SET_MODE:
                // Mode change is always allowed
                break;
        }
    }

    // Update drone status based on command type
    private void updateDroneStatusForCommand(Drone drone, CommandType commandType) {
        switch (commandType) {
            case TAKEOFF:
                drone.setFlightStatus(FlightStatus.IN_FLIGHT);
                break;
            case LAND:
                drone.setFlightStatus(FlightStatus.LANDING);
                break;
            case EMERGENCY_STOP:
                drone.setFlightStatus(FlightStatus.EMERGENCY);
                break;
            case SET_GOAL:
                // Only store the goal — don't change flight status
                // Navigation starts when START_AUTONOMOUS_NAV is issued
                break;
            case START_AUTONOMOUS_NAV:
                drone.setFlightStatus(FlightStatus.NAVIGATING);
                drone.setNavigationMode(NavigationMode.RL_AGENT);
                break;
            case STOP_AUTONOMOUS_NAV:
                drone.setFlightStatus(FlightStatus.HOVERING);
                drone.setNavigationMode(NavigationMode.MANUAL);
                break;
            case PAUSE_NAV:
                drone.setFlightStatus(FlightStatus.HOVERING);
                break;
            case RESUME_NAV:
                drone.setFlightStatus(FlightStatus.NAVIGATING);
                break;
            case FORCE_REPLAN:
                drone.setFlightStatus(FlightStatus.REPLANNING);
                break;
            default:
                // Other commands don't change flight status
                break;
        }
        droneRepository.save(drone);
    }

    // Helper methods
    private Command findCommandOrThrow(UUID commandId) {
        return commandRepository.findById(commandId)
                .orElseThrow(() -> new ResourceNotFoundException("Command", "id", commandId));
    }

    private CommandDTO mapToDTO(Command command) {
        return CommandDTO.builder()
                .id(command.getId())
                .commandType(command.getCommandType())
                .parameters(command.getParameters())
                .status(command.getStatus())
                .createdAt(command.getCreatedAt())
                .executedAt(command.getExecutedAt())
                .issuedByUserId(command.getIssuedBy() != null ? command.getIssuedBy().getId() : null)
                .issuedByUsername(command.getIssuedBy() != null ? command.getIssuedBy().getUsername() : null)
                .droneId(command.getDrone().getId())
                .droneName(command.getDrone().getName())
                .missionId(command.getMission() != null ? command.getMission().getId() : null)
                .build();
    }

    // Inner class for statistics
    @lombok.Builder
    @lombok.Data
    public static class CommandStatistics {
        private long totalCommands;
        private long pendingCommands;
        private long sentCommands;
        private long acknowledgedCommands;
        private long failedCommands;
    }
}

