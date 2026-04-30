package com.drone_command_center.Service;

import com.drone_command_center.DTO.event.MissionEvent;
import com.drone_command_center.DTO.request.MissionCreateRequest;
import com.drone_command_center.DTO.request.WaypointCreateRequest;
import com.drone_command_center.DTO.response.MissionDTO;
import com.drone_command_center.DTO.response.PagedResponse;
import com.drone_command_center.DTO.response.WaypointDTO;
import com.drone_command_center.Entity.Drone;
import com.drone_command_center.Entity.Mission;
import com.drone_command_center.Entity.User;
import com.drone_command_center.Entity.Waypoint;
import com.drone_command_center.Entity.enums.ConnectionStatus;
import com.drone_command_center.Entity.enums.MissionStatus;
import com.drone_command_center.Repository.DroneRepository;
import com.drone_command_center.Repository.MissionRepository;
import com.drone_command_center.Repository.UserRepository;
import com.drone_command_center.Repository.WaypointRepository;
import com.drone_command_center.exception.InvalidOperationException;
import com.drone_command_center.exception.ResourceNotFoundException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class MissionService {

    private final MissionRepository missionRepository;
    private final DroneRepository droneRepository;
    private final UserRepository userRepository;
    private final WaypointRepository waypointRepository;
    private final Optional<EventPublisher> eventPublisher;

    /**
     * Create a new mission
     */
    @Transactional
    public MissionDTO createMission(MissionCreateRequest request, UUID userId) {
        log.info("User {} creating mission: {}", userId, request.getName());
        
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new ResourceNotFoundException("User", "id", userId));

        Mission mission = Mission.builder()
                .name(request.getName())
                .description(request.getDescription())
                .missionType(request.getMissionType())
                .status(MissionStatus.CREATED)
                .estimatedDurationMinutes(request.getEstimatedDurationMinutes())
                .createdBy(user)
                .createdAt(Instant.now())
                .waypoints(new ArrayList<>())
                .build();

        // Assign drone if provided
        if (request.getAssignedDroneId() != null) {
            Drone drone = droneRepository.findById(request.getAssignedDroneId())
                    .orElseThrow(() -> new ResourceNotFoundException("Drone", "id", request.getAssignedDroneId()));
            mission.setAssignedDrone(drone);
        }

        Mission savedMission = missionRepository.save(mission);

        // Add waypoints if provided
        if (request.getWaypoints() != null && !request.getWaypoints().isEmpty()) {
            for (WaypointCreateRequest wpRequest : request.getWaypoints()) {
                Waypoint waypoint = Waypoint.builder()
                        .sequenceOrder(wpRequest.getSequenceOrder())
                        .latitude(wpRequest.getLatitude())
                        .longitude(wpRequest.getLongitude())
                        .altitude(wpRequest.getAltitude())
                        .speed(wpRequest.getSpeed())
                        .hoverDuration(wpRequest.getHoverDuration())
                        .action(wpRequest.getAction())
                        .heading(wpRequest.getHeading())
                        .mission(savedMission)
                        .build();
                waypointRepository.save(waypoint);
                savedMission.getWaypoints().add(waypoint);
            }
        }

        log.info("Mission {} created successfully", savedMission.getId());

        publishMissionEvent("CREATED", savedMission);

        return mapToDTO(savedMission);
    }

    /**
     * Get mission by ID
     */
    public MissionDTO getMissionById(UUID missionId) {
        Mission mission = findMissionOrThrow(missionId);
        return mapToDTO(mission);
    }

    private static final Set<String> ALLOWED_SORT_FIELDS = Set.of("name", "createdAt", "status", "missionType", "priority", "startedAt");
    private static final int MAX_PAGE_SIZE = 100;

    /**
     * Get all missions with pagination
     */
    public PagedResponse<MissionDTO> getAllMissions(int page, int size, String sortBy, String sortDir) {
        if (!ALLOWED_SORT_FIELDS.contains(sortBy)) {
            throw new InvalidOperationException("Invalid sort field: " + sortBy + ". Allowed: " + ALLOWED_SORT_FIELDS);
        }
        size = Math.min(size, MAX_PAGE_SIZE);
        Sort sort = sortDir.equalsIgnoreCase("desc") 
            ? Sort.by(sortBy).descending() 
            : Sort.by(sortBy).ascending();
        Pageable pageable = PageRequest.of(page, size, sort);
        
        Page<Mission> missionPage = missionRepository.findAll(pageable);
        
        List<MissionDTO> content = missionPage.getContent().stream()
                .map(this::mapToDTO)
                .collect(Collectors.toList());
        
        return PagedResponse.<MissionDTO>builder()
                .content(content)
                .page(missionPage.getNumber())
                .size(missionPage.getSize())
                .totalElements(missionPage.getTotalElements())
                .totalPages(missionPage.getTotalPages())
                .first(missionPage.isFirst())
                .last(missionPage.isLast())
                .build();
    }

    /**
     * Get missions by status
     */
    public List<MissionDTO> getMissionsByStatus(MissionStatus status) {
        return missionRepository.findByStatus(status).stream()
                .map(this::mapToDTO)
                .collect(Collectors.toList());
    }

    /**
     * Get missions by drone
     */
    public PagedResponse<MissionDTO> getMissionsByDrone(UUID droneId, int page, int size) {
        Pageable pageable = PageRequest.of(page, size, Sort.by("createdAt").descending());
        Page<Mission> missionPage = missionRepository.findByAssignedDroneId(droneId, pageable);
        
        List<MissionDTO> content = missionPage.getContent().stream()
                .map(this::mapToDTO)
                .collect(Collectors.toList());
        
        return PagedResponse.<MissionDTO>builder()
                .content(content)
                .page(missionPage.getNumber())
                .size(missionPage.getSize())
                .totalElements(missionPage.getTotalElements())
                .totalPages(missionPage.getTotalPages())
                .first(missionPage.isFirst())
                .last(missionPage.isLast())
                .build();
    }

    /**
     * Get missions created by user
     */
    public PagedResponse<MissionDTO> getMissionsByUser(UUID userId, int page, int size) {
        Pageable pageable = PageRequest.of(page, size, Sort.by("createdAt").descending());
        Page<Mission> missionPage = missionRepository.findByCreatedById(userId, pageable);
        
        List<MissionDTO> content = missionPage.getContent().stream()
                .map(this::mapToDTO)
                .collect(Collectors.toList());
        
        return PagedResponse.<MissionDTO>builder()
                .content(content)
                .page(missionPage.getNumber())
                .size(missionPage.getSize())
                .totalElements(missionPage.getTotalElements())
                .totalPages(missionPage.getTotalPages())
                .first(missionPage.isFirst())
                .last(missionPage.isLast())
                .build();
    }

    /**
     * Assign drone to mission
     */
    @Transactional
    public MissionDTO assignDroneToMission(UUID missionId, UUID droneId) {
        Mission mission = findMissionOrThrow(missionId);
        Drone drone = droneRepository.findById(droneId)
                .orElseThrow(() -> new ResourceNotFoundException("Drone", "id", droneId));

        // Check if drone already has an active mission
        List<MissionStatus> activeStatuses = Arrays.asList(MissionStatus.ACTIVE, MissionStatus.IN_PROGRESS);
        if (missionRepository.existsByAssignedDroneIdAndStatusIn(droneId, activeStatuses)) {
            throw new InvalidOperationException("Drone already has an active mission");
        }

        mission.setAssignedDrone(drone);
        Mission savedMission = missionRepository.save(mission);
        log.info("Drone {} assigned to mission {}", droneId, missionId);
        return mapToDTO(savedMission);
    }

    /**
     * Start a mission
     */
    @Transactional
    public MissionDTO startMission(UUID missionId) {
        Mission mission = findMissionOrThrow(missionId);

        // Validate mission can be started
        if (mission.getStatus() != MissionStatus.CREATED && mission.getStatus() != MissionStatus.PLANNED) {
            throw new InvalidOperationException("Mission cannot be started. Current status: " + mission.getStatus());
        }

        if (mission.getAssignedDrone() == null) {
            throw new InvalidOperationException("Cannot start mission: No drone assigned");
        }

        if (mission.getAssignedDrone().getConnectionStatus() != ConnectionStatus.ONLINE) {
            throw new InvalidOperationException("Cannot start mission: Assigned drone is not connected");
        }

        if (mission.getWaypoints() == null || mission.getWaypoints().isEmpty()) {
            throw new InvalidOperationException("Cannot start mission: No waypoints defined");
        }

        mission.setStatus(MissionStatus.ACTIVE);
        mission.setStartedAt(Instant.now());
        Mission savedMission = missionRepository.save(mission);
        log.info("Mission {} started", missionId);

        publishMissionEvent("STARTED", savedMission);

        return mapToDTO(savedMission);
    }

    /**
     * Pause a mission
     */
    @Transactional
    public MissionDTO pauseMission(UUID missionId) {
        Mission mission = findMissionOrThrow(missionId);

        if (mission.getStatus() != MissionStatus.ACTIVE && mission.getStatus() != MissionStatus.IN_PROGRESS) {
            throw new InvalidOperationException("Mission cannot be paused. Current status: " + mission.getStatus());
        }

        mission.setStatus(MissionStatus.PAUSED);
        Mission savedMission = missionRepository.save(mission);
        log.info("Mission {} paused", missionId);
        return mapToDTO(savedMission);
    }

    /**
     * Resume a paused mission
     */
    @Transactional
    public MissionDTO resumeMission(UUID missionId) {
        Mission mission = findMissionOrThrow(missionId);

        if (mission.getStatus() != MissionStatus.PAUSED) {
            throw new InvalidOperationException("Mission cannot be resumed. Current status: " + mission.getStatus());
        }

        mission.setStatus(MissionStatus.ACTIVE);
        Mission savedMission = missionRepository.save(mission);
        log.info("Mission {} resumed", missionId);
        return mapToDTO(savedMission);
    }

    /**
     * Complete a mission
     */
    @Transactional
    public MissionDTO completeMission(UUID missionId, boolean success) {
        Mission mission = findMissionOrThrow(missionId);

        if (success) {
            mission.setStatus(MissionStatus.COMPLETED);
            log.info("Mission {} completed successfully", missionId);
        } else {
            mission.setStatus(MissionStatus.FAILED);
            log.warn("Mission {} failed", missionId);
        }
        mission.setCompletedAt(Instant.now());
        
        Mission savedMission = missionRepository.save(mission);

        publishMissionEvent("COMPLETED", savedMission);

        return mapToDTO(savedMission);
    }

    /**
     * Abort a mission
     */
    @Transactional
    public MissionDTO abortMission(UUID missionId) {
        Mission mission = findMissionOrThrow(missionId);

        if (mission.getStatus() == MissionStatus.COMPLETED || mission.getStatus() == MissionStatus.FAILED) {
            throw new InvalidOperationException("Cannot abort mission that is already completed or failed");
        }

        mission.setStatus(MissionStatus.ABORTED);
        mission.setCompletedAt(Instant.now());
        Mission savedMission = missionRepository.save(mission);
        log.info("Mission {} aborted", missionId);

        publishMissionEvent("ABORTED", savedMission);

        return mapToDTO(savedMission);
    }

    /**
     * Add waypoint to mission
     */
    @Transactional
    public MissionDTO addWaypoint(UUID missionId, WaypointCreateRequest request) {
        Mission mission = findMissionOrThrow(missionId);

        if (mission.getStatus() != MissionStatus.CREATED && mission.getStatus() != MissionStatus.PLANNED) {
            throw new InvalidOperationException("Cannot add waypoints to mission that has already started");
        }

        Waypoint waypoint = Waypoint.builder()
                .sequenceOrder(request.getSequenceOrder())
                .latitude(request.getLatitude())
                .longitude(request.getLongitude())
                .altitude(request.getAltitude())
                .speed(request.getSpeed())
                .hoverDuration(request.getHoverDuration())
                .action(request.getAction())
                .heading(request.getHeading())
                .mission(mission)
                .build();

        waypointRepository.save(waypoint);
        mission.getWaypoints().add(waypoint);
        
        log.info("Waypoint added to mission {}", missionId);
        return mapToDTO(mission);
    }

    /**
     * Remove waypoint from mission
     */
    @Transactional
    public MissionDTO removeWaypoint(UUID missionId, UUID waypointId) {
        Mission mission = findMissionOrThrow(missionId);

        if (mission.getStatus() != MissionStatus.CREATED && mission.getStatus() != MissionStatus.PLANNED) {
            throw new InvalidOperationException("Cannot remove waypoints from mission that has already started");
        }

        Waypoint waypoint = waypointRepository.findById(waypointId)
                .orElseThrow(() -> new ResourceNotFoundException("Waypoint", "id", waypointId));

        if (!waypoint.getMission().getId().equals(missionId)) {
            throw new InvalidOperationException("Waypoint does not belong to this mission");
        }

        mission.getWaypoints().remove(waypoint);
        waypointRepository.delete(waypoint);
        
        log.info("Waypoint {} removed from mission {}", waypointId, missionId);
        return mapToDTO(mission);
    }

    /**
     * Delete a mission
     */
    @Transactional
    public void deleteMission(UUID missionId) {
        Mission mission = findMissionOrThrow(missionId);

        if (mission.getStatus() == MissionStatus.ACTIVE || mission.getStatus() == MissionStatus.IN_PROGRESS) {
            throw new InvalidOperationException("Cannot delete active mission. Please abort it first.");
        }

        missionRepository.delete(mission);
        log.info("Mission {} deleted", missionId);
    }

    /**
     * Get mission statistics
     */
    public MissionStatistics getMissionStatistics() {
        return MissionStatistics.builder()
                .totalMissions(missionRepository.count())
                .createdMissions(missionRepository.countByStatus(MissionStatus.CREATED))
                .activeMissions(missionRepository.countByStatus(MissionStatus.ACTIVE))
                .completedMissions(missionRepository.countByStatus(MissionStatus.COMPLETED))
                .failedMissions(missionRepository.countByStatus(MissionStatus.FAILED))
                .build();
    }

    // Helper methods
    private Mission findMissionOrThrow(UUID missionId) {
        return missionRepository.findById(missionId)
                .orElseThrow(() -> new ResourceNotFoundException("Mission", "id", missionId));
    }

    private void publishMissionEvent(String eventType, Mission mission) {
        eventPublisher.ifPresent(ep -> ep.publish("mission." + eventType.toLowerCase(), MissionEvent.builder()
                .eventType(eventType)
                .missionId(mission.getId())
                .missionName(mission.getName())
                .status(mission.getStatus().name())
                .droneId(mission.getAssignedDrone() != null ? mission.getAssignedDrone().getId() : null)
                .userId(mission.getCreatedBy() != null ? mission.getCreatedBy().getId() : null)
                .timestamp(Instant.now())
                .build()));
    }

    private MissionDTO mapToDTO(Mission mission) {
        List<WaypointDTO> waypointDTOs = mission.getWaypoints() != null 
            ? mission.getWaypoints().stream()
                .map(this::mapWaypointToDTO)
                .collect(Collectors.toList())
            : new ArrayList<>();

        return MissionDTO.builder()
                .id(mission.getId())
                .name(mission.getName())
                .description(mission.getDescription())
                .missionType(mission.getMissionType())
                .status(mission.getStatus())
                .createdAt(mission.getCreatedAt())
                .startedAt(mission.getStartedAt())
                .completedAt(mission.getCompletedAt())
                .estimatedDurationMinutes(mission.getEstimatedDurationMinutes())
                .createdByUserId(mission.getCreatedBy() != null ? mission.getCreatedBy().getId() : null)
                .createdByUsername(mission.getCreatedBy() != null ? mission.getCreatedBy().getUsername() : null)
                .assignedDroneId(mission.getAssignedDrone() != null ? mission.getAssignedDrone().getId() : null)
                .assignedDroneName(mission.getAssignedDrone() != null ? mission.getAssignedDrone().getName() : null)
                .waypoints(waypointDTOs)
                .build();
    }

    private WaypointDTO mapWaypointToDTO(Waypoint waypoint) {
        return WaypointDTO.builder()
                .id(waypoint.getId())
                .sequenceOrder(waypoint.getSequenceOrder())
                .latitude(waypoint.getLatitude())
                .longitude(waypoint.getLongitude())
                .altitude(waypoint.getAltitude())
                .speed(waypoint.getSpeed())
                .hoverDuration(waypoint.getHoverDuration())
                .action(waypoint.getAction())
                .heading(waypoint.getHeading())
                .build();
    }

    // Inner class for statistics
    @lombok.Builder
    @lombok.Data
    public static class MissionStatistics {
        private long totalMissions;
        private long createdMissions;
        private long activeMissions;
        private long completedMissions;
        private long failedMissions;
    }
}
