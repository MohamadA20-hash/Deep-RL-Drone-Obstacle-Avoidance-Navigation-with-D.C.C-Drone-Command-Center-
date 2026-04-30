package com.drone_command_center.Service;

import com.drone_command_center.DTO.request.TelemetryCreateRequest;
import com.drone_command_center.DTO.response.TelemetryDTO;
import com.drone_command_center.Entity.Drone;
import com.drone_command_center.Entity.Telemetry;
import com.drone_command_center.Entity.enums.ConnectionStatus;
import com.drone_command_center.Entity.enums.FlightStatus;
import com.drone_command_center.Entity.enums.NavigationMode;
import com.drone_command_center.Repository.DroneRepository;
import com.drone_command_center.Repository.TelemetryRepository;
import com.drone_command_center.exception.ResourceNotFoundException;
import com.drone_command_center.websocket.TelemetryWebSocketHandler;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
@DisplayName("TelemetryService Tests")
class TelemetryServiceTest {

    @Mock
    private TelemetryRepository telemetryRepository;
    @Mock
    private DroneRepository droneRepository;
    @Mock
    private TelemetryWebSocketHandler webSocketHandler;
    @Mock
    private Optional<EventPublisher> eventPublisher;

    @InjectMocks
    private TelemetryService telemetryService;

    private Drone testDrone;
    private UUID droneId;

    @BeforeEach
    void setUp() {
        droneId = UUID.randomUUID();
        testDrone = Drone.builder()
                .id(droneId)
                .serialNumber("DJI-001")
                .name("Scout")
                .modelType("DJI M300")
                .connectionStatus(ConnectionStatus.ONLINE)
                .flightStatus(FlightStatus.IN_FLIGHT)
                .batteryLevel(85.0)
                .navigationMode(NavigationMode.MANUAL)
                .latitude(0.0)
                .longitude(0.0)
                .altitude(0.0)
                .build();
    }

    private TelemetryCreateRequest buildRequest(double battery, double altitude,
                                                 double velX, double velY, double velZ,
                                                 double obstacleDistance) {
        return TelemetryCreateRequest.builder()
                .droneId(droneId)
                .latitude(37.7749)
                .longitude(-122.4194)
                .altitude(altitude)
                .velocityX(velX)
                .velocityY(velY)
                .velocityZ(velZ)
                .yaw(90.0)
                .pitch(5.0)
                .roll(2.0)
                .batteryLevel(battery)
                .obstacleDistance(obstacleDistance)
                .build();
    }

    @Nested
    @DisplayName("Ingest Telemetry Tests")
    class IngestTelemetryTests {

        @Test
        @DisplayName("Should ingest telemetry successfully")
        void shouldIngestTelemetry() {
            TelemetryCreateRequest request = buildRequest(85.0, 50.0, 2.5, 1.0, 0.5, 10.0);

            Telemetry savedTelemetry = Telemetry.builder()
                    .id(UUID.randomUUID())
                    .drone(testDrone)
                    .timestamp(Instant.now())
                    .latitude(37.7749)
                    .longitude(-122.4194)
                    .altitude(50.0)
                    .batteryLevel(85.0)
                    .obstacleDistance(10.0)
                    .build();

            when(droneRepository.findById(droneId)).thenReturn(Optional.of(testDrone));
            when(telemetryRepository.save(any(Telemetry.class))).thenReturn(savedTelemetry);
            when(droneRepository.save(any(Drone.class))).thenReturn(testDrone);

            TelemetryDTO result = telemetryService.ingestTelemetry(request);

            assertThat(result).isNotNull();
            assertThat(result.getLatitude()).isEqualTo(37.7749);
            assertThat(result.getBatteryLevel()).isEqualTo(85.0);
            verify(telemetryRepository).save(any(Telemetry.class));
            verify(droneRepository).save(testDrone);
            verify(webSocketHandler).broadcastTelemetry(eq(droneId), any(TelemetryDTO.class));
        }

