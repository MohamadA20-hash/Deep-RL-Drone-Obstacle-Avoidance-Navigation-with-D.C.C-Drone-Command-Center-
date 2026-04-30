package com.drone_command_center.Service;

import com.drone_command_center.DTO.request.MissionCreateRequest;
import com.drone_command_center.DTO.request.WaypointCreateRequest;
import com.drone_command_center.DTO.response.MissionDTO;
import com.drone_command_center.Entity.Drone;
import com.drone_command_center.Entity.Mission;
import com.drone_command_center.Entity.User;
import com.drone_command_center.Entity.Waypoint;
import com.drone_command_center.Entity.enums.*;
import com.drone_command_center.Repository.DroneRepository;
import com.drone_command_center.Repository.MissionRepository;
import com.drone_command_center.Repository.UserRepository;
import com.drone_command_center.Repository.WaypointRepository;
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
import java.util.*;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
@DisplayName("MissionService Tests")
class MissionServiceTest {

    @Mock
    private MissionRepository missionRepository;
    @Mock
    private DroneRepository droneRepository;
    @Mock
    private UserRepository userRepository;
    @Mock
    private WaypointRepository waypointRepository;
    @Mock
    private Optional<EventPublisher> eventPublisher;

    @InjectMocks
    private MissionService missionService;

    private User testUser;
    private Drone testDrone;
    private Mission testMission;
    private UUID userId;
    private UUID droneId;
    private UUID missionId;

    @BeforeEach
    void setUp() {
        userId = UUID.randomUUID();
        droneId = UUID.randomUUID();
        missionId = UUID.randomUUID();

        testUser = User.builder()
                .id(userId)
                .username("operator1")
                .email("operator@test.com")
                .enabled(true)
                .build();

        testDrone = Drone.builder()
                .id(droneId)
                .serialNumber("DJI-001")
                .name("Scout Alpha")
                .modelType("DJI Matrice 300")
                .connectionStatus(ConnectionStatus.ONLINE)
                .flightStatus(FlightStatus.IDLE)
                .batteryLevel(85.0)
                .build();

        testMission = Mission.builder()
                .id(missionId)
                .name("Survey Mission")
                .description("Area survey")
                .missionType(MissionType.PATROL)
                .status(MissionStatus.CREATED)
                .createdBy(testUser)
                .assignedDrone(testDrone)
                .createdAt(Instant.now())
                .waypoints(new ArrayList<>())
                .build();
    }

    @Nested
    @DisplayName("Create Mission Tests")
    class CreateMissionTests {

        @Test
        @DisplayName("Should create mission successfully without waypoints")
        void shouldCreateMissionSuccessfully() {
            MissionCreateRequest request = MissionCreateRequest.builder()
                    .name("Survey Mission")
                    .description("Area survey")
                    .missionType(MissionType.PATROL)
                    .estimatedDurationMinutes(30)
                    .build();

            when(userRepository.findById(userId)).thenReturn(Optional.of(testUser));
            when(missionRepository.save(any(Mission.class))).thenReturn(testMission);

            MissionDTO result = missionService.createMission(request, userId);

            assertThat(result).isNotNull();
            assertThat(result.getName()).isEqualTo("Survey Mission");
            assertThat(result.getStatus()).isEqualTo(MissionStatus.CREATED);
            verify(missionRepository).save(any(Mission.class));
        }

        @Test
        @DisplayName("Should create mission with drone assignment")
        void shouldCreateMissionWithDrone() {
            MissionCreateRequest request = MissionCreateRequest.builder()
                    .name("Patrol Mission")
                    .missionType(MissionType.PATROL)
                    .assignedDroneId(droneId)
                    .build();

            when(userRepository.findById(userId)).thenReturn(Optional.of(testUser));
            when(droneRepository.findById(droneId)).thenReturn(Optional.of(testDrone));
            when(missionRepository.save(any(Mission.class))).thenReturn(testMission);

            MissionDTO result = missionService.createMission(request, userId);

            assertThat(result).isNotNull();
            verify(droneRepository).findById(droneId);
        }

        @Test
        @DisplayName("Should create mission with waypoints")
        void shouldCreateMissionWithWaypoints() {
            WaypointCreateRequest wp = WaypointCreateRequest.builder()
                    .sequenceOrder(1)
                    .latitude(37.7749)
                    .longitude(-122.4194)
                    .altitude(50.0)
                    .speed(5.0)
                    .build();

            MissionCreateRequest request = MissionCreateRequest.builder()
                    .name("Delivery Mission")
                    .missionType(MissionType.DELIVERY)
                    .waypoints(List.of(wp))
                    .build();

            when(userRepository.findById(userId)).thenReturn(Optional.of(testUser));
            when(missionRepository.save(any(Mission.class))).thenReturn(testMission);
            when(waypointRepository.save(any(Waypoint.class))).thenAnswer(inv -> inv.getArgument(0));

            MissionDTO result = missionService.createMission(request, userId);

            assertThat(result).isNotNull();
            verify(waypointRepository).save(any(Waypoint.class));
        }

