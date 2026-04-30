package com.drone_command_center.Service;

import com.drone_command_center.DTO.event.CommandEvent;
import com.drone_command_center.DTO.event.DroneEvent;
import com.drone_command_center.DTO.event.MissionEvent;
import com.drone_command_center.DTO.event.TelemetryAlertEvent;
import com.drone_command_center.config.RabbitMQConfig;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;

@Slf4j
@Service
@RequiredArgsConstructor
@ConditionalOnProperty(name = "app.rabbitmq.enabled", havingValue = "true")
public class EventConsumer {

    private final EmailService emailService;

    @RabbitListener(queues = RabbitMQConfig.DRONE_STATUS_QUEUE)
    public void handleDroneEvent(DroneEvent event) {
        log.info("Received drone event [{}]: drone={}, status={}",
                event.getEventType(), event.getSerialNumber(), event.getStatus());

        switch (event.getEventType()) {
            case "REGISTERED" -> log.info("New drone registered: {} ({})", event.getDroneName(), event.getSerialNumber());
            case "STATUS_CHANGED" -> log.info("Drone {} status: {} -> {}", event.getSerialNumber(), event.getPreviousStatus(), event.getStatus());
            case "DELETED" -> log.info("Drone deleted: {}", event.getSerialNumber());
        }
    }

    @RabbitListener(queues = RabbitMQConfig.MISSION_EVENTS_QUEUE)
    public void handleMissionEvent(MissionEvent event) {
        log.info("Received mission event [{}]: mission={}, status={}",
                event.getEventType(), event.getMissionName(), event.getStatus());

        if ("COMPLETED".equals(event.getEventType())) {
            log.info("Mission completed: {}", event.getMissionName());
        }
    }

    @RabbitListener(queues = RabbitMQConfig.COMMAND_EVENTS_QUEUE)
    public void handleCommandEvent(CommandEvent event) {
        log.info("Received command event [{}]: command={}, type={}, drone={}",
                event.getEventType(), event.getCommandId(), event.getCommandType(), event.getDroneId());
    }

    @RabbitListener(queues = RabbitMQConfig.TELEMETRY_ALERTS_QUEUE)
    public void handleTelemetryAlert(TelemetryAlertEvent event) {
        log.warn("Telemetry alert [{}]: drone={}, message={}, value={}",
                event.getAlertType(), event.getDroneName(), event.getMessage(), event.getValue());
    }
}
