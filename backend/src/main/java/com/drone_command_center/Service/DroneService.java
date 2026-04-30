package com.drone_command_center.Service;

import com.drone_command_center.DTO.event.DroneEvent;
import com.drone_command_center.DTO.request.DroneCreateRequest;
import com.drone_command_center.DTO.request.DroneUpdateRequest;
import com.drone_command_center.DTO.response.DroneDTO;
import com.drone_command_center.DTO.response.PagedResponse;
import com.drone_command_center.Entity.Drone;
import com.drone_command_center.Entity.User;
import com.drone_command_center.Entity.enums.ConnectionStatus;
import com.drone_command_center.Entity.enums.FlightStatus;
import com.drone_command_center.Entity.enums.NavigationMode;
import com.drone_command_center.Entity.enums.AutonomyLevel;
import com.drone_command_center.Repository.DroneRepository;
import com.drone_command_center.Repository.UserRepository;
import com.drone_command_center.exception.DuplicateResourceException;
import com.drone_command_center.exception.InvalidOperationException;
import com.drone_command_center.exception.ResourceNotFoundException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.Caching;
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
public class DroneService {

    private final DroneRepository droneRepository;
    private final UserRepository userRepository;
    private final Optional<EventPublisher> eventPublisher;

    /**
     * Register a new drone in the system
     */
    @Transactional
    @CacheEvict(value = "drones", allEntries = true)
    public DroneDTO registerDrone(DroneCreateRequest request) {
        log.info("Registering new drone with serial number: {}", request.getSerialNumber());
        
        if (droneRepository.existsBySerialNumber(request.getSerialNumber())) {
            throw new DuplicateResourceException("Drone", "serialNumber", request.getSerialNumber());
        }

        Drone drone = Drone.builder()
                .serialNumber(request.getSerialNumber())
                .name(request.getName())
                .modelType(request.getModelType())
                .firmwareVersion(request.getFirmwareVersion())
                .connectionStatus(ConnectionStatus.OFFLINE)
                .flightStatus(FlightStatus.IDLE)
                .autonomyLevel(request.getAutonomyLevel() != null ? request.getAutonomyLevel() : AutonomyLevel.MANUAL)
                .navigationMode(request.getNavigationMode() != null ? request.getNavigationMode() : NavigationMode.MANUAL)
                .batteryLevel(100.0)
                .latitude(0.0)
                .longitude(0.0)
                .altitude(0.0)
                .failsafeEnabled(request.getFailsafeEnabled() != null ? request.getFailsafeEnabled() : true)
                .obstacleDetected(false)
                .homeLatitude(request.getHomeLatitude())
                .homeLongitude(request.getHomeLongitude())
                .homeAltitude(request.getHomeAltitude())
                .registeredAt(Instant.now())
                .build();

        Drone savedDrone = droneRepository.save(drone);
        log.info("Drone registered successfully with ID: {}", savedDrone.getId());

        eventPublisher.ifPresent(ep -> ep.publish("drone.registered", DroneEvent.builder()
                .eventType("REGISTERED")
                .droneId(savedDrone.getId())
                .serialNumber(savedDrone.getSerialNumber())
                .droneName(savedDrone.getName())
                .status(savedDrone.getConnectionStatus().name())
                .timestamp(Instant.now())
                .build()));

        return mapToDTO(savedDrone);
    }

    private static final Set<String> ALLOWED_SORT_FIELDS = Set.of("name", "serialNumber", "registeredAt", "connectionStatus", "flightStatus", "batteryLevel", "modelType");
    private static final int MAX_PAGE_SIZE = 100;

    private int compareDronePriority(Drone left, Drone right) {
        int connectionCompare = Boolean.compare(
                right.getConnectionStatus() == ConnectionStatus.ONLINE,
                left.getConnectionStatus() == ConnectionStatus.ONLINE
        );
        if (connectionCompare != 0) {
            return connectionCompare;
        }

        int navCompare = Boolean.compare(isOperationalFlightState(right), isOperationalFlightState(left));
        if (navCompare != 0) {
            return navCompare;
        }

        int positionCompare = Boolean.compare(hasPosition(right), hasPosition(left));
        if (positionCompare != 0) {
            return positionCompare;
        }

        if (left.getLastHeartbeat() != null && right.getLastHeartbeat() != null) {
            int heartbeatCompare = right.getLastHeartbeat().compareTo(left.getLastHeartbeat());
            if (heartbeatCompare != 0) {
                return heartbeatCompare;
            }
        } else if (left.getLastHeartbeat() != null || right.getLastHeartbeat() != null) {
            return left.getLastHeartbeat() != null ? -1 : 1;
        }

        int batteryCompare = Double.compare(right.getBatteryLevel(), left.getBatteryLevel());
        if (batteryCompare != 0) {
            return batteryCompare;
        }

        return left.getName().compareToIgnoreCase(right.getName());
    }

