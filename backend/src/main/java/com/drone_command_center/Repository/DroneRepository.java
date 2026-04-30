package com.drone_command_center.Repository;

import com.drone_command_center.Entity.Drone;
import com.drone_command_center.Entity.enums.ConnectionStatus;
import com.drone_command_center.Entity.enums.FlightStatus;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface DroneRepository extends JpaRepository<Drone, UUID> {

    Optional<Drone> findBySerialNumber(String serialNumber);

    boolean existsBySerialNumber(String serialNumber);

    List<Drone> findByConnectionStatus(ConnectionStatus status);

    List<Drone> findByFlightStatus(FlightStatus status);

    long countByConnectionStatus(ConnectionStatus status);

    long countByFlightStatus(FlightStatus status);

    List<Drone> findByBatteryLevelLessThan(double level);
}