        @Test
        @DisplayName("Should update drone position from telemetry")
        void shouldUpdateDronePosition() {
            TelemetryCreateRequest request = buildRequest(75.0, 30.0, 1.0, 0.5, 0.0, 15.0);

            Telemetry savedTelemetry = Telemetry.builder()
                    .id(UUID.randomUUID())
                    .drone(testDrone)
                    .timestamp(Instant.now())
                    .latitude(37.7749)
                    .longitude(-122.4194)
                    .altitude(30.0)
                    .batteryLevel(75.0)
                    .build();

            when(droneRepository.findById(droneId)).thenReturn(Optional.of(testDrone));
            when(telemetryRepository.save(any(Telemetry.class))).thenReturn(savedTelemetry);
            when(droneRepository.save(any(Drone.class))).thenReturn(testDrone);

            telemetryService.ingestTelemetry(request);

            // Verify drone state was updated
            assertThat(testDrone.getLatitude()).isEqualTo(37.7749);
            assertThat(testDrone.getLongitude()).isEqualTo(-122.4194);
            assertThat(testDrone.getAltitude()).isEqualTo(30.0);
            assertThat(testDrone.getBatteryLevel()).isEqualTo(75.0);
            assertThat(testDrone.getConnectionStatus()).isEqualTo(ConnectionStatus.ONLINE);
        }

        @Test
        @DisplayName("Should detect obstacle when close")
        void shouldDetectObstacle() {
            TelemetryCreateRequest request = buildRequest(80.0, 20.0, 1.0, 0.0, 0.0, 1.5);

            Telemetry savedTelemetry = Telemetry.builder()
                    .id(UUID.randomUUID())
                    .drone(testDrone)
                    .timestamp(Instant.now())
                    .latitude(37.7749)
                    .longitude(-122.4194)
                    .altitude(20.0)
                    .batteryLevel(80.0)
                    .obstacleDistance(1.5)
                    .build();

            when(droneRepository.findById(droneId)).thenReturn(Optional.of(testDrone));
            when(telemetryRepository.save(any(Telemetry.class))).thenReturn(savedTelemetry);
            when(droneRepository.save(any(Drone.class))).thenReturn(testDrone);

            telemetryService.ingestTelemetry(request);

            // Obstacle distance 1.5 < OBSTACLE_CRITICAL_DISTANCE (2.0) → detected
            assertThat(testDrone.isObstacleDetected()).isTrue();
        }

        @Test
        @DisplayName("Should not detect obstacle when far")
        void shouldNotDetectObstacleFar() {
            TelemetryCreateRequest request = buildRequest(80.0, 20.0, 1.0, 0.0, 0.0, 10.0);

            Telemetry savedTelemetry = Telemetry.builder()
                    .id(UUID.randomUUID())
                    .drone(testDrone)
                    .timestamp(Instant.now())
                    .latitude(37.7749)
                    .longitude(-122.4194)
                    .altitude(20.0)
                    .batteryLevel(80.0)
                    .obstacleDistance(10.0)
                    .build();

            when(droneRepository.findById(droneId)).thenReturn(Optional.of(testDrone));
            when(telemetryRepository.save(any(Telemetry.class))).thenReturn(savedTelemetry);
            when(droneRepository.save(any(Drone.class))).thenReturn(testDrone);

            telemetryService.ingestTelemetry(request);

            assertThat(testDrone.isObstacleDetected()).isFalse();
        }

        @Test
        @DisplayName("Should throw when drone not found")
        void shouldThrowWhenDroneNotFound() {
            TelemetryCreateRequest request = buildRequest(85.0, 50.0, 0.0, 0.0, 0.0, 10.0);

            when(droneRepository.findById(droneId)).thenReturn(Optional.empty());

            assertThatThrownBy(() -> telemetryService.ingestTelemetry(request))
                    .isInstanceOf(ResourceNotFoundException.class);
        }

