package com.drone_command_center.Service;

import com.drone_command_center.DTO.response.SensorReadingDTO;
import com.drone_command_center.Entity.Drone;
import com.drone_command_center.Entity.Sensor;
import com.drone_command_center.Entity.Telemetry;
import com.drone_command_center.Entity.enums.ConnectionStatus;
import com.drone_command_center.Entity.enums.SensorType;
import com.drone_command_center.Repository.DroneRepository;
import com.drone_command_center.Repository.SensorRepository;
import com.drone_command_center.Repository.TelemetryRepository;
import com.drone_command_center.exception.ResourceNotFoundException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * Exposes a drone's sensor suite together with live readings derived from
 * the most recent {@link Telemetry} row. There is no random/synthetic data:
 * every reading maps to a field the AirSim/NavRL bridge actually publishes.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class SensorService {

    private final SensorRepository sensorRepository;
    private final DroneRepository droneRepository;
    private final TelemetryRepository telemetryRepository;

    @Transactional(readOnly = true)
    public List<SensorReadingDTO> getSensorsForDrone(UUID droneId) {
        Drone drone = droneRepository.findById(droneId)
                .orElseThrow(() -> new ResourceNotFoundException("Drone", "id", droneId));

        List<Sensor> sensors = sensorRepository.findByDrone(drone);
        Optional<Telemetry> latest = telemetryRepository.findFirstByDroneIdOrderByTimestampDesc(droneId);
        boolean droneOnline = drone.getConnectionStatus() == ConnectionStatus.ONLINE;

        return sensors.stream()
                .map(s -> toReadingDTO(s, latest.orElse(null), droneOnline))
                .collect(Collectors.toList());
    }

    private SensorReadingDTO toReadingDTO(Sensor sensor, Telemetry t, boolean droneOnline) {
        boolean hasLiveData = sensor.isEnabled() && t != null && droneOnline;

        return SensorReadingDTO.builder()
                .id(sensor.getId())
                .type(sensor.getType())
                .model(sensor.getModel())
                .rangeMeters(sensor.getRangeMeters())
                .frequencyHz(sensor.getFrequencyHz())
                .enabled(sensor.isEnabled())
                .online(hasLiveData)
                .readingAt(t != null ? t.getTimestamp() : null)
                .reading(buildReading(sensor.getType(), t, hasLiveData))
                .build();
    }

    private Map<String, Object> buildReading(SensorType type, Telemetry t, boolean live) {
        Map<String, Object> r = new LinkedHashMap<>();
        if (!live || t == null) {
            r.put("status", "NO_SIGNAL");
            return r;
        }
        switch (type) {
            case GPS -> {
                r.put("latitude", t.getLatitude());
                r.put("longitude", t.getLongitude());
                r.put("altitudeM", t.getAltitude());
                // Latitude=0 AND longitude=0 strongly implies AirSim hasn't published
                // a GPS fix yet — surface that to the operator instead of pretending.
                boolean hasFix = !(t.getLatitude() == 0.0 && t.getLongitude() == 0.0);
                r.put("fix", hasFix ? "3D_FIX" : "NO_FIX");
            }
            case IMU -> {
                r.put("yawDeg", t.getYaw());
                r.put("pitchDeg", t.getPitch());
                r.put("rollDeg", t.getRoll());
                double speed = Math.sqrt(
                        t.getVelocityX() * t.getVelocityX()
                                + t.getVelocityY() * t.getVelocityY()
                                + t.getVelocityZ() * t.getVelocityZ());
                r.put("speedMps", round(speed, 3));
            }
            case LIDAR -> {
                Double closest = t.getClosestObstacleDistance();
                if (closest == null || closest <= 0) closest = t.getObstacleDistance();
                r.put("closestObstacleM", closest);
                r.put("mappedCells", t.getMappedObstacleCells() != null ? t.getMappedObstacleCells() : 0);
                // The bridge sets Drone.obstacleDetected; for a fresh-from-telemetry
                // signal we re-derive it from the LIDAR distance threshold (5 m).
                r.put("obstacleDetected", closest != null && closest > 0 && closest < 5.0);
            }
            case CAMERA -> {
                // Camera doesn't have its own telemetry stream — its liveness mirrors
                // the bridge connection. Resolution/fps come from the sensor spec.
                r.put("streamStatus", "ONLINE");
                r.put("note", "FPV stream available via bridge");
            }
        }
        return r;
    }

    private static double round(double v, int decimals) {
        double scale = Math.pow(10, decimals);
        return Math.round(v * scale) / scale;
    }
}
