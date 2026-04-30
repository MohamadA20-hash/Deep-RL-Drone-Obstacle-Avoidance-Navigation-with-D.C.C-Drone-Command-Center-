package com.drone_command_center.Repository;

import com.drone_command_center.Entity.Sensor;
import com.drone_command_center.Entity.Drone;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface SensorRepository extends JpaRepository<Sensor, UUID> {

    List<Sensor> findByDrone(Drone drone);
}

