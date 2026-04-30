package com.drone_command_center.Repository;


import com.drone_command_center.Entity.Command;
import com.drone_command_center.Entity.enums.CommandStatus;
import com.drone_command_center.Entity.enums.CommandType;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Repository
public interface CommandRepository extends JpaRepository<Command, UUID> {

    List<Command> findByDroneIdAndStatus(UUID droneId, CommandStatus status);

    Page<Command> findByDroneId(UUID droneId, Pageable pageable);

    Page<Command> findByIssuedById(UUID userId, Pageable pageable);

    Page<Command> findByMissionId(UUID missionId, Pageable pageable);

    List<Command> findByDroneIdAndCreatedAtBetween(UUID droneId, Instant start, Instant end);

    long countByDroneIdAndStatus(UUID droneId, CommandStatus status);

    long countByStatus(CommandStatus status);

    List<Command> findByStatus(CommandStatus status);

    List<Command> findByCommandTypeAndStatus(CommandType type, CommandStatus status);
}
