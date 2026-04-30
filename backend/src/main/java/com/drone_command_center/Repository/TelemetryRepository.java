package com.drone_command_center.Repository;

import com.drone_command_center.Entity.Telemetry;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface TelemetryRepository extends JpaRepository<Telemetry, UUID> {

    Page<Telemetry> findByDroneId(UUID droneId, Pageable pageable);

    List<Telemetry> findByDroneIdAndTimestampAfter(UUID droneId, Instant since);

    List<Telemetry> findByDroneIdAndTimestampBetween(UUID droneId, Instant start, Instant end);

    Optional<Telemetry> findFirstByDroneIdOrderByTimestampDesc(UUID droneId);

    @Query("SELECT t FROM Telemetry t WHERE t.drone.id = :droneId ORDER BY t.timestamp DESC")
    List<Telemetry> findLatestByDroneId(@Param("droneId") UUID droneId, Pageable pageable);

    long countByDroneId(UUID droneId);

    void deleteByDroneIdAndTimestampBefore(UUID droneId, Instant before);
}

