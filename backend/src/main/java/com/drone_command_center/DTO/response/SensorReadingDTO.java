package com.drone_command_center.DTO.response;

import com.drone_command_center.Entity.enums.SensorType;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

/**
 * Snapshot of a single sensor's metadata together with its latest reading,
 * derived from the drone's most recent {@code Telemetry} row.
 *
 * <p>The {@code reading} map is sensor-type specific:
 * <ul>
 *   <li><b>GPS</b> → {@code latitude, longitude, altitude, fix}</li>
 *   <li><b>IMU</b> → {@code yaw, pitch, roll, accelMagnitude}</li>
 *   <li><b>LIDAR</b> → {@code closestObstacleM, mappedCells, obstacleDetected}</li>
 *   <li><b>CAMERA</b> → {@code streamStatus, resolution, fps}</li>
 * </ul>
 *
 * <p>{@code online=false} when no telemetry has been received from the drone
 * (so the UI can render a clear "no signal" state instead of stale data).
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class SensorReadingDTO {

    private UUID id;
    private SensorType type;
    private String model;
    private double rangeMeters;
    private double frequencyHz;
    private boolean enabled;

    /** {@code true} when the sensor's source telemetry stream is live. */
    private boolean online;

    /** Wall-clock of the telemetry row this reading was derived from. */
    private Instant readingAt;

    /** Sensor-type specific key/value reading. Order is preserved for the UI. */
    @Builder.Default
    private Map<String, Object> reading = new LinkedHashMap<>();
}
