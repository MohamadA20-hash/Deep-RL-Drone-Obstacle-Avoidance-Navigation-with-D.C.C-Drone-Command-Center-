package com.drone_command_center.scheduler;

import com.drone_command_center.Entity.Drone;
import com.drone_command_center.Entity.enums.ConnectionStatus;
import com.drone_command_center.Repository.DroneRepository;
import com.drone_command_center.Repository.TelemetryRepository;
import com.drone_command_center.Service.RefreshTokenService;
import com.drone_command_center.websocket.TelemetryWebSocketHandler;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;

/**
 * Scheduled tasks for system maintenance and health checks.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class ScheduledTasks {

    private final DroneRepository droneRepository;
    private final TelemetryRepository telemetryRepository;
    private final RefreshTokenService refreshTokenService;
    private final TelemetryWebSocketHandler webSocketHandler;

    @Value("${app.scheduler.telemetry-retention-days:30}")
    private int telemetryRetentionDays;

    @Value("${app.scheduler.heartbeat-timeout-seconds:60}")
    private int heartbeatTimeoutSeconds;

    /**
     * Check drone connectivity every 30 seconds.
     * Mark drones as offline if no heartbeat received within timeout.
     */
    @Scheduled(fixedRate = 30000)
    @Transactional
    public void checkDroneConnectivity() {
        log.debug("Running drone connectivity check...");
        
        Instant timeout = Instant.now().minus(heartbeatTimeoutSeconds, ChronoUnit.SECONDS);
        List<Drone> onlineDrones = droneRepository.findByConnectionStatus(ConnectionStatus.ONLINE);
        
        int disconnectedCount = 0;
        for (Drone drone : onlineDrones) {
            if (drone.getLastHeartbeat() == null || drone.getLastHeartbeat().isBefore(timeout)) {
                drone.setConnectionStatus(ConnectionStatus.OFFLINE);
                droneRepository.save(drone);
                disconnectedCount++;
                
                log.warn("Drone {} marked as OFFLINE due to heartbeat timeout", drone.getSerialNumber());
                
                // Broadcast status change via WebSocket
                webSocketHandler.broadcastAlert("droneOffline", 
                        "Drone " + drone.getName() + " went offline", 
                        drone.getId());
            }
        }
        
        if (disconnectedCount > 0) {
            log.info("Marked {} drones as offline due to heartbeat timeout", disconnectedCount);
        }
    }

    /**
     * Check for low battery drones every 5 minutes.
     */
    @Scheduled(fixedRate = 300000)
    public void checkLowBatteryDrones() {
        log.debug("Running low battery check...");
        
        List<Drone> lowBatteryDrones = droneRepository.findByBatteryLevelLessThan(20.0);
        
        for (Drone drone : lowBatteryDrones) {
            if (drone.getConnectionStatus() == ConnectionStatus.ONLINE) {
                log.warn("Drone {} has low battery: {}%", drone.getSerialNumber(), drone.getBatteryLevel());
                
                webSocketHandler.broadcastAlert("lowBattery", 
                        String.format("Drone %s has low battery (%.1f%%)", drone.getName(), drone.getBatteryLevel()),
                        drone.getId());
            }
        }
    }

    /**
     * Cleanup old telemetry data daily at 2 AM.
     */
    @Scheduled(cron = "0 0 2 * * ?")
    @Transactional
    public void cleanupOldTelemetry() {
        log.info("Starting telemetry cleanup task...");

        Instant cutoffDate = Instant.now().minus(telemetryRetentionDays, ChronoUnit.DAYS);

        // Delete telemetry older than retention period for each drone
        List<Drone> drones = droneRepository.findAll();
        for (Drone drone : drones) {
            telemetryRepository.deleteByDroneIdAndTimestampBefore(drone.getId(), cutoffDate);
        }

        log.info("Telemetry cleanup task completed (retention: {} days)", telemetryRetentionDays);
    }

    /**
     * Cleanup expired tokens daily at 3 AM.
     */
    @Scheduled(cron = "0 0 3 * * ?")
    @Transactional
    public void cleanupExpiredTokens() {
        log.info("Starting token cleanup task...");
        
        refreshTokenService.deleteExpiredTokens();

        log.info("Token cleanup task completed");
    }

    /**
     * Log system statistics every hour.
     */
    @Scheduled(fixedRate = 3600000)
    public void logSystemStatistics() {
        long totalDrones = droneRepository.count();
        long onlineDrones = droneRepository.countByConnectionStatus(ConnectionStatus.ONLINE);
        int websocketConnections = webSocketHandler.getConnectedSessionsCount();
        
        log.info("System Statistics - Total Drones: {}, Online: {}, WebSocket Connections: {}",
                totalDrones, onlineDrones, websocketConnections);
    }
}