    private boolean isOperationalFlightState(Drone drone) {
        return drone.getFlightStatus() == FlightStatus.NAVIGATING
                || drone.getFlightStatus() == FlightStatus.REPLANNING
                || drone.getFlightStatus() == FlightStatus.IN_FLIGHT
                || drone.getFlightStatus() == FlightStatus.HOVERING;
    }

    private boolean hasPosition(Drone drone) {
        return drone.getPositionNedX() != null
                || drone.getPositionNedY() != null;
    }

    /**
     * Get all drones with pagination
     */
    public PagedResponse<DroneDTO> getAllDrones(int page, int size, String sortBy, String sortDir) {
        if (!ALLOWED_SORT_FIELDS.contains(sortBy)) {
            throw new InvalidOperationException("Invalid sort field: " + sortBy + ". Allowed: " + ALLOWED_SORT_FIELDS);
        }
        size = Math.min(size, MAX_PAGE_SIZE);
        Sort sort = sortDir.equalsIgnoreCase("desc") 
            ? Sort.by(sortBy).descending() 
            : Sort.by(sortBy).ascending();
        Pageable pageable = PageRequest.of(page, size, sort);
        
        Page<Drone> dronePage = droneRepository.findAll(pageable);
        
        List<DroneDTO> content = dronePage.getContent().stream()
                .map(this::mapToDTO)
                .collect(Collectors.toList());
        
        return PagedResponse.<DroneDTO>builder()
                .content(content)
                .page(dronePage.getNumber())
                .size(dronePage.getSize())
                .totalElements(dronePage.getTotalElements())
                .totalPages(dronePage.getTotalPages())
                .first(dronePage.isFirst())
                .last(dronePage.isLast())
                .build();
    }

    /**
     * Get all drones (no pagination)
     */
    public List<DroneDTO> getAllDronesSimple() {
        return droneRepository.findAll().stream()
                .sorted(this::compareDronePriority)
                .map(this::mapToDTO)
                .collect(Collectors.toList());
    }

    /**
     * Get drones by connection status
     */
    public List<DroneDTO> getDronesByConnectionStatus(ConnectionStatus status) {
        return droneRepository.findByConnectionStatus(status).stream()
                .map(this::mapToDTO)
                .collect(Collectors.toList());
    }

    /**
     * Get drones by flight status
     */
    public List<DroneDTO> getDronesByFlightStatus(FlightStatus status) {
        return droneRepository.findByFlightStatus(status).stream()
                .map(this::mapToDTO)
                .collect(Collectors.toList());
    }

    /**
     * Get a single drone by ID
     */
    public DroneDTO getDroneById(UUID droneId) {
        Drone drone = findDroneOrThrow(droneId);
        return mapToDTO(drone);
    }

    /**
     * Get drone entity (for internal use)
     */
    public Drone getDroneEntity(UUID droneId) {
        return findDroneOrThrow(droneId);
    }

    /**
     * Update drone information
     */
    @Transactional
    @Caching(evict = {
            @CacheEvict(value = "drones", allEntries = true),
            @CacheEvict(value = "droneById", key = "#droneId")
    })
    public DroneDTO updateDrone(UUID droneId, DroneUpdateRequest request) {
        Drone drone = findDroneOrThrow(droneId);

        if (request.getName() != null) {
            drone.setName(request.getName());
        }
        if (request.getFirmwareVersion() != null) {
            drone.setFirmwareVersion(request.getFirmwareVersion());
        }
        if (request.getAutonomyLevel() != null) {
            drone.setAutonomyLevel(request.getAutonomyLevel());
        }
        if (request.getNavigationMode() != null) {
            drone.setNavigationMode(request.getNavigationMode());
        }
        if (request.getFailsafeEnabled() != null) {
            drone.setFailsafeEnabled(request.getFailsafeEnabled());
        }
        if (request.getHomeLatitude() != null) {
            drone.setHomeLatitude(request.getHomeLatitude());
        }
        if (request.getHomeLongitude() != null) {
            drone.setHomeLongitude(request.getHomeLongitude());
        }
        if (request.getHomeAltitude() != null) {
            drone.setHomeAltitude(request.getHomeAltitude());
        }

        Drone updatedDrone = droneRepository.save(drone);
        log.info("Drone {} updated successfully", droneId);
        return mapToDTO(updatedDrone);
    }

    /**
     * Delete a drone
     */
    @Transactional
    @Caching(evict = {
            @CacheEvict(value = "drones", allEntries = true),
            @CacheEvict(value = "droneById", key = "#droneId")
    })
    public void deleteDrone(UUID droneId) {
        Drone drone = findDroneOrThrow(droneId);
        
        if (drone.getFlightStatus() == FlightStatus.IN_FLIGHT || 
            drone.getFlightStatus() == FlightStatus.HOVERING) {
            throw new InvalidOperationException("Cannot delete drone while it is in flight or hovering");
        }
        
        droneRepository.delete(drone);
        log.info("Drone {} deleted successfully", droneId);

        eventPublisher.ifPresent(ep -> ep.publish("drone.deleted", DroneEvent.builder()
                .eventType("DELETED")
                .droneId(droneId)
                .serialNumber(drone.getSerialNumber())
                .droneName(drone.getName())
                .timestamp(Instant.now())
                .build()));
    }

