package com.drone_command_center.config;

import com.drone_command_center.Entity.Drone;
import com.drone_command_center.Entity.Mission;
import com.drone_command_center.Entity.Sensor;
import com.drone_command_center.Entity.User;
import com.drone_command_center.Entity.Waypoint;
import com.drone_command_center.Entity.enums.*;
import com.drone_command_center.Repository.DroneRepository;
import com.drone_command_center.Repository.MissionRepository;
import com.drone_command_center.Repository.SensorRepository;
import com.drone_command_center.Repository.UserRepository;
import com.drone_command_center.Repository.WaypointRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/**
 * Seeds the demo accounts, sample drone, and sample missions on startup.
 *
 * <p>Idempotent: every seed step checks first and skips if the data already
 * exists. Controlled by {@code app.seed.enabled} (default {@code true} so a
 * fresh DB comes up demo-ready out of the box). Set
 * {@code APP_SEED_ENABLED=false} for production.
 */
@Slf4j
@Component
@RequiredArgsConstructor
@Profile("!test") // Don't run in test profile
public class DataSeeder implements CommandLineRunner {

    private final UserRepository userRepository;
    private final DroneRepository droneRepository;
    private final MissionRepository missionRepository;
    private final WaypointRepository waypointRepository;
    private final SensorRepository sensorRepository;
    private final PasswordEncoder passwordEncoder;

    @Value("${app.seed.enabled:true}")
    private boolean seedEnabled;

    @Value("${app.seed.operator.username:operator}")
    private String operatorUsername;

    @Value("${app.seed.operator.password:Operator@2026!}")
    private String operatorPassword;

    @Value("${app.seed.operator.email:operator@dronecommandcenter.com}")
    private String operatorEmail;

    @Value("${app.airsim.bridge.auth-user:navrl_bridge}")
    private String bridgeUsername;

    @Value("${app.airsim.bridge.auth-pass:NavRL@2026!}")
    private String bridgePassword;

    @Override
    public void run(String... args) {
        if (!seedEnabled) {
            log.info("Data seeding is disabled. Set app.seed.enabled=true to enable.");
            return;
        }

        log.info("Starting data seeding...");

        seedResearcherUser();
        User operator = seedOperatorUser();
        seedBridgeUser();
        Drone drone = seedSampleDrones();
        seedSensors(drone);
        seedSampleMissions(operator, drone);

        log.info("Data seeding completed.");
    }

    /**
     * Seeds the four-sensor stack matched to the modelled DJI M300 platform.
     * The {@code SensorService} pairs these rows with live telemetry to
     * report real readings — none of the values below are dummy data, they
     * describe the physical sensor specs.
     */
    private void seedSensors(Drone drone) {
        if (drone == null) {
            log.warn("No drone available \u2014 skipping sensor seeding.");
            return;
        }
        if (sensorRepository.findByDrone(drone).size() > 0) {
            log.info("Sensors already exist for drone {}, skipping...", drone.getName());
            return;
        }

        List<Sensor> sensors = List.of(
                Sensor.builder()
                        .type(SensorType.GPS)
                        .model("u-blox NEO-M9N")
                        .rangeMeters(0.0)        // not range-limited
                        .frequencyHz(10.0)
                        .enabled(true)
                        .drone(drone)
                        .build(),
                Sensor.builder()
                        .type(SensorType.IMU)
                        .model("Bosch BMI088")
                        .rangeMeters(0.0)        // inertial, no spatial range
                        .frequencyHz(200.0)
                        .enabled(true)
                        .drone(drone)
                        .build(),
                Sensor.builder()
                        .type(SensorType.LIDAR)
                        .model("Livox Mid-360")
                        .rangeMeters(40.0)
                        .frequencyHz(20.0)
                        .enabled(true)
                        .drone(drone)
                        .build(),
                Sensor.builder()
                        .type(SensorType.CAMERA)
                        .model("Zenmuse H20T (FPV)")
                        .rangeMeters(0.0)
                        .frequencyHz(30.0)
                        .enabled(true)
                        .drone(drone)
                        .build()
        );
        sensorRepository.saveAll(sensors);
        log.info("Created {} sensors for drone '{}'.", sensors.size(), drone.getName());
    }

    /**
     * Seeds a default operator account so panelists can log in immediately.
     */
    private User seedOperatorUser() {
        return userRepository.findByUsername(operatorUsername).orElseGet(() -> {
            User operator = User.builder()
                    .username(operatorUsername)
                    .password(passwordEncoder.encode(operatorPassword))
                    .email(operatorEmail)
                    .enabled(true)
                    .build();
            User saved = userRepository.save(operator);
            log.info("Created demo operator user: {} (password: {})", operatorUsername, operatorPassword);
            return saved;
        });
    }

    /**
     * Seeds the bridge service account using the same credentials the
     * AirSim Python bridge will read from {@code BRIDGE_AUTH_USER/PASS}.
     * Without this, the bridge cannot authenticate on first startup.
     */
    private void seedBridgeUser() {
        if (userRepository.findByUsername(bridgeUsername).isPresent()) {
            log.info("Bridge user '{}' already exists, skipping...", bridgeUsername);
            return;
        }

        User bridge = User.builder()
                .username(bridgeUsername)
                .password(passwordEncoder.encode(bridgePassword))
                .email(bridgeUsername + "@bridge.local")
                .enabled(true)
                .build();
        userRepository.save(bridge);
        log.info("Created AirSim bridge service user: {}", bridgeUsername);
    }

    private void seedResearcherUser() {
        String researcherUsername = "researcher";
        if (userRepository.findByUsername(researcherUsername).isPresent()) {
            log.info("Researcher user already exists, skipping...");
            return;
        }

        User researcher = User.builder()
                .username(researcherUsername)
                .password(passwordEncoder.encode("Research@2026!"))
                .email("researcher@dronecommandcenter.com")
                .enabled(true)
                .build();

        userRepository.save(researcher);
        log.info("Created researcher user: {}", researcherUsername);
    }

