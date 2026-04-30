package com.drone_command_center.Service;

import com.drone_command_center.DTO.request.DroneCreateRequest;
import com.drone_command_center.DTO.request.DroneUpdateRequest;
import com.drone_command_center.DTO.response.DroneDTO;
import com.drone_command_center.Entity.Drone;
import com.drone_command_center.Entity.enums.AutonomyLevel;
import com.drone_command_center.Entity.enums.ConnectionStatus;
import com.drone_command_center.Entity.enums.FlightStatus;
import com.drone_command_center.Entity.enums.NavigationMode;
import com.drone_command_center.Repository.DroneRepository;
import com.drone_command_center.Repository.UserRepository;
import com.drone_command_center.exception.DuplicateResourceException;
import com.drone_command_center.exception.InvalidOperationException;
import com.drone_command_center.exception.ResourceNotFoundException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
@DisplayName("DroneService Tests")
class DroneServiceTest {

    @Mock
    private DroneRepository droneRepository;

    @Mock
    private UserRepository userRepository;

    private DroneService droneService;

    private Drone testDrone;
    private DroneCreateRequest createRequest;
    private UUID droneId;

    @BeforeEach
    void setUp() {
        droneService = new DroneService(droneRepository, userRepository, Optional.empty());
        droneId = UUID.randomUUID();
        
        testDrone = Drone.builder()
                .id(droneId)
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
                .registeredAt(Instant.now())
                .build();

        createRequest = DroneCreateRequest.builder()
                .serialNumber("DJI-M300-001")
                .name("Alpha Scout")
                .modelType("DJI Matrice 300 RTK")
                .firmwareVersion("v2.5.1")
                .autonomyLevel(AutonomyLevel.MANUAL)
                .navigationMode(NavigationMode.MANUAL)
                .failsafeEnabled(true)
                .homeLatitude(37.7749)
                .homeLongitude(-122.4194)
                .homeAltitude(10.0)
                .build();
    }

    @Nested
    @DisplayName("Register Drone Tests")
    class RegisterDroneTests {

        @Test
        @DisplayName("Should register drone successfully")
        void shouldRegisterDroneSuccessfully() {
            // Given
            when(droneRepository.existsBySerialNumber(anyString())).thenReturn(false);
            when(droneRepository.save(any(Drone.class))).thenReturn(testDrone);

            // When
            DroneDTO result = droneService.registerDrone(createRequest);

            // Then
            assertThat(result).isNotNull();
            assertThat(result.getSerialNumber()).isEqualTo(createRequest.getSerialNumber());
            assertThat(result.getName()).isEqualTo(createRequest.getName());
            assertThat(result.getModelType()).isEqualTo(createRequest.getModelType());
            verify(droneRepository, times(1)).save(any(Drone.class));
        }

        @Test
        @DisplayName("Should throw exception when serial number already exists")
        void shouldThrowExceptionWhenSerialNumberExists() {
            // Given
            when(droneRepository.existsBySerialNumber(anyString())).thenReturn(true);

            // When/Then
            assertThatThrownBy(() -> droneService.registerDrone(createRequest))
                    .isInstanceOf(DuplicateResourceException.class)
                    .hasMessageContaining("serialNumber");

            verify(droneRepository, never()).save(any(Drone.class));
        }

        @Test
        @DisplayName("Should set default values when not provided")
        void shouldSetDefaultValuesWhenNotProvided() {
            // Given
            DroneCreateRequest minimalRequest = DroneCreateRequest.builder()
                    .serialNumber("TEST-001")
                    .name("Test Drone")
                    .modelType("Test Model")
                    .build();

            when(droneRepository.existsBySerialNumber(anyString())).thenReturn(false);
            when(droneRepository.save(any(Drone.class))).thenAnswer(invocation -> {
                Drone saved = invocation.getArgument(0);
                saved.setId(UUID.randomUUID());
                return saved;
            });

            // When
            DroneDTO result = droneService.registerDrone(minimalRequest);

            // Then
            assertThat(result).isNotNull();
            assertThat(result.getConnectionStatus()).isEqualTo(ConnectionStatus.OFFLINE);
            assertThat(result.getFlightStatus()).isEqualTo(FlightStatus.IDLE);
            assertThat(result.getAutonomyLevel()).isEqualTo(AutonomyLevel.MANUAL);
            assertThat(result.getBatteryLevel()).isEqualTo(100.0);
        }
    }

    @Nested
    @DisplayName("Get Drone Tests")
    class GetDroneTests {

        @Test
        @DisplayName("Should get drone by ID")
        void shouldGetDroneById() {
            // Given
            when(droneRepository.findById(droneId)).thenReturn(Optional.of(testDrone));

            // When
            DroneDTO result = droneService.getDroneById(droneId);

            // Then
            assertThat(result).isNotNull();
            assertThat(result.getId()).isEqualTo(droneId);
            assertThat(result.getSerialNumber()).isEqualTo(testDrone.getSerialNumber());
        }

