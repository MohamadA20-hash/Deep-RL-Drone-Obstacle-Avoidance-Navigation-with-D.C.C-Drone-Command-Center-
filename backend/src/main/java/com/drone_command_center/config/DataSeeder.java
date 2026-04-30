package com.drone_command_center.config;

import com.drone_command_center.Entity.Drone;
import com.drone_command_center.Entity.User;
import com.drone_command_center.Entity.enums.*;
import com.drone_command_center.Repository.DroneRepository;
import com.drone_command_center.Repository.UserRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

import java.time.Instant;

/**
 * Data seeder for initializing default data.
 * Only runs in development profile or when explicitly enabled.
 */
@Slf4j
@Component
@RequiredArgsConstructor
@Profile("!test") // Don't run in test profile
public class DataSeeder implements CommandLineRunner {

    private final UserRepository userRepository;
    private final DroneRepository droneRepository;
    private final PasswordEncoder passwordEncoder;

    @Value("${app.seed.enabled:false}")
    private boolean seedEnabled;

    @Override
    public void run(String... args) {
        if (!seedEnabled) {
            log.info("Data seeding is disabled. Set app.seed.enabled=true to enable.");
            return;
        }

        log.info("Starting data seeding...");

        seedResearcherUser();
        seedSampleDrones();

        log.info("Data seeding completed.");
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

    private void seedSampleDrones() {
        if (droneRepository.count() > 0) {
            log.info("Drones already exist, skipping drone seeding...");
            return;
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

        droneRepository.save(drone);
        log.info("Created 1 sample control drone");
    }
}