    private Drone seedSampleDrones() {
        if (droneRepository.count() > 0) {
            log.info("Drones already exist, skipping drone seeding...");
            return droneRepository.findAll().stream().findFirst().orElse(null);
        }

        // Seed a single sample drone to match the default AirSim deployment model.
        Drone drone = Drone.builder()
                .serialNumber("DJI-M300-001")
                .name("Alpha Scout")
                .modelType("DJI Matrice 300 RTK")
                .firmwareVersion("v2.5.1")
                .connectionStatus(ConnectionStatus.OFFLINE)
                .flightStatus(FlightStatus.IDLE)
                .autonomyLevel(AutonomyLevel.MANUAL)
                .navigationMode(NavigationMode.MANUAL)
                .batteryLevel(100.0)
                .latitude(37.7749)
                .longitude(-122.4194)
                .altitude(0.0)
                .failsafeEnabled(true)
                .obstacleDetected(false)
                .homeLatitude(37.7749)
                .homeLongitude(-122.4194)
                .homeAltitude(10.0)
                .registeredAt(Instant.now())
                .build();

        Drone saved = droneRepository.save(drone);
        log.info("Created 1 sample control drone: {}", saved.getName());
        return saved;
    }

    /**
     * Seeds 2 sample missions so the dashboard isn't empty on first launch.
     */
    private void seedSampleMissions(User operator, Drone drone) {
        if (operator == null) {
            log.warn("No operator user available \u2014 skipping sample mission seeding.");
            return;
        }
        if (missionRepository.count() > 0) {
            log.info("Missions already exist, skipping mission seeding...");
            return;
        }

        Mission inspection = missionRepository.save(Mission.builder()
                .name("Building Inspection Demo")
                .description("Sample autonomous inspection sweep around a building footprint.")
                .missionType(MissionType.INSPECTION)
                .status(MissionStatus.CREATED)
                .estimatedDurationMinutes(8)
                .createdBy(operator)
                .assignedDrone(drone)
                .createdAt(Instant.now())
                .goalNedX(40.0)
                .goalNedY(0.0)
                .baseAltitude(15.0)
                .waypoints(new ArrayList<>())
                .build());

        Mission patrol = missionRepository.save(Mission.builder()
                .name("Perimeter Patrol Demo")
                .description("Sample autonomous perimeter patrol used as the live demo mission.")
                .missionType(MissionType.NAVIGATION)
                .status(MissionStatus.CREATED)
                .estimatedDurationMinutes(5)
                .createdBy(operator)
                .assignedDrone(drone)
                .createdAt(Instant.now())
                .goalNedX(60.0)
                .goalNedY(20.0)
                .baseAltitude(12.0)
                .waypoints(new ArrayList<>())
                .build());

        seedWaypointsForInspection(inspection, drone);
        seedWaypointsForPatrol(patrol, drone);

        log.info("Created 2 sample missions with waypoints: '{}' and '{}'",
                inspection.getName(), patrol.getName());
    }

    /** Four-corner inspection orbit anchored on the drone's home position. */
    private void seedWaypointsForInspection(Mission mission, Drone drone) {
        double lat = drone.getHomeLatitude() != null ? drone.getHomeLatitude() : drone.getLatitude();
        double lon = drone.getHomeLongitude() != null ? drone.getHomeLongitude() : drone.getLongitude();
        // ~0.0001\u00b0 \u2248 11 m at the equator \u2014 good order of magnitude for an inspection orbit.
        double[][] corners = {
                {lat + 0.0001, lon, 15.0, 0.0},
                {lat + 0.0001, lon + 0.0001, 15.0, 90.0},
                {lat,          lon + 0.0001, 15.0, 180.0},
                {lat,          lon,          15.0, 270.0}
        };
        WaypointAction[] actions = {
                WaypointAction.SCAN_AREA, WaypointAction.TAKE_PHOTO,
                WaypointAction.SCAN_AREA, WaypointAction.RETURN_HOME
        };
        for (int i = 0; i < corners.length; i++) {
            waypointRepository.save(Waypoint.builder()
                    .sequenceOrder(i + 1)
                    .latitude(corners[i][0])
                    .longitude(corners[i][1])
                    .altitude(corners[i][2])
                    .heading(corners[i][3])
                    .speed(2.0)
                    .hoverDuration(i == 0 || i == 2 ? 5 : 0)
                    .action(actions[i])
                    .autoGenerated(false)
                    .mission(mission)
                    .build());
        }
    }

    /** Five-leg patrol path expressed in NavRL NED coordinates. */
    private void seedWaypointsForPatrol(Mission mission, Drone drone) {
        double lat = drone.getHomeLatitude() != null ? drone.getHomeLatitude() : drone.getLatitude();
        double lon = drone.getHomeLongitude() != null ? drone.getHomeLongitude() : drone.getLongitude();
        double[][] legs = {
                {15.0,  0.0},
                {30.0, 10.0},
                {45.0, 20.0},
                {60.0, 20.0}
        };
        for (int i = 0; i < legs.length; i++) {
            waypointRepository.save(Waypoint.builder()
                    .sequenceOrder(i + 1)
                    .latitude(lat)
                    .longitude(lon)
                    .altitude(12.0)
                    .heading(0.0)
                    .speed(2.0)
                    .hoverDuration(0)
                    .action(WaypointAction.FLY_THROUGH)
                    .nedX(legs[i][0])
                    .nedY(legs[i][1])
                    .autoGenerated(true)
                    .mission(mission)
                    .build());
        }
    }
}