        @Test
        @DisplayName("Should throw exception when drone not found")
        void shouldThrowExceptionWhenDroneNotFound() {
            // Given
            when(droneRepository.findById(droneId)).thenReturn(Optional.empty());

            // When/Then
            assertThatThrownBy(() -> droneService.getDroneById(droneId))
                    .isInstanceOf(ResourceNotFoundException.class);
        }

        @Test
        @DisplayName("Should get drones by connection status")
        void shouldGetDronesByConnectionStatus() {
            // Given
            when(droneRepository.findByConnectionStatus(ConnectionStatus.ONLINE))
                    .thenReturn(List.of(testDrone));

            // When
            List<DroneDTO> result = droneService.getDronesByConnectionStatus(ConnectionStatus.ONLINE);

            // Then
            assertThat(result).hasSize(1);
        }
    }

    @Nested
    @DisplayName("Update Drone Tests")
    class UpdateDroneTests {

        @Test
        @DisplayName("Should update drone successfully")
        void shouldUpdateDroneSuccessfully() {
            // Given
            DroneUpdateRequest updateRequest = DroneUpdateRequest.builder()
                    .name("Updated Name")
                    .firmwareVersion("v3.0.0")
                    .build();

            when(droneRepository.findById(droneId)).thenReturn(Optional.of(testDrone));
            when(droneRepository.save(any(Drone.class))).thenReturn(testDrone);

            // When
            DroneDTO result = droneService.updateDrone(droneId, updateRequest);

            // Then
            assertThat(result).isNotNull();
            verify(droneRepository, times(1)).save(testDrone);
        }

        @Test
        @DisplayName("Should only update non-null fields")
        void shouldOnlyUpdateNonNullFields() {
            // Given
            DroneUpdateRequest partialUpdate = DroneUpdateRequest.builder()
                    .name("New Name")
                    .build();

            String originalFirmware = testDrone.getFirmwareVersion();
            when(droneRepository.findById(droneId)).thenReturn(Optional.of(testDrone));
            when(droneRepository.save(any(Drone.class))).thenReturn(testDrone);

            // When
            droneService.updateDrone(droneId, partialUpdate);

            // Then
            assertThat(testDrone.getName()).isEqualTo("New Name");
            assertThat(testDrone.getFirmwareVersion()).isEqualTo(originalFirmware);
        }
    }

    @Nested
    @DisplayName("Delete Drone Tests")
    class DeleteDroneTests {

        @Test
        @DisplayName("Should delete drone successfully when idle")
        void shouldDeleteDroneWhenIdle() {
            // Given
            testDrone.setFlightStatus(FlightStatus.IDLE);
            when(droneRepository.findById(droneId)).thenReturn(Optional.of(testDrone));

            // When
            droneService.deleteDrone(droneId);

            // Then
            verify(droneRepository, times(1)).delete(testDrone);
        }

        @Test
        @DisplayName("Should throw exception when trying to delete drone in flight")
        void shouldThrowExceptionWhenDeletingDroneInFlight() {
            // Given
            testDrone.setFlightStatus(FlightStatus.IN_FLIGHT);
            when(droneRepository.findById(droneId)).thenReturn(Optional.of(testDrone));

            // When/Then
            assertThatThrownBy(() -> droneService.deleteDrone(droneId))
                    .isInstanceOf(InvalidOperationException.class)
                    .hasMessageContaining("in flight");

            verify(droneRepository, never()).delete(any(Drone.class));
        }
    }

    @Nested
    @DisplayName("Connection Status Tests")
    class ConnectionStatusTests {

        @Test
        @DisplayName("Should update connection status")
        void shouldUpdateConnectionStatus() {
            // Given
            when(droneRepository.findById(droneId)).thenReturn(Optional.of(testDrone));
            when(droneRepository.save(any(Drone.class))).thenReturn(testDrone);

            // When
            DroneDTO result = droneService.updateConnectionStatus(droneId, ConnectionStatus.ONLINE);

            // Then
            assertThat(result.getConnectionStatus()).isEqualTo(ConnectionStatus.ONLINE);
            assertThat(testDrone.getLastHeartbeat()).isNotNull();
        }

        @Test
        @DisplayName("Should check if drone is connected")
        void shouldCheckIfDroneIsConnected() {
            // Given
            testDrone.setConnectionStatus(ConnectionStatus.ONLINE);
            when(droneRepository.findById(droneId)).thenReturn(Optional.of(testDrone));

            // When
            boolean isConnected = droneService.isDroneConnected(droneId);

            // Then
            assertThat(isConnected).isTrue();
        }
    }
}
