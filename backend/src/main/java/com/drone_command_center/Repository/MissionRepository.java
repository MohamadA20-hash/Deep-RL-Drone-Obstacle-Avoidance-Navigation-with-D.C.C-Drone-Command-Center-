package com.drone_command_center.Repository;

import com.drone_command_center.Entity.Mission;
import com.drone_command_center.Entity.enums.MissionStatus;
import com.drone_command_center.Entity.enums.MissionType;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.UUID;

@Repository
public interface MissionRepository extends JpaRepository<Mission, UUID> {

    List<Mission> findByStatus(MissionStatus status);

    Page<Mission> findByStatus(MissionStatus status, Pageable pageable);

    Page<Mission> findByCreatedById(UUID userId, Pageable pageable);

    Page<Mission> findByAssignedDroneId(UUID droneId, Pageable pageable);

    List<Mission> findByAssignedDroneIdAndStatus(UUID droneId, MissionStatus status);

    List<Mission> findByMissionType(MissionType type);

    long countByStatus(MissionStatus status);

    boolean existsByAssignedDroneIdAndStatusIn(UUID droneId, List<MissionStatus> statuses);
}

