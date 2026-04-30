package com.drone_command_center.Repository;

import com.drone_command_center.Entity.Waypoint;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.UUID;

@Repository
public interface WaypointRepository extends JpaRepository<Waypoint, UUID> {
    
    List<Waypoint> findByMissionIdOrderBySequenceOrderAsc(UUID missionId);
    
    void deleteByMissionId(UUID missionId);
}