        @Test
        @DisplayName("Should set flight status to IN_FLIGHT when moving at altitude")
        void shouldSetInFlightWhenMoving() {
            // Drone starts as IDLE (not a nav status)
            testDrone.setFlightStatus(FlightStatus.IDLE);

            TelemetryCreateRequest request = buildRequest(80.0, 10.0, 3.0, 2.0, 0.0, 20.0);

            Telemetry savedTelemetry = Telemetry.builder()
                    .id(UUID.randomUUID())
                    .drone(testDrone)
                    .timestamp(Instant.now())
                    .latitude(37.7749)
                    .longitude(-122.4194)
                    .altitude(10.0)
                    .batteryLevel(80.0)
                    .build();

            when(droneRepository.findById(droneId)).thenReturn(Optional.of(testDrone));
            when(telemetryRepository.save(any(Telemetry.class))).thenReturn(savedTelemetry);
            when(droneRepository.save(any(Drone.class))).thenReturn(testDrone);

            telemetryService.ingestTelemetry(request);

            // altitude > 1.0 and velocity > 0.1 → IN_FLIGHT
            assertThat(testDrone.getFlightStatus()).isEqualTo(FlightStatus.IN_FLIGHT);
        }

        @Test
        @DisplayName("Should set HOVERING when at altitude with no velocity")
        void shouldSetHoveringWhenStationary() {
            testDrone.setFlightStatus(FlightStatus.IDLE);

            TelemetryCreateRequest request = buildRequest(80.0, 5.0, 0.0, 0.0, 0.0, 20.0);

            Telemetry savedTelemetry = Telemetry.builder()
                    .id(UUID.randomUUID())
                    .drone(testDrone)
                    .timestamp(Instant.now())
                    .latitude(37.7749)
                    .longitude(-122.4194)
                    .altitude(5.0)
                    .batteryLevel(80.0)
                    .build();

            when(droneRepository.findById(droneId)).thenReturn(Optional.of(testDrone));
            when(telemetryRepository.save(any(Telemetry.class))).thenReturn(savedTelemetry);
            when(droneRepository.save(any(Drone.class))).thenReturn(testDrone);

            telemetryService.ingestTelemetry(request);

            // altitude > 0.5, velocity all 0 → HOVERING
            assertThat(testDrone.getFlightStatus()).isEqualTo(FlightStatus.HOVERING);
        }

        @Test
        @DisplayName("Should preserve NAVIGATING status from telemetry")
        void shouldPreserveNavigatingStatus() {
            testDrone.setFlightStatus(FlightStatus.NAVIGATING);

            TelemetryCreateRequest request = buildRequest(80.0, 10.0, 3.0, 2.0, 0.0, 20.0);

            Telemetry savedTelemetry = Telemetry.builder()
                    .id(UUID.randomUUID())
                    .drone(testDrone)
                    .timestamp(Instant.now())
                    .latitude(37.7749)
                    .longitude(-122.4194)
                    .altitude(10.0)
                    .batteryLevel(80.0)
                    .build();

            when(droneRepository.findById(droneId)).thenReturn(Optional.of(testDrone));
            when(telemetryRepository.save(any(Telemetry.class))).thenReturn(savedTelemetry);
            when(droneRepository.save(any(Drone.class))).thenReturn(testDrone);

            telemetryService.ingestTelemetry(request);

            // NAVIGATING is a nav status - should NOT be overwritten
            assertThat(testDrone.getFlightStatus()).isEqualTo(FlightStatus.NAVIGATING);
        }

