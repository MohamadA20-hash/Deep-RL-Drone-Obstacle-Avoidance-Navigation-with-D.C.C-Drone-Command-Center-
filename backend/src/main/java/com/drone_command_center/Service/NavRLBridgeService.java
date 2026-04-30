package com.drone_command_center.Service;

import com.drone_command_center.DTO.request.CommandCreateRequest;
import com.drone_command_center.DTO.response.CommandDTO;
import com.drone_command_center.DTO.response.DroneDTO;
import com.drone_command_center.Entity.Drone;
import com.drone_command_center.Entity.Mission;
import com.drone_command_center.Entity.enums.*;
import com.drone_command_center.Repository.DroneRepository;
import com.drone_command_center.Repository.MissionRepository;
import com.drone_command_center.exception.InvalidOperationException;
import com.drone_command_center.exception.ResourceNotFoundException;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PostConstruct;
import lombok.*;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

/**
 * Bridge service between the Drone Command Center and the NavRL autonomous
 * navigation planner. Handles goal-setting, planner configuration, and 
 * translates between the command center's data model and NavRL's AirSim 
 * NED coordinate system.
 *
 * NavRL operates in AirSim NED coordinates:
 *   x = North (meters), y = East (meters), z = Down (meters, negative = above ground)
 * 
 * NavRL planner capabilities:
 *   - A* global path planning on an occupancy grid
 *   - PPO+CNN local navigation (feedforward, 3-layer CNN → 128 + MLP 256→256)
 *   - Reactive altitude controller (CRUISE/CLIMBING/HOLDING/DESCENDING)
 *   - LiDAR: 4.0m range, 36 horizontal bins, 4 vertical bins
 *   - Max velocity: 2.0 m/s, Control frequency: 20 Hz
 *   - Confirmed obstacle memory with grid decay
 *   - Best-effort goal arrival for obstructed goals
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class NavRLBridgeService {

    private final CommandService commandService;
    private final DroneRepository droneRepository;
    private final MissionRepository missionRepository;
    private final ObjectMapper objectMapper;

    /**
     * Default NavRL planner configuration matching navrl_city_planner.py PlannerConfig
     */
    public static final Map<String, Object> DEFAULT_PLANNER_CONFIG = Map.ofEntries(
            Map.entry("grid_resolution", 2.0),
            Map.entry("grid_size", 200),
            Map.entry("grid_decay_max_age", 60.0),
            Map.entry("confirmed_obs_count", 3),
            Map.entry("lidar_range", 4.0),
            Map.entry("lidar_horizontal_bins", 36),
            Map.entry("lidar_vertical_bins", 4),
            Map.entry("max_velocity", 2.0),
            Map.entry("control_freq", 20),
            Map.entry("goal_tolerance", 3.0),
            Map.entry("waypoint_reach_threshold", 3.0),
            Map.entry("stuck_velocity_threshold", 0.15),
            Map.entry("stuck_time_threshold", 4.0),
            Map.entry("proactive_replan_interval", 8.0),
            Map.entry("best_effort_distance", 15.0),
            Map.entry("best_effort_replan_threshold", 2),
            Map.entry("yaw_vel_scale_threshold", 60.0),
            Map.entry("yaw_vel_min_scale", 0.5),
            Map.entry("smooth_iterations", 50),
            Map.entry("smooth_alpha", 0.3),
            Map.entry("min_altitude", 10),
            Map.entry("pitch_warning_threshold", 8.0),
            Map.entry("pitch_critical_threshold", 15.0),
            Map.entry("pitch_velocity_scale", 0.4),
            Map.entry("pitch_min_altitude_boost", 3.0)
    );

    /**
     * On boot: clear any stale navigation state left over from a previous
     * crash / hard-stop. If a drone's row was persisted with
     * flight_status=NAVIGATING|REPLANNING and a non-null goal, the bridge
     * would otherwise see isNavigating=true on its first /status poll and
     * spawn nav_worker against a goal the operator never re-issued.
     */
    @PostConstruct
    @Transactional
    public void resetStaleNavigationOnBoot() {
        try {
            int reset = 0;
            for (Drone d : droneRepository.findAll()) {
                FlightStatus fs = d.getFlightStatus();
                if (fs == FlightStatus.NAVIGATING
                        || fs == FlightStatus.REPLANNING
                        || fs == FlightStatus.GOAL_REACHED
                        || fs == FlightStatus.RETURNING_HOME
                        || fs == FlightStatus.EMERGENCY) {
                    log.warn("[boot] Clearing stale flight_status={} on drone {}", fs, d.getId());
                    d.setFlightStatus(FlightStatus.IDLE);
                }
                if (d.getGoalNedX() != null || d.getGoalNedY() != null) {
                    log.warn("[boot] Clearing stale goal ({}, {}) on drone {}",
                            d.getGoalNedX(), d.getGoalNedY(), d.getId());
                    d.setGoalNedX(null);
                    d.setGoalNedY(null);
                }
                droneRepository.save(d);
                reset++;
            }
            log.info("[boot] Inspected {} drone(s); navigation state cleared", reset);
        } catch (Exception e) {
            log.error("[boot] Failed to reset stale navigation state", e);
        }
    }

    /**
     * Set a navigation goal for a drone. This creates a SET_GOAL command
     * with the goal coordinates in NED meters.
     *
     * @param droneId  The drone UUID
     * @param goalX    Goal X position (North, meters)
     * @param goalY    Goal Y position (East, meters)
     * @param userId   The user issuing the command
     * @return CommandDTO for the created command
     */
    @Transactional
    public CommandDTO setNavigationGoal(UUID droneId, double goalX, double goalY, UUID userId) {
        Drone drone = droneRepository.findById(droneId)
                .orElseThrow(() -> new ResourceNotFoundException("Drone", "id", droneId));

        // Persist the goal coordinates so a later START_AUTONOMOUS_NAV can
        // pick them up. DO NOT change flightStatus here — setting NAVIGATING
        // would cause the AirSim bridge (which polls /api/navrl/drones/{id}/status
        // and reacts to isNavigating=true) to immediately spawn nav_worker,
        // which would defeat the START NAV / two-step UX. Navigation only
        // starts when the operator explicitly presses START NAV →
        // startAutonomousNavigation(...) below.
        drone.setGoalNedX(goalX);
        drone.setGoalNedY(goalY);
        droneRepository.save(drone);

        // Build command parameters
        Map<String, Object> params = new HashMap<>();
        params.put("goal_x", goalX);
        params.put("goal_y", goalY);

        String paramsJson;
        try {
            paramsJson = objectMapper.writeValueAsString(params);
        } catch (JsonProcessingException e) {
            throw new InvalidOperationException("Failed to serialize goal parameters");
        }

        CommandCreateRequest request = CommandCreateRequest.builder()
                .droneId(droneId)
                .commandType(CommandType.SET_GOAL)
                .parameters(paramsJson)
                .build();

        log.info("Setting NavRL goal for drone {} to [{}, {}]", droneId, goalX, goalY);
        return commandService.sendCommand(request, userId);
    }

    /**
     * Start autonomous navigation with optional planner config overrides.
     *
     * @param droneId        The drone UUID
     * @param goalX          Goal X position (North, meters)
     * @param goalY          Goal Y position (East, meters)
     * @param baseAltitude   Base flight altitude (meters, positive)
     * @param configOverrides Optional planner config overrides (null = use defaults)
     * @param userId         The user issuing the command
     * @return CommandDTO for the created command
     */
    @Transactional
    public CommandDTO startAutonomousNavigation(UUID droneId, Double goalX, Double goalY,
                                                 double baseAltitude, Map<String, Object> configOverrides,
                                                 UUID userId) {
        Drone drone = droneRepository.findById(droneId)
                .orElseThrow(() -> new ResourceNotFoundException("Drone", "id", droneId));

        // Use provided goal, or fall back to existing stored goal
        double gx = goalX != null ? goalX : (drone.getGoalNedX() != null ? drone.getGoalNedX() : 0.0);
        double gy = goalY != null ? goalY : (drone.getGoalNedY() != null ? drone.getGoalNedY() : 0.0);
        drone.setGoalNedX(gx);
        drone.setGoalNedY(gy);
        // Mark NAVIGATING so /status returns isNavigating=true → bridge spawns nav_worker.
        drone.setFlightStatus(FlightStatus.NAVIGATING);
        droneRepository.save(drone);

        // Build full parameters
        Map<String, Object> params = new HashMap<>();
        params.put("goal_x", gx);
        params.put("goal_y", gy);
        params.put("min_altitude", baseAltitude);

        // Merge config overrides with defaults
        Map<String, Object> config = new HashMap<>(DEFAULT_PLANNER_CONFIG);
        if (configOverrides != null) {
            config.putAll(configOverrides);
        }
        params.put("planner_config", config);

        String paramsJson;
        try {
            paramsJson = objectMapper.writeValueAsString(params);
        } catch (JsonProcessingException e) {
            throw new InvalidOperationException("Failed to serialize navigation parameters");
        }

        CommandCreateRequest request = CommandCreateRequest.builder()
                .droneId(droneId)
                .commandType(CommandType.START_AUTONOMOUS_NAV)
                .parameters(paramsJson)
                .build();

        log.info("Starting NavRL autonomous navigation for drone {} to [{}, {}] at altitude {}m",
                droneId, gx, gy, baseAltitude);
        return commandService.sendCommand(request, userId);
    }

    /**
     * Force the NavRL planner to recompute its A* path.
     */
    @Transactional
    public CommandDTO forceReplan(UUID droneId, UUID userId) {
        CommandCreateRequest request = CommandCreateRequest.builder()
                .droneId(droneId)
                .commandType(CommandType.FORCE_REPLAN)
                .parameters("{}")
                .build();

        log.info("Forcing NavRL replan for drone {}", droneId);
        return commandService.sendCommand(request, userId);
    }

    /**
     * Pause autonomous navigation (drone will hover in place).
     */
    @Transactional
    public CommandDTO pauseNavigation(UUID droneId, UUID userId) {
        CommandCreateRequest request = CommandCreateRequest.builder()
                .droneId(droneId)
                .commandType(CommandType.PAUSE_NAV)
                .parameters("{}")
                .build();

        log.info("Pausing NavRL navigation for drone {}", droneId);
        return commandService.sendCommand(request, userId);
    }

    /**
     * Resume a previously paused navigation.
     */
    @Transactional
    public CommandDTO resumeNavigation(UUID droneId, UUID userId) {
        CommandCreateRequest request = CommandCreateRequest.builder()
                .droneId(droneId)
                .commandType(CommandType.RESUME_NAV)
                .parameters("{}")
                .build();

        log.info("Resuming NavRL navigation for drone {}", droneId);
        return commandService.sendCommand(request, userId);
    }

    /**
     * Stop autonomous navigation and switch to manual mode.
     */
    @Transactional
    public CommandDTO stopNavigation(UUID droneId, UUID userId) {
        // Clear NAVIGATING flag so the AirSim bridge stops dispatching nav_worker.
        droneRepository.findById(droneId).ifPresent(d -> {
            if (d.getFlightStatus() == FlightStatus.NAVIGATING
                    || d.getFlightStatus() == FlightStatus.REPLANNING) {
                d.setFlightStatus(FlightStatus.HOVERING);
                droneRepository.save(d);
            }
        });

        CommandCreateRequest request = CommandCreateRequest.builder()
                .droneId(droneId)
                .commandType(CommandType.STOP_AUTONOMOUS_NAV)
                .parameters("{}")
                .build();

        log.info("Stopping NavRL navigation for drone {}", droneId);
        return commandService.sendCommand(request, userId);
    }

    /**
     * Emergency land — stops navigation and commands the drone to land immediately.
     * Sets flightStatus=EMERGENCY and clears the goal so the AirSim bridge will
     * (a) treat isNavigating=false on its next /status poll and stop dispatching
     * nav_worker, and (b) detect the EMERGENCY transition mid-flight to kill the
     * running nav_worker subprocess and call AirSim's landAsync() directly.
     */
    @Transactional
    public CommandDTO emergencyLand(UUID droneId, UUID userId) {
        droneRepository.findById(droneId).ifPresent(d -> {
            d.setFlightStatus(FlightStatus.EMERGENCY);
            d.setGoalNedX(null);
            d.setGoalNedY(null);
            droneRepository.save(d);
        });

        CommandCreateRequest request = CommandCreateRequest.builder()
                .droneId(droneId)
                .commandType(CommandType.EMERGENCY_STOP)
                .parameters("{\"action\":\"land\"}")
                .build();

        log.info("EMERGENCY LAND for drone {} — flightStatus=EMERGENCY, goal cleared", droneId);
        return commandService.sendCommand(request, userId);
    }

    /**
     * Update planner configuration on a running navigation session.
     */
    @Transactional
    public CommandDTO updatePlannerConfig(UUID droneId, Map<String, Object> configOverrides, UUID userId) {
        String paramsJson;
        try {
            paramsJson = objectMapper.writeValueAsString(configOverrides);
        } catch (JsonProcessingException e) {
            throw new InvalidOperationException("Failed to serialize planner config");
        }

        CommandCreateRequest request = CommandCreateRequest.builder()
                .droneId(droneId)
                .commandType(CommandType.SET_PLANNER_CONFIG)
                .parameters(paramsJson)
                .build();

        log.info("Updating NavRL planner config for drone {}", droneId);
        return commandService.sendCommand(request, userId);
    }

    /**
     * Get the default planner configuration as a reference.
     */
    public Map<String, Object> getDefaultPlannerConfig() {
        return new HashMap<>(DEFAULT_PLANNER_CONFIG);
    }

    /**
     * Mark navigation as complete and update drone flight status + metrics.
     */
    @Transactional
    public void completeNavigation(UUID droneId, boolean success, Map<String, Object> metrics) {
        Drone drone = droneRepository.findById(droneId)
                .orElseThrow(() -> new ResourceNotFoundException("Drone", "id", droneId));

        drone.setFlightStatus(success ? FlightStatus.GOAL_REACHED : FlightStatus.HOVERING);
        drone.setNavigationMode(NavigationMode.MANUAL);

        if (metrics != null) {
            if (metrics.containsKey("efficiency"))
                drone.setNavigationEfficiency(((Number) metrics.get("efficiency")).doubleValue());
            if (metrics.containsKey("replans"))
                drone.setTotalReplanCount(((Number) metrics.get("replans")).intValue());
            if (metrics.containsKey("distanceToGoal"))
                drone.setDistanceToGoal(((Number) metrics.get("distanceToGoal")).doubleValue());
            if (metrics.containsKey("altitudeMode"))
                drone.setAltitudeMode((String) metrics.get("altitudeMode"));
        }

        droneRepository.save(drone);
        log.info("NavRL navigation completed for drone {}: success={}", droneId, success);
    }

    /**
     * Get NavRL navigation status for a drone.
     */
    public NavRLStatus getNavigationStatus(UUID droneId) {
        Drone drone = droneRepository.findById(droneId)
                .orElseThrow(() -> new ResourceNotFoundException("Drone", "id", droneId));

        boolean isNavigating = drone.getFlightStatus() == FlightStatus.NAVIGATING
                || drone.getFlightStatus() == FlightStatus.REPLANNING;

        return NavRLStatus.builder()
                .droneId(droneId)
                .isNavigating(isNavigating)
                .navigationMode(drone.getNavigationMode())
                .flightStatus(drone.getFlightStatus())
                .positionNedX(drone.getPositionNedX())
                .positionNedY(drone.getPositionNedY())
                .positionNedZ(drone.getPositionNedZ())
                .goalNedX(drone.getGoalNedX())
                .goalNedY(drone.getGoalNedY())
                .distanceToGoal(drone.getDistanceToGoal())
                .navigationEfficiency(drone.getNavigationEfficiency())
                .totalReplanCount(drone.getTotalReplanCount())
                .altitudeMode(drone.getAltitudeMode())
                .build();
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class NavRLStatus {
        private UUID droneId;
        private boolean isNavigating;
        private NavigationMode navigationMode;
        private FlightStatus flightStatus;
        private Double positionNedX;
        private Double positionNedY;
        private Double positionNedZ;
        private Double goalNedX;
        private Double goalNedY;
        private Double distanceToGoal;
        private Double navigationEfficiency;
        private Integer totalReplanCount;
        private String altitudeMode;
    }
}
