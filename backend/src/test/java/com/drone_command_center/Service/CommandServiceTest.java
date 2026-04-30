package com.drone_command_center.Service;

import com.drone_command_center.DTO.request.CommandCreateRequest;
import com.drone_command_center.DTO.response.CommandDTO;
import com.drone_command_center.Entity.Command;
import com.drone_command_center.Entity.Drone;
import com.drone_command_center.Entity.User;
import com.drone_command_center.Entity.enums.*;
import com.drone_command_center.Repository.CommandRepository;
import com.drone_command_center.Repository.DroneRepository;
import com.drone_command_center.Repository.MissionRepository;
import com.drone_command_center.Repository.UserRepository;
import com.drone_command_center.exception.InvalidOperationException;
import com.drone_command_center.exception.ResourceNotFoundException;
import com.drone_command_center.websocket.TelemetryWebSocketHandler;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Instant;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
@DisplayName("CommandService Tests")
class CommandServiceTest {

    @Mock
    private CommandRepository commandRepository;
    @Mock
    private DroneRepository droneRepository;
    @Mock
    private UserRepository userRepository;
    @Mock
    private MissionRepository missionRepository;
    @Mock
    private Optional<EventPublisher> eventPublisher;
    @Mock
    private TelemetryWebSocketHandler webSocketHandler;

    @InjectMocks
    private CommandService commandService;

    private Drone testDrone;
    private User testUser;
    private UUID droneId;
    private UUID userId;
    private UUID commandId;

    @BeforeEach
    void setUp() {
        droneId = UUID.randomUUID();
        userId = UUID.randomUUID();
        commandId = UUID.randomUUID();

        testDrone = Drone.builder()
                .id(droneId)
                .serialNumber("DJI-001")
                .name("Scout")
                .modelType("DJI M300")
                .connectionStatus(ConnectionStatus.ONLINE)
                .flightStatus(FlightStatus.IDLE)
                .batteryLevel(85.0)
                .navigationMode(NavigationMode.MANUAL)
                .build();

        testUser = User.builder()
                .id(userId)
                .username("pilot1")
                .email("pilot@test.com")
                .enabled(true)
                .build();
    }

    private Command buildCommand(CommandType type, CommandStatus status) {
        return Command.builder()
                .id(commandId)
                .drone(testDrone)
                .issuedBy(testUser)
                .commandType(type)
                .status(status)
                .createdAt(Instant.now())
                .build();
    }

    @Nested
    @DisplayName("Send Command Tests")
    class SendCommandTests {

        @Test
        @DisplayName("Should send TAKEOFF command to idle drone")
        void shouldSendTakeoffCommand() {
            CommandCreateRequest request = CommandCreateRequest.builder()
                    .droneId(droneId)
                    .commandType(CommandType.TAKEOFF)
                    .parameters("{\"altitude\": 50}")
                    .build();

            Command savedCommand = buildCommand(CommandType.TAKEOFF, CommandStatus.PENDING);

            when(droneRepository.findById(droneId)).thenReturn(Optional.of(testDrone));
            when(userRepository.findById(userId)).thenReturn(Optional.of(testUser));
            when(commandRepository.save(any(Command.class))).thenReturn(savedCommand);

            CommandDTO result = commandService.sendCommand(request, userId);

            assertThat(result).isNotNull();
            assertThat(result.getCommandType()).isEqualTo(CommandType.TAKEOFF);
            assertThat(result.getStatus()).isEqualTo(CommandStatus.PENDING);
            assertThat(testDrone.getFlightStatus()).isEqualTo(FlightStatus.IN_FLIGHT);
            verify(droneRepository).save(testDrone);
        }

        @Test
        @DisplayName("Should still send command when drone is offline in simulation mode")
        void shouldAllowOfflineDroneCommandsInSimulationMode() {
            testDrone.setConnectionStatus(ConnectionStatus.OFFLINE);
            CommandCreateRequest request = CommandCreateRequest.builder()
                    .droneId(droneId)
                    .commandType(CommandType.TAKEOFF)
                    .build();

            Command savedCommand = buildCommand(CommandType.TAKEOFF, CommandStatus.PENDING);

            when(droneRepository.findById(droneId)).thenReturn(Optional.of(testDrone));
            when(userRepository.findById(userId)).thenReturn(Optional.of(testUser));
            when(commandRepository.save(any(Command.class))).thenReturn(savedCommand);

            CommandDTO result = commandService.sendCommand(request, userId);

            assertThat(result).isNotNull();
            assertThat(result.getCommandType()).isEqualTo(CommandType.TAKEOFF);
            verify(webSocketHandler).broadcastCommand(droneId, CommandType.TAKEOFF.name(), null);
        }

