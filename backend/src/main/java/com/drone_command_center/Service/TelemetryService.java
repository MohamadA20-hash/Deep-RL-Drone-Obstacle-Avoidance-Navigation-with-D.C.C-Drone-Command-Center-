package com.drone_command_center.Service;

import com.drone_command_center.DTO.event.TelemetryAlertEvent;
import com.drone_command_center.DTO.request.TelemetryCreateRequest;
import com.drone_command_center.DTO.response.FlightPathPointDTO;
import com.drone_command_center.DTO.response.PagedResponse;
import com.drone_command_center.DTO.response.TelemetryDTO;
import com.drone_command_center.Entity.Drone;
import com.drone_command_center.Entity.Telemetry;
import com.drone_command_center.Entity.enums.AutonomyLevel;
import com.drone_command_center.Entity.enums.ConnectionStatus;
import com.drone_command_center.Entity.enums.FlightStatus;
import com.drone_command_center.Entity.enums.NavigationMode;
import com.drone_command_center.Repository.DroneRepository;
import com.drone_command_center.Repository.TelemetryRepository;
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
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class TelemetryService {

    private final TelemetryRepository telemetryRepository;
    private final DroneRepository droneRepository;
    private final TelemetryWebSocketHandler webSocketHandler;
    private final Optional<EventPublisher> eventPublisher;

    private static final double LOW_BATTERY_THRESHOLD = 20.0;
    private static final double CRITICAL_BATTERY_THRESHOLD = 10.0;
    private static final double OBSTACLE_WARNING_DISTANCE = 5.0;
    private static final double OBSTACLE_CRITICAL_DISTANCE = 2.0;

    /**
     * Ingest telemetry data from a drone
     */
    @Transactional
    public TelemetryDTO ingestTelemetry(TelemetryCreateRequest request) {
        Drone drone = droneRepository.findById(request.getDroneId())
                .orElseGet(() -> autoRegisterBridgeDrone(request.getDroneId()));

        // Create telemetry record
        Telemetry telemetry = Telemetry.builder()
                .drone(drone)
                .timestamp(Instant.now())
                .latitude(request.getLatitude())
                .longitude(request.getLongitude())
                .altitude(request.getAltitude())
                .velocityX(request.getVelocityX())
                .velocityY(request.getVelocityY())
                .velocityZ(request.getVelocityZ())
                .yaw(request.getYaw())
                .pitch(request.getPitch())
                .roll(request.getRoll())
                .batteryLevel(request.getBatteryLevel())
                .obstacleDistance(request.getObstacleDistance())
                // NavRL fields
                .positionNedX(request.getPositionNedX())
                .positionNedY(request.getPositionNedY())
                .positionNedZ(request.getPositionNedZ())
                .altitudeMode(request.getAltitudeMode())
                .stuckReplanCount(request.getStuckReplanCount())
                .proactiveReplanCount(request.getProactiveReplanCount())
                .navigationEfficiency(request.getNavigationEfficiency())
                .pathLength(request.getPathLength())
                .optimalDistance(request.getOptimalDistance())
                .distanceToGoal(request.getDistanceToGoal())
                .mappedObstacleCells(request.getMappedObstacleCells())
                .closestObstacleDistance(request.getClosestObstacleDistance())
                .bestEffortActive(request.getBestEffortActive())
                .collisionCount(request.getCollisionCount())
                .currentPathWaypointCount(request.getCurrentPathWaypointCount())
                .navrlSpeed(request.getNavrlSpeed())
                .build();

        Telemetry savedTelemetry = telemetryRepository.save(telemetry);

        // Update drone's current state
        updateDroneState(drone, request);

        // Publish telemetry alerts via RabbitMQ
        publishTelemetryAlerts(drone, request);

        TelemetryDTO dto = mapToDTO(savedTelemetry);

        // Attach transient LiDAR scan (not persisted in DB)
        dto.setLidarScan(request.getLidarScan());

        // Broadcast to WebSocket subscribers
        webSocketHandler.broadcastTelemetry(request.getDroneId(), dto);

        log.debug("Telemetry recorded for drone {}", request.getDroneId());
        return dto;
    }

    /**
     * Auto-register a drone the first time the AirSim bridge sends telemetry for
     * an unknown UUID. This avoids the 404 deadlock where the bridge cannot push
     * any data unless an operator first manually creates the drone in the DB.
     * The created drone is a minimal stub that will be enriched by subsequent
     * telemetry frames (lat/lon/alt/NED/battery/heartbeat).
     */
    private Drone autoRegisterBridgeDrone(UUID droneId) {
        log.warn("Telemetry received for unknown drone {} \u2014 auto-registering bridge drone stub", droneId);
        String shortId = droneId.toString().substring(0, 8);
        Drone stub = Drone.builder()
                .id(droneId)
                .serialNumber("AIRSIM-" + shortId.toUpperCase())
                .name("AirSim Drone " + shortId)
                .modelType("AirSim Multirotor")
                .firmwareVersion("sim")
                .connectionStatus(ConnectionStatus.ONLINE)
                .flightStatus(FlightStatus.IDLE)
                .autonomyLevel(AutonomyLevel.MANUAL)
                .navigationMode(NavigationMode.MANUAL)
                .batteryLevel(100.0)
                .latitude(0.0)
                .longitude(0.0)
                .altitude(0.0)
                .failsafeEnabled(true)
                .obstacleDetected(false)
                .registeredAt(Instant.now())
                .lastHeartbeat(Instant.now())
                .build();
        return droneRepository.save(stub);
    }

    /**
     * Get latest telemetry for a drone
     */
    public TelemetryDTO getLatestTelemetry(UUID droneId) {
        // Verify drone exists
        droneRepository.findById(droneId)
                .orElseThrow(() -> new ResourceNotFoundException("Drone", "id", droneId));

        return telemetryRepository.findFirstByDroneIdOrderByTimestampDesc(droneId)
                .map(this::mapToDTO)
                .orElse(null);
    }

    /**
     * Get telemetry history for a drone with pagination
     */
    public PagedResponse<TelemetryDTO> getTelemetryHistory(UUID droneId, int page, int size) {
        Pageable pageable = PageRequest.of(page, size, Sort.by("timestamp").descending());
        Page<Telemetry> telemetryPage = telemetryRepository.findByDroneId(droneId, pageable);
        
        List<TelemetryDTO> content = telemetryPage.getContent().stream()
                .map(this::mapToDTO)
                .collect(Collectors.toList());
        
        return PagedResponse.<TelemetryDTO>builder()
                .content(content)
                .page(telemetryPage.getNumber())
                .size(telemetryPage.getSize())
                .totalElements(telemetryPage.getTotalElements())
                .totalPages(telemetryPage.getTotalPages())
                .first(telemetryPage.isFirst())
                .last(telemetryPage.isLast())
                .build();
    }

    /**
     * Get telemetry for a specific time range
     */
    public List<TelemetryDTO> getTelemetryInRange(UUID droneId, Instant start, Instant end) {
        return telemetryRepository.findByDroneIdAndTimestampBetween(droneId, start, end).stream()
                .map(this::mapToDTO)
                .collect(Collectors.toList());
    }

    /**
     * Get telemetry since a specific time
     */
    public List<TelemetryDTO> getTelemetrySince(UUID droneId, Instant since) {
        return telemetryRepository.findByDroneIdAndTimestampAfter(droneId, since).stream()
                .map(this::mapToDTO)
                .collect(Collectors.toList());
    }

    /**
     * Get the last N telemetry records for a drone
     */
    public List<TelemetryDTO> getLatestTelemetryRecords(UUID droneId, int count) {
        Pageable pageable = PageRequest.of(0, count);
        return telemetryRepository.findLatestByDroneId(droneId, pageable).stream()
                .map(this::mapToDTO)
                .collect(Collectors.toList());
    }

    /**
     * Get telemetry count for a drone
     */
    public long getTelemetryCount(UUID droneId) {
        return telemetryRepository.countByDroneId(droneId);
    }

    /**
     * Delete old telemetry data (for cleanup)
     */
    @Transactional
    public void deleteOldTelemetry(UUID droneId, int daysToKeep) {
        Instant cutoff = Instant.now().minus(daysToKeep, ChronoUnit.DAYS);
        telemetryRepository.deleteByDroneIdAndTimestampBefore(droneId, cutoff);
        log.info("Deleted telemetry older than {} days for drone {}", daysToKeep, droneId);
    }

    /**
     * Get flight path (series of coordinates)
     */
    public List<FlightPathPointDTO> getFlightPath(UUID droneId, Instant start, Instant end) {
        return telemetryRepository.findByDroneIdAndTimestampBetween(droneId, start, end).stream()
                .map(t -> FlightPathPointDTO.builder()
                        .timestamp(t.getTimestamp())
                        .latitude(t.getLatitude())
                        .longitude(t.getLongitude())
                        .altitude(t.getAltitude())
                        .build())
                .collect(Collectors.toList());
    }

    // Update drone's real-time state from telemetry
    private void updateDroneState(Drone drone, TelemetryCreateRequest request) {
        // Update position
        drone.setLatitude(request.getLatitude());
        drone.setLongitude(request.getLongitude());
        drone.setAltitude(request.getAltitude());

        // Update NED position if provided (NavRL)
        if (request.getPositionNedX() != null) {
            drone.setPositionNedX(request.getPositionNedX());
            drone.setPositionNedY(request.getPositionNedY());
            drone.setPositionNedZ(request.getPositionNedZ());
        }

        // Update NavRL navigation state
        if (request.getNavigationEfficiency() != null) {
            drone.setNavigationEfficiency(request.getNavigationEfficiency());
        }
        if (request.getDistanceToGoal() != null) {
            drone.setDistanceToGoal(request.getDistanceToGoal());
        }
        if (request.getAltitudeMode() != null) {
            drone.setAltitudeMode(request.getAltitudeMode());
        }
        if (request.getStuckReplanCount() != null || request.getProactiveReplanCount() != null) {
            int total = (request.getStuckReplanCount() != null ? request.getStuckReplanCount() : 0)
                      + (request.getProactiveReplanCount() != null ? request.getProactiveReplanCount() : 0);
            drone.setTotalReplanCount(total);
        }

        // Update battery
        drone.setBatteryLevel(request.getBatteryLevel());

        // Update connection status and heartbeat
        drone.setConnectionStatus(ConnectionStatus.ONLINE);
        drone.setLastHeartbeat(Instant.now());

        // Check for obstacle
        if (request.getObstacleDistance() > 0 && request.getObstacleDistance() < OBSTACLE_CRITICAL_DISTANCE) {
            drone.setObstacleDetected(true);
            log.warn("Obstacle detected for drone {} at distance {}", drone.getId(), request.getObstacleDistance());
        } else {
            drone.setObstacleDetected(false);
        }

        // Update flight status based on altitude and velocity
        // Preserve navigation-related statuses — don't overwrite NAVIGATING, REPLANNING, GOAL_REACHED
        FlightStatus currentStatus = drone.getFlightStatus();
        boolean isNavStatus = currentStatus == FlightStatus.NAVIGATING
                || currentStatus == FlightStatus.REPLANNING
                || currentStatus == FlightStatus.GOAL_REACHED;
        if (!isNavStatus) {
            if (request.getAltitude() > 1.0 && 
                (Math.abs(request.getVelocityX()) > 0.1 || 
                 Math.abs(request.getVelocityY()) > 0.1 || 
                 Math.abs(request.getVelocityZ()) > 0.1)) {
                drone.setFlightStatus(FlightStatus.IN_FLIGHT);
            } else if (request.getAltitude() > 0.5) {
                drone.setFlightStatus(FlightStatus.HOVERING);
            }
        }

        // Log warnings for low battery
        if (request.getBatteryLevel() < CRITICAL_BATTERY_THRESHOLD) {
            log.error("CRITICAL: Drone {} battery at {}%", drone.getId(), request.getBatteryLevel());
        } else if (request.getBatteryLevel() < LOW_BATTERY_THRESHOLD) {
            log.warn("Low battery for drone {}: {}%", drone.getId(), request.getBatteryLevel());
        }

        droneRepository.save(drone);
    }

    // Helper methods
    private TelemetryDTO mapToDTO(Telemetry telemetry) {
        return TelemetryDTO.builder()
                .id(telemetry.getId())
                .timestamp(telemetry.getTimestamp())
                .latitude(telemetry.getLatitude())
                .longitude(telemetry.getLongitude())
                .altitude(telemetry.getAltitude())
                .velocityX(telemetry.getVelocityX())
                .velocityY(telemetry.getVelocityY())
                .velocityZ(telemetry.getVelocityZ())
                .yaw(telemetry.getYaw())
                .pitch(telemetry.getPitch())
                .roll(telemetry.getRoll())
                .batteryLevel(telemetry.getBatteryLevel())
                .obstacleDistance(telemetry.getObstacleDistance())
                .droneId(telemetry.getDrone().getId())
                .droneName(telemetry.getDrone().getName())
                // NavRL fields
                .positionNedX(telemetry.getPositionNedX())
                .positionNedY(telemetry.getPositionNedY())
                .positionNedZ(telemetry.getPositionNedZ())
                .altitudeMode(telemetry.getAltitudeMode())
                .stuckReplanCount(telemetry.getStuckReplanCount())
                .proactiveReplanCount(telemetry.getProactiveReplanCount())
                .navigationEfficiency(telemetry.getNavigationEfficiency())
                .pathLength(telemetry.getPathLength())
                .optimalDistance(telemetry.getOptimalDistance())
                .distanceToGoal(telemetry.getDistanceToGoal())
                .mappedObstacleCells(telemetry.getMappedObstacleCells())
                .closestObstacleDistance(telemetry.getClosestObstacleDistance())
                .bestEffortActive(telemetry.getBestEffortActive())
                .collisionCount(telemetry.getCollisionCount())
                .currentPathWaypointCount(telemetry.getCurrentPathWaypointCount())
                .navrlSpeed(telemetry.getNavrlSpeed())
                .build();
    }

    private void publishTelemetryAlerts(Drone drone, TelemetryCreateRequest request) {
        if (request.getBatteryLevel() < CRITICAL_BATTERY_THRESHOLD) {
            eventPublisher.ifPresent(ep -> ep.publish("telemetry.low_battery", TelemetryAlertEvent.builder()
                    .alertType("CRITICAL_BATTERY")
                    .droneId(drone.getId())
                    .droneName(drone.getName())
                    .message(String.format("Critical battery level: %.1f%%", request.getBatteryLevel()))
                    .value(request.getBatteryLevel())
                    .timestamp(Instant.now())
                    .build()));
        } else if (request.getBatteryLevel() < LOW_BATTERY_THRESHOLD) {
            eventPublisher.ifPresent(ep -> ep.publish("telemetry.low_battery", TelemetryAlertEvent.builder()
                    .alertType("LOW_BATTERY")
                    .droneId(drone.getId())
                    .droneName(drone.getName())
                    .message(String.format("Low battery level: %.1f%%", request.getBatteryLevel()))
                    .value(request.getBatteryLevel())
                    .timestamp(Instant.now())
                    .build()));
        }

        if (request.getObstacleDistance() > 0 && request.getObstacleDistance() < OBSTACLE_WARNING_DISTANCE) {
            eventPublisher.ifPresent(ep -> ep.publish("telemetry.obstacle", TelemetryAlertEvent.builder()
                    .alertType("OBSTACLE_WARNING")
                    .droneId(drone.getId())
                    .droneName(drone.getName())
                    .message(String.format("Obstacle detected at %.1fm", request.getObstacleDistance()))
                    .value(request.getObstacleDistance())
                    .timestamp(Instant.now())
                    .build()));
        }
    }
}

