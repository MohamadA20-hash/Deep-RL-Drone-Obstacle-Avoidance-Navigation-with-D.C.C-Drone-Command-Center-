package com.drone_command_center.websocket;

import com.drone_command_center.DTO.response.DroneDTO;
import com.drone_command_center.DTO.response.TelemetryDTO;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.ConcurrentWebSocketSessionDecorator;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import java.io.IOException;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArraySet;

/**
 * WebSocket handler for real-time telemetry updates.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class TelemetryWebSocketHandler extends TextWebSocketHandler {

    private final ObjectMapper objectMapper;

    // All connected sessions
    private final Set<WebSocketSession> sessions = new CopyOnWriteArraySet<>();
    
    // Sessions subscribed to specific drones
    private final Map<UUID, Set<WebSocketSession>> droneSubscriptions = new ConcurrentHashMap<>();

    @Override
    public void afterConnectionEstablished(WebSocketSession session) throws Exception {
        // Wrap with ConcurrentWebSocketSessionDecorator to serialize concurrent sends from
        // multiple HTTP worker threads. The underlying Tomcat WsRemoteEndpoint is NOT thread-safe;
        // without this wrapper, concurrent broadcastTelemetry() calls produce
        // IllegalStateException: TEXT_PARTIAL_WRITING.
        // 10s send-time limit, 512 KB buffer.
        WebSocketSession safeSession = new ConcurrentWebSocketSessionDecorator(session, 10_000, 512 * 1024);
        sessions.add(safeSession);
        log.info("WebSocket connection established: {}", safeSession.getId());

        // Send welcome message
        sendMessage(safeSession, new WebSocketMessage("connected", "Connected to telemetry stream", null));
    }

    @Override
    protected void handleTextMessage(WebSocketSession rawSession, TextMessage message) throws Exception {
        WebSocketSession session = resolveSession(rawSession);
        try {
            WebSocketCommand command = objectMapper.readValue(message.getPayload(), WebSocketCommand.class);
            
            switch (command.getAction()) {
                case "subscribe":
                    if (command.getDroneId() != null) {
                        subscribeToDrone(session, command.getDroneId());
                    } else {
                        // Subscribe to all drones
                        log.info("Session {} subscribed to all drones", session.getId());
                    }
                    break;
                    
                case "unsubscribe":
                    if (command.getDroneId() != null) {
                        unsubscribeFromDrone(session, command.getDroneId());
                    }
                    break;
                    
                case "ping":
                    sendMessage(session, new WebSocketMessage("pong", null, null));
                    break;
                    
                default:
                    log.warn("Unknown WebSocket command: {}", command.getAction());
            }
        } catch (Exception e) {
            log.error("Error handling WebSocket message: {}", e.getMessage());
            sendMessage(session, new WebSocketMessage("error", e.getMessage(), null));
        }
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) throws Exception {
        // Spring invokes callbacks with the original (undecorated) session, so match by id.
        removeSessionById(session.getId());
        log.info("WebSocket connection closed: {} - {}", session.getId(), status);
    }

    @Override
    public void handleTransportError(WebSocketSession session, Throwable exception) throws Exception {
        log.error("WebSocket transport error for session {}: {}", session.getId(), exception.getMessage());
        removeSessionById(session.getId());
    }

    private void removeSessionById(String id) {
        sessions.removeIf(s -> id.equals(s.getId()));
        droneSubscriptions.values().forEach(subscribers -> subscribers.removeIf(s -> id.equals(s.getId())));
    }

    /**
     * Subscribe a session to a specific drone's telemetry.
     */
    private void subscribeToDrone(WebSocketSession session, UUID droneId) {
        // Use the decorated session (thread-safe) instead of the raw one passed to handleTextMessage.
        WebSocketSession safe = resolveSession(session);
        droneSubscriptions.computeIfAbsent(droneId, k -> new CopyOnWriteArraySet<>()).add(safe);
        log.info("Session {} subscribed to drone {}", safe.getId(), droneId);
        sendMessage(safe, new WebSocketMessage("subscribed", "Subscribed to drone " + droneId, droneId));
    }

    /**
     * Returns the ConcurrentWebSocketSessionDecorator we registered in afterConnectionEstablished
     * for the given raw session id. Falls back to the raw session if not found.
     */
    private WebSocketSession resolveSession(WebSocketSession raw) {
        String id = raw.getId();
        for (WebSocketSession s : sessions) {
            if (id.equals(s.getId())) {
                return s;
            }
        }
        return raw;
    }

    /**
     * Unsubscribe a session from a specific drone's telemetry.
     */
    private void unsubscribeFromDrone(WebSocketSession session, UUID droneId) {
        Set<WebSocketSession> subscribers = droneSubscriptions.get(droneId);
        if (subscribers != null) {
            subscribers.remove(session);
            log.info("Session {} unsubscribed from drone {}", session.getId(), droneId);
        }
        sendMessage(session, new WebSocketMessage("unsubscribed", "Unsubscribed from drone " + droneId, droneId));
    }

    /**
     * Broadcast telemetry update to all sessions subscribed to a drone.
     */
    public void broadcastTelemetry(UUID droneId, TelemetryDTO telemetry) {
        WebSocketMessage message = new WebSocketMessage("telemetry", null, telemetry);
        
        // Send to subscribers of this specific drone
        Set<WebSocketSession> subscribers = droneSubscriptions.get(droneId);
        if (subscribers != null) {
            subscribers.forEach(session -> sendMessage(session, message));
        }
        
        // Also send to sessions not subscribed to specific drones (broadcast subscribers)
        sessions.stream()
                .filter(session -> !isSubscribedToAnyDrone(session))
                .forEach(session -> sendMessage(session, message));
    }

    /**
     * Broadcast drone status update to all connected sessions.
     */
    public void broadcastDroneStatus(DroneDTO drone) {
        WebSocketMessage message = new WebSocketMessage("droneStatus", null, drone);
        sessions.forEach(session -> sendMessage(session, message));
    }

    /**
     * Broadcast a command to all sessions subscribed to a drone.
     * This allows the Python bridge to receive STOP/PAUSE/RESUME etc. in real-time.
     */
    public void broadcastCommand(UUID droneId, String commandType, Object payload) {
        Map<String, Object> data = new java.util.HashMap<>();
        data.put("commandType", commandType);
        data.put("droneId", droneId.toString());
        if (payload != null) data.put("payload", payload);
        WebSocketMessage message = new WebSocketMessage("command", null, data);

        // Send to subscribers of this specific drone
        Set<WebSocketSession> subscribers = droneSubscriptions.get(droneId);
        if (subscribers != null) {
            subscribers.forEach(session -> sendMessage(session, message));
        }
        // Also send to broadcast (non-subscribed) sessions
        sessions.stream()
                .filter(session -> !isSubscribedToAnyDrone(session))
                .forEach(session -> sendMessage(session, message));
        log.info("Broadcast command {} for drone {} to {} sessions", commandType, droneId, sessions.size());
    }

    /**
     * Broadcast alert to all connected sessions.
     */
    public void broadcastAlert(String alertType, String alertMessage, Object data) {
        WebSocketMessage message = new WebSocketMessage(alertType, alertMessage, data);
        sessions.forEach(session -> sendMessage(session, message));
    }

    private boolean isSubscribedToAnyDrone(WebSocketSession session) {
        return droneSubscriptions.values().stream()
                .anyMatch(subscribers -> subscribers.contains(session));
    }

    private void sendMessage(WebSocketSession session, WebSocketMessage message) {
        if (!session.isOpen()) {
            return;
        }
        try {
            String json = objectMapper.writeValueAsString(message);
            session.sendMessage(new TextMessage(json));
        } catch (IOException e) {
            log.warn("WebSocket send IO error for session {}: {} (dropping session)", session.getId(), e.getMessage());
            removeSessionById(session.getId());
        } catch (IllegalStateException e) {
            // Buffer overflow or session in unexpected state - drop to avoid log spam.
            log.warn("WebSocket send state error for session {}: {} (dropping session)", session.getId(), e.getMessage());
            removeSessionById(session.getId());
        }
    }

    /**
     * Get the number of connected sessions.
     */
    public int getConnectedSessionsCount() {
        return sessions.size();
    }

    // Inner classes for WebSocket messages
    public record WebSocketMessage(String type, String message, Object data) {}
    
    public static class WebSocketCommand {
        private String action;
        private UUID droneId;

        public String getAction() { return action; }
        public void setAction(String action) { this.action = action; }
        public UUID getDroneId() { return droneId; }
        public void setDroneId(UUID droneId) { this.droneId = droneId; }
    }
}