        @Test
        @DisplayName("Should throw when drone not found")
        void shouldThrowWhenDroneNotFound() {
            CommandCreateRequest request = CommandCreateRequest.builder()
                    .droneId(droneId)
                    .commandType(CommandType.TAKEOFF)
                    .build();

            when(droneRepository.findById(droneId)).thenReturn(Optional.empty());

            assertThatThrownBy(() -> commandService.sendCommand(request, userId))
                    .isInstanceOf(ResourceNotFoundException.class);
        }

        @Test
        @DisplayName("Should reject TAKEOFF when drone is already in flight")
        void shouldRejectTakeoffWhenInFlight() {
            testDrone.setFlightStatus(FlightStatus.IN_FLIGHT);
            CommandCreateRequest request = CommandCreateRequest.builder()
                    .droneId(droneId)
                    .commandType(CommandType.TAKEOFF)
                    .build();

            when(droneRepository.findById(droneId)).thenReturn(Optional.of(testDrone));
            when(userRepository.findById(userId)).thenReturn(Optional.of(testUser));

            assertThatThrownBy(() -> commandService.sendCommand(request, userId))
                    .isInstanceOf(InvalidOperationException.class)
                    .hasMessageContaining("Cannot takeoff");
        }

        @Test
        @DisplayName("Should reject TAKEOFF when battery is low")
        void shouldRejectTakeoffWithLowBattery() {
            testDrone.setBatteryLevel(10.0);
            CommandCreateRequest request = CommandCreateRequest.builder()
                    .droneId(droneId)
                    .commandType(CommandType.TAKEOFF)
                    .build();

            when(droneRepository.findById(droneId)).thenReturn(Optional.of(testDrone));
            when(userRepository.findById(userId)).thenReturn(Optional.of(testUser));

            assertThatThrownBy(() -> commandService.sendCommand(request, userId))
                    .isInstanceOf(InvalidOperationException.class)
                    .hasMessageContaining("Battery level too low");
        }

        @Test
        @DisplayName("Should send LAND command to in-flight drone")
        void shouldSendLandCommand() {
            testDrone.setFlightStatus(FlightStatus.IN_FLIGHT);
            CommandCreateRequest request = CommandCreateRequest.builder()
                    .droneId(droneId)
                    .commandType(CommandType.LAND)
                    .build();

            Command savedCommand = buildCommand(CommandType.LAND, CommandStatus.PENDING);

            when(droneRepository.findById(droneId)).thenReturn(Optional.of(testDrone));
            when(userRepository.findById(userId)).thenReturn(Optional.of(testUser));
            when(commandRepository.save(any(Command.class))).thenReturn(savedCommand);

            CommandDTO result = commandService.sendCommand(request, userId);

            assertThat(result.getCommandType()).isEqualTo(CommandType.LAND);
            assertThat(testDrone.getFlightStatus()).isEqualTo(FlightStatus.LANDING);
        }

        @Test
        @DisplayName("Should always allow EMERGENCY_STOP")
        void shouldAlwaysAllowEmergencyStop() {
            testDrone.setFlightStatus(FlightStatus.IN_FLIGHT);
            CommandCreateRequest request = CommandCreateRequest.builder()
                    .droneId(droneId)
                    .commandType(CommandType.EMERGENCY_STOP)
                    .build();

            Command savedCommand = buildCommand(CommandType.EMERGENCY_STOP, CommandStatus.PENDING);

            when(droneRepository.findById(droneId)).thenReturn(Optional.of(testDrone));
            when(userRepository.findById(userId)).thenReturn(Optional.of(testUser));
            when(commandRepository.save(any(Command.class))).thenReturn(savedCommand);

            CommandDTO result = commandService.sendCommand(request, userId);

            assertThat(result.getCommandType()).isEqualTo(CommandType.EMERGENCY_STOP);
            assertThat(testDrone.getFlightStatus()).isEqualTo(FlightStatus.EMERGENCY);
        }
    }