    /**
     * Update drone connection status
     */
    @Transactional
    @CacheEvict(value = {"drones", "droneById"}, allEntries = true)
    public DroneDTO updateConnectionStatus(UUID droneId, ConnectionStatus status) {
        Drone drone = findDroneOrThrow(droneId);
        ConnectionStatus previousStatus = drone.getConnectionStatus();
        drone.setConnectionStatus(status);
        if (status == ConnectionStatus.ONLINE) {
            drone.setLastHeartbeat(Instant.now());
        }
        droneRepository.save(drone);

        eventPublisher.ifPresent(ep -> ep.publish("drone.status.changed", DroneEvent.builder()
                .eventType("STATUS_CHANGED")
                .droneId(droneId)
                .serialNumber(drone.getSerialNumber())
                .droneName(drone.getName())
                .status(status.name())
                .previousStatus(previousStatus.name())
                .timestamp(Instant.now())
                .build()));

        return mapToDTO(drone);
    }

    /**
     * Update drone flight status
     */
    @Transactional
    public void updateFlightStatus(UUID droneId, FlightStatus status) {
        Drone drone = findDroneOrThrow(droneId);
        drone.setFlightStatus(status);
        droneRepository.save(drone);
    }

    /**
     * Update drone position
     */
    @Transactional
    public void updatePosition(UUID droneId, double latitude, double longitude, double altitude) {
        Drone drone = findDroneOrThrow(droneId);
        drone.setLatitude(latitude);
        drone.setLongitude(longitude);
        drone.setAltitude(altitude);
        drone.setLastHeartbeat(Instant.now());
        drone.setConnectionStatus(ConnectionStatus.ONLINE);
        droneRepository.save(drone);
    }

    /**
     * Update battery level
     */
    @Transactional
    public void updateBatteryLevel(UUID droneId, double batteryLevel) {
        Drone drone = findDroneOrThrow(droneId);
        drone.setBatteryLevel(batteryLevel);
        droneRepository.save(drone);
    }

    /**
     * Check if drone is connected
     */
    public boolean isDroneConnected(UUID droneId) {
        Drone drone = findDroneOrThrow(droneId);
        return drone.getConnectionStatus() == ConnectionStatus.ONLINE;
    }

    /**
     * Get drones with low battery
     */
    public List<DroneDTO> getDronesWithLowBattery(double threshold) {
        return droneRepository.findByBatteryLevelLessThan(threshold).stream()
                .map(this::mapToDTO)
                .collect(Collectors.toList());
    }

    /**
     * Get count of drones by status
     */
    public long countByConnectionStatus(ConnectionStatus status) {
        return droneRepository.countByConnectionStatus(status);
    }

    // Helper methods
    private Drone findDroneOrThrow(UUID droneId) {
        return droneRepository.findById(droneId)
                .orElseThrow(() -> new ResourceNotFoundException("Drone", "id", droneId));
    }

    public DroneDTO mapToDTO(Drone drone) {
        return DroneDTO.builder()
                .id(drone.getId())
                .serialNumber(drone.getSerialNumber())
                .name(drone.getName())
                .modelType(drone.getModelType())
                .firmwareVersion(drone.getFirmwareVersion())
                .connectionStatus(drone.getConnectionStatus())
                .flightStatus(drone.getFlightStatus())
                .batteryLevel(drone.getBatteryLevel())
                .latitude(drone.getLatitude())
                .longitude(drone.getLongitude())
                .altitude(drone.getAltitude())
                .autonomyLevel(drone.getAutonomyLevel())
                .navigationMode(drone.getNavigationMode())
                .failsafeEnabled(drone.isFailsafeEnabled())
                .obstacleDetected(drone.isObstacleDetected())
                .lastHeartbeat(drone.getLastHeartbeat())
                .registeredAt(drone.getRegisteredAt())
                .homeLatitude(drone.getHomeLatitude())
                .homeLongitude(drone.getHomeLongitude())
                .homeAltitude(drone.getHomeAltitude())
                .positionNedX(drone.getPositionNedX())
                .positionNedY(drone.getPositionNedY())
                .positionNedZ(drone.getPositionNedZ())
                .goalNedX(drone.getGoalNedX())
                .goalNedY(drone.getGoalNedY())
                .navigationEfficiency(drone.getNavigationEfficiency())
                .totalReplanCount(drone.getTotalReplanCount())
                .distanceToGoal(drone.getDistanceToGoal())
                .altitudeMode(drone.getAltitudeMode())
                .build();
    }
}