        @Test
        @DisplayName("Should throw when user not found")
        void shouldThrowWhenUserNotFound() {
            MissionCreateRequest request = MissionCreateRequest.builder()
                    .name("Test")
                    .missionType(MissionType.PATROL)
                    .build();

            when(userRepository.findById(userId)).thenReturn(Optional.empty());

            assertThatThrownBy(() -> missionService.createMission(request, userId))
                    .isInstanceOf(ResourceNotFoundException.class);
        }
    }

    @Nested
    @DisplayName("Start Mission Tests")
    class StartMissionTests {

        @Test
        @DisplayName("Should start a created mission")
        void shouldStartCreatedMission() {
            Waypoint wp = Waypoint.builder().id(UUID.randomUUID()).sequenceOrder(1)
                    .latitude(37.7749).longitude(-122.4194).altitude(100.0).build();
            testMission.setWaypoints(List.of(wp));
            testMission.setStatus(MissionStatus.CREATED);

            when(missionRepository.findById(missionId)).thenReturn(Optional.of(testMission));
            when(missionRepository.save(any(Mission.class))).thenReturn(testMission);

            MissionDTO result = missionService.startMission(missionId);

            assertThat(result).isNotNull();
            assertThat(testMission.getStatus()).isEqualTo(MissionStatus.ACTIVE);
            assertThat(testMission.getStartedAt()).isNotNull();
        }

        @Test
        @DisplayName("Should throw when mission already active")
        void shouldThrowWhenAlreadyActive() {
            testMission.setStatus(MissionStatus.ACTIVE);
            when(missionRepository.findById(missionId)).thenReturn(Optional.of(testMission));

            assertThatThrownBy(() -> missionService.startMission(missionId))
                    .isInstanceOf(InvalidOperationException.class)
                    .hasMessageContaining("cannot be started");
        }

        @Test
        @DisplayName("Should throw when no drone assigned")
        void shouldThrowWhenNoDroneAssigned() {
            testMission.setAssignedDrone(null);
            when(missionRepository.findById(missionId)).thenReturn(Optional.of(testMission));

            assertThatThrownBy(() -> missionService.startMission(missionId))
                    .isInstanceOf(InvalidOperationException.class)
                    .hasMessageContaining("No drone assigned");
        }

        @Test
        @DisplayName("Should throw when drone is offline")
        void shouldThrowWhenDroneOffline() {
            testDrone.setConnectionStatus(ConnectionStatus.OFFLINE);
            when(missionRepository.findById(missionId)).thenReturn(Optional.of(testMission));

            assertThatThrownBy(() -> missionService.startMission(missionId))
                    .isInstanceOf(InvalidOperationException.class)
                    .hasMessageContaining("not connected");
        }

        @Test
        @DisplayName("Should throw when no waypoints defined")
        void shouldThrowWhenNoWaypoints() {
            testMission.setWaypoints(new ArrayList<>());
            when(missionRepository.findById(missionId)).thenReturn(Optional.of(testMission));

            assertThatThrownBy(() -> missionService.startMission(missionId))
                    .isInstanceOf(InvalidOperationException.class)
                    .hasMessageContaining("No waypoints");
        }
    }

    @Nested
    @DisplayName("Mission Lifecycle Tests")
    class MissionLifecycleTests {

        @Test
        @DisplayName("Should pause active mission")
        void shouldPauseActiveMission() {
            testMission.setStatus(MissionStatus.ACTIVE);
            when(missionRepository.findById(missionId)).thenReturn(Optional.of(testMission));
            when(missionRepository.save(any(Mission.class))).thenReturn(testMission);

            MissionDTO result = missionService.pauseMission(missionId);

            assertThat(testMission.getStatus()).isEqualTo(MissionStatus.PAUSED);
        }

        @Test
        @DisplayName("Should resume paused mission")
        void shouldResumePausedMission() {
            testMission.setStatus(MissionStatus.PAUSED);
            when(missionRepository.findById(missionId)).thenReturn(Optional.of(testMission));
            when(missionRepository.save(any(Mission.class))).thenReturn(testMission);

            MissionDTO result = missionService.resumeMission(missionId);

            assertThat(testMission.getStatus()).isEqualTo(MissionStatus.ACTIVE);
        }

        @Test
        @DisplayName("Should throw when pausing non-active mission")
        void shouldThrowWhenPausingNonActiveMission() {
            testMission.setStatus(MissionStatus.CREATED);
            when(missionRepository.findById(missionId)).thenReturn(Optional.of(testMission));

            assertThatThrownBy(() -> missionService.pauseMission(missionId))
                    .isInstanceOf(InvalidOperationException.class);
        }

        @Test
        @DisplayName("Should complete mission successfully")
        void shouldCompleteMissionSuccessfully() {
            testMission.setStatus(MissionStatus.ACTIVE);
            when(missionRepository.findById(missionId)).thenReturn(Optional.of(testMission));
            when(missionRepository.save(any(Mission.class))).thenReturn(testMission);

            MissionDTO result = missionService.completeMission(missionId, true);

            assertThat(testMission.getStatus()).isEqualTo(MissionStatus.COMPLETED);
            assertThat(testMission.getCompletedAt()).isNotNull();
        }