    @Nested
    @DisplayName("Command Acknowledgement Tests")
    class AcknowledgementTests {

        @Test
        @DisplayName("Should acknowledge command successfully")
        void shouldAcknowledgeCommand() {
            Command command = buildCommand(CommandType.TAKEOFF, CommandStatus.SENT);
            when(commandRepository.findById(commandId)).thenReturn(Optional.of(command));
            when(commandRepository.save(any(Command.class))).thenReturn(command);

            CommandDTO result = commandService.acknowledgeCommand(commandId, true);

            assertThat(command.getStatus()).isEqualTo(CommandStatus.ACKNOWLEDGED);
            assertThat(command.getExecutedAt()).isNotNull();
        }

        @Test
        @DisplayName("Should mark command as failed")
        void shouldMarkCommandFailed() {
            Command command = buildCommand(CommandType.TAKEOFF, CommandStatus.SENT);
            when(commandRepository.findById(commandId)).thenReturn(Optional.of(command));
            when(commandRepository.save(any(Command.class))).thenReturn(command);

            commandService.acknowledgeCommand(commandId, false);

            assertThat(command.getStatus()).isEqualTo(CommandStatus.FAILED);
        }

        @Test
        @DisplayName("Should mark pending command as sent")
        void shouldMarkAsSent() {
            Command command = buildCommand(CommandType.TAKEOFF, CommandStatus.PENDING);
            when(commandRepository.findById(commandId)).thenReturn(Optional.of(command));
            when(commandRepository.save(any(Command.class))).thenReturn(command);

            commandService.markCommandAsSent(commandId);

            assertThat(command.getStatus()).isEqualTo(CommandStatus.SENT);
        }

        @Test
        @DisplayName("Should throw when marking non-pending command as sent")
        void shouldThrowWhenMarkingNonPendingAsSent() {
            Command command = buildCommand(CommandType.TAKEOFF, CommandStatus.ACKNOWLEDGED);
            when(commandRepository.findById(commandId)).thenReturn(Optional.of(command));

            assertThatThrownBy(() -> commandService.markCommandAsSent(commandId))
                    .isInstanceOf(InvalidOperationException.class);
        }
    }

    @Nested
    @DisplayName("Cancel Command Tests")
    class CancelCommandTests {

        @Test
        @DisplayName("Should cancel pending command")
        void shouldCancelPendingCommand() {
            Command command = buildCommand(CommandType.TAKEOFF, CommandStatus.PENDING);
            when(commandRepository.findById(commandId)).thenReturn(Optional.of(command));

            commandService.cancelCommand(commandId);

            verify(commandRepository).delete(command);
        }

        @Test
        @DisplayName("Should throw when cancelling non-pending command")
        void shouldThrowWhenCancellingNonPending() {
            Command command = buildCommand(CommandType.TAKEOFF, CommandStatus.SENT);
            when(commandRepository.findById(commandId)).thenReturn(Optional.of(command));

            assertThatThrownBy(() -> commandService.cancelCommand(commandId))
                    .isInstanceOf(InvalidOperationException.class);
        }
    }

    @Nested
    @DisplayName("Statistics Tests")
    class StatisticsTests {

        @Test
        @DisplayName("Should return command statistics")
        void shouldReturnStatistics() {
            when(commandRepository.count()).thenReturn(20L);
            when(commandRepository.countByStatus(CommandStatus.PENDING)).thenReturn(5L);
            when(commandRepository.countByStatus(CommandStatus.SENT)).thenReturn(3L);
            when(commandRepository.countByStatus(CommandStatus.ACKNOWLEDGED)).thenReturn(10L);
            when(commandRepository.countByStatus(CommandStatus.FAILED)).thenReturn(2L);

            CommandService.CommandStatistics stats = commandService.getCommandStatistics();

            assertThat(stats.getTotalCommands()).isEqualTo(20);
            assertThat(stats.getPendingCommands()).isEqualTo(5);
            assertThat(stats.getAcknowledgedCommands()).isEqualTo(10);
        }
    }
}