        @Test
        @DisplayName("Should update NavRL fields when provided")
        void shouldUpdateNavRLFields() {
            TelemetryCreateRequest request = buildRequest(80.0, 10.0, 1.0, 0.0, 0.0, 20.0);
            request.setPositionNedX(15.5);
            request.setPositionNedY(-8.3);
            request.setPositionNedZ(-10.0);
            request.setNavigationEfficiency(70.7);
            request.setDistanceToGoal(5.2);
            request.setAltitudeMode("CRUISE");

            Telemetry savedTelemetry = Telemetry.builder()
                    .id(UUID.randomUUID())
                    .drone(testDrone)
                    .timestamp(Instant.now())
                    .latitude(37.7749)
                    .longitude(-122.4194)
                    .altitude(10.0)
                    .batteryLevel(80.0)
                    .build();

            when(droneRepository.findById(droneId)).thenReturn(Optional.of(testDrone));
            when(telemetryRepository.save(any(Telemetry.class))).thenReturn(savedTelemetry);
            when(droneRepository.save(any(Drone.class))).thenReturn(testDrone);

            telemetryService.ingestTelemetry(request);

            assertThat(testDrone.getPositionNedX()).isEqualTo(15.5);
            assertThat(testDrone.getPositionNedY()).isEqualTo(-8.3);
            assertThat(testDrone.getNavigationEfficiency()).isEqualTo(70.7);
            assertThat(testDrone.getDistanceToGoal()).isEqualTo(5.2);
            assertThat(testDrone.getAltitudeMode()).isEqualTo("CRUISE");
        }
    }

    @Nested
    @DisplayName("Get Telemetry Tests")
    class GetTelemetryTests {

        @Test
        @DisplayName("Should get latest telemetry")
        void shouldGetLatestTelemetry() {
            Telemetry telemetry = Telemetry.builder()
                    .id(UUID.randomUUID())
                    .drone(testDrone)
                    .timestamp(Instant.now())
                    .latitude(37.7749)
                    .longitude(-122.4194)
                    .altitude(50.0)
                    .batteryLevel(85.0)
                    .build();

            when(droneRepository.findById(droneId)).thenReturn(Optional.of(testDrone));
            when(telemetryRepository.findFirstByDroneIdOrderByTimestampDesc(droneId))
                    .thenReturn(Optional.of(telemetry));

            TelemetryDTO result = telemetryService.getLatestTelemetry(droneId);

            assertThat(result).isNotNull();
            assertThat(result.getLatitude()).isEqualTo(37.7749);
            assertThat(result.getBatteryLevel()).isEqualTo(85.0);
        }

        @Test
        @DisplayName("Should return null when no telemetry exists")
        void shouldReturnNullWhenNoTelemetry() {
            when(droneRepository.findById(droneId)).thenReturn(Optional.of(testDrone));
            when(telemetryRepository.findFirstByDroneIdOrderByTimestampDesc(droneId))
                    .thenReturn(Optional.empty());

            TelemetryDTO result = telemetryService.getLatestTelemetry(droneId);

            assertThat(result).isNull();
        }

        @Test
        @DisplayName("Should throw when drone not found for latest telemetry")
        void shouldThrowWhenDroneNotFoundForLatest() {
            when(droneRepository.findById(droneId)).thenReturn(Optional.empty());

            assertThatThrownBy(() -> telemetryService.getLatestTelemetry(droneId))
                    .isInstanceOf(ResourceNotFoundException.class);
        }

        @Test
        @DisplayName("Should get telemetry count")
        void shouldGetTelemetryCount() {
            when(telemetryRepository.countByDroneId(droneId)).thenReturn(42L);

            long count = telemetryService.getTelemetryCount(droneId);

            assertThat(count).isEqualTo(42);
        }
    }

    @Nested
    @DisplayName("Cleanup Tests")
    class CleanupTests {

        @Test
        @DisplayName("Should delete old telemetry data")
        void shouldDeleteOldTelemetry() {
            telemetryService.deleteOldTelemetry(droneId, 30);

            verify(telemetryRepository).deleteByDroneIdAndTimestampBefore(eq(droneId), any(Instant.class));
        }
    }
}