        @Test
        @DisplayName("Should mark mission as failed")
        void shouldMarkMissionAsFailed() {
            testMission.setStatus(MissionStatus.ACTIVE);
            when(missionRepository.findById(missionId)).thenReturn(Optional.of(testMission));
            when(missionRepository.save(any(Mission.class))).thenReturn(testMission);

            MissionDTO result = missionService.completeMission(missionId, false);

            assertThat(testMission.getStatus()).isEqualTo(MissionStatus.FAILED);
        }

        @Test
        @DisplayName("Should abort mission")
        void shouldAbortMission() {
            testMission.setStatus(MissionStatus.ACTIVE);
            when(missionRepository.findById(missionId)).thenReturn(Optional.of(testMission));
            when(missionRepository.save(any(Mission.class))).thenReturn(testMission);

            MissionDTO result = missionService.abortMission(missionId);

            assertThat(testMission.getStatus()).isEqualTo(MissionStatus.ABORTED);
            assertThat(testMission.getCompletedAt()).isNotNull();
        }

        @Test
        @DisplayName("Should throw when aborting completed mission")
        void shouldThrowWhenAbortingCompletedMission() {
            testMission.setStatus(MissionStatus.COMPLETED);
            when(missionRepository.findById(missionId)).thenReturn(Optional.of(testMission));

            assertThatThrownBy(() -> missionService.abortMission(missionId))
                    .isInstanceOf(InvalidOperationException.class);
        }
    }

    @Nested
    @DisplayName("Delete Mission Tests")
    class DeleteMissionTests {

        @Test
        @DisplayName("Should delete created mission")
        void shouldDeleteCreatedMission() {
            testMission.setStatus(MissionStatus.CREATED);
            when(missionRepository.findById(missionId)).thenReturn(Optional.of(testMission));

            missionService.deleteMission(missionId);

            verify(missionRepository).delete(testMission);
        }

        @Test
        @DisplayName("Should throw when deleting active mission")
        void shouldThrowWhenDeletingActiveMission() {
            testMission.setStatus(MissionStatus.ACTIVE);
            when(missionRepository.findById(missionId)).thenReturn(Optional.of(testMission));

            assertThatThrownBy(() -> missionService.deleteMission(missionId))
                    .isInstanceOf(InvalidOperationException.class)
                    .hasMessageContaining("Cannot delete active mission");
        }
    }

    @Nested
    @DisplayName("Waypoint Management Tests")
    class WaypointTests {

        @Test
        @DisplayName("Should add waypoint to created mission")
        void shouldAddWaypoint() {
            testMission.setStatus(MissionStatus.CREATED);
            testMission.setWaypoints(new ArrayList<>());
            WaypointCreateRequest request = WaypointCreateRequest.builder()
                    .sequenceOrder(1)
                    .latitude(37.0)
                    .longitude(-122.0)
                    .altitude(50.0)
                    .build();

            when(missionRepository.findById(missionId)).thenReturn(Optional.of(testMission));
            when(waypointRepository.save(any(Waypoint.class))).thenAnswer(inv -> inv.getArgument(0));

            MissionDTO result = missionService.addWaypoint(missionId, request);

            assertThat(result).isNotNull();
            verify(waypointRepository).save(any(Waypoint.class));
        }

        @Test
        @DisplayName("Should throw when adding waypoint to started mission")
        void shouldThrowWhenAddingToStartedMission() {
            testMission.setStatus(MissionStatus.ACTIVE);
            WaypointCreateRequest request = WaypointCreateRequest.builder()
                    .sequenceOrder(1)
                    .latitude(37.0)
                    .longitude(-122.0)
                    .altitude(50.0)
                    .build();

            when(missionRepository.findById(missionId)).thenReturn(Optional.of(testMission));

            assertThatThrownBy(() -> missionService.addWaypoint(missionId, request))
                    .isInstanceOf(InvalidOperationException.class);
        }
    }

    @Nested
    @DisplayName("Statistics Tests")
    class StatisticsTests {

        @Test
        @DisplayName("Should return mission statistics")
        void shouldReturnStatistics() {
            when(missionRepository.count()).thenReturn(10L);
            when(missionRepository.countByStatus(MissionStatus.CREATED)).thenReturn(2L);
            when(missionRepository.countByStatus(MissionStatus.ACTIVE)).thenReturn(3L);
            when(missionRepository.countByStatus(MissionStatus.COMPLETED)).thenReturn(4L);
            when(missionRepository.countByStatus(MissionStatus.FAILED)).thenReturn(1L);

            MissionService.MissionStatistics stats = missionService.getMissionStatistics();

            assertThat(stats.getTotalMissions()).isEqualTo(10);
            assertThat(stats.getActiveMissions()).isEqualTo(3);
            assertThat(stats.getCompletedMissions()).isEqualTo(4);
        }
    }
}
