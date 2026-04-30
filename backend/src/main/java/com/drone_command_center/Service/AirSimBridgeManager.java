package com.drone_command_center.Service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import lombok.Getter;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.io.*;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Manages the AirSim Python auto-bridge as a subprocess.
 * <p>
 * On backend startup, automatically launches airsim_auto_bridge.py which:
 * - Polls for AirSim availability
 * - Auto-connects when AirSim is detected
 * - Streams telemetry to the backend
 * - Auto-reconnects on failure
 * <p>
 * The bridge process communicates status via JSON lines on stdout.
 */
@Slf4j
@Service
public class AirSimBridgeManager {

    private final ObjectMapper objectMapper;

    @Value("${app.airsim.bridge.auto-start:true}")
    private boolean autoStart;

    @Value("${app.airsim.bridge.python-path:#{null}}")
    private String configuredPythonPath;

    @Value("${app.airsim.bridge.script-path:#{null}}")
    private String configuredScriptPath;

    @Value("${app.airsim.bridge.auth-user:navrl_bridge}")
    private String bridgeAuthUser;

    @Value("${app.airsim.bridge.auth-pass:NavRL@2026!}")
    private String bridgeAuthPass;

    private Process bridgeProcess;
    private Thread stdoutReader;
    private Thread stderrReader;
    private volatile boolean stopping = false;

    @Getter
    private final AtomicReference<BridgeStatus> currentStatus =
            new AtomicReference<>(new BridgeStatus("stopped", null, Instant.now(), 0));

    public AirSimBridgeManager(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @PostConstruct
    public void init() {
        if (autoStart) {
            log.info("AirSim bridge auto-start enabled, launching...");
            start();
        } else {
            log.info("AirSim bridge auto-start disabled");
        }
    }

    @PreDestroy
    public void destroy() {
        stop();
    }

    /**
     * Watchdog: every 10 seconds, if auto-start is enabled and the bridge
     * process is not alive (and we're not in the middle of a graceful stop),
     * relaunch it. This guarantees recovery when:
     *   - the initial start at boot failed (e.g. AirSim/Python not yet ready)
     *   - the user manually stopped the bridge but later wants it back
     *   - the python process exits before the monitor thread re-spawns it
     */
    @Scheduled(fixedDelay = 10_000L, initialDelay = 15_000L)
    public void respawnIfNeeded() {
        if (!autoStart || stopping) return;
        if (bridgeProcess != null && bridgeProcess.isAlive()) return;
        log.info("Bridge watchdog: process not alive, relaunching...");
        start();
    }

    /**
     * Start the bridge subprocess.
     */
    public synchronized boolean start() {
        if (bridgeProcess != null && bridgeProcess.isAlive()) {
            log.info("Bridge process already running (PID {})", bridgeProcess.pid());
            return true;
        }

        stopping = false;
        String pythonPath = resolvePythonPath();
        String scriptPath = resolveScriptPath();

        if (pythonPath == null) {
            log.error("Python executable not found. Set app.airsim.bridge.python-path");
            updateStatus("error", "Python not found");
            return false;
        }

        if (scriptPath == null || !Files.exists(Paths.get(scriptPath))) {
            log.error("Bridge script not found at: {}", scriptPath);
            updateStatus("error", "Bridge script not found");
            return false;
        }

        try {
            ProcessBuilder pb = new ProcessBuilder(pythonPath, scriptPath);
            pb.redirectErrorStream(false);

            // Pass config via environment
            Map<String, String> env = pb.environment();
            env.put("BRIDGE_BACKEND_URL", "http://localhost:8080/api");
            env.put("BRIDGE_WS_URL", "ws://localhost:8080/ws/telemetry");
            env.put("BRIDGE_AUTH_USER", bridgeAuthUser);
            env.put("BRIDGE_AUTH_PASS", bridgeAuthPass);
            env.put("PYTHONUNBUFFERED", "1");
            env.put("PYTHONIOENCODING", "utf-8");

            bridgeProcess = pb.start();
            long pid = bridgeProcess.pid();
            log.info("Bridge process started (PID {})", pid);
            updateStatus("starting", "PID " + pid);

            // Read stdout (JSON status lines)
            stdoutReader = new Thread(() -> readStdout(bridgeProcess.getInputStream()),
                    "bridge-stdout");
            stdoutReader.setDaemon(true);
            stdoutReader.start();

            // Read stderr (Python logging)
            stderrReader = new Thread(() -> readStderr(bridgeProcess.getErrorStream()),
                    "bridge-stderr");
            stderrReader.setDaemon(true);
            stderrReader.start();

            // Monitor process exit
            Thread monitor = new Thread(() -> monitorProcess(), "bridge-monitor");
            monitor.setDaemon(true);
            monitor.start();

            return true;
        } catch (IOException e) {
            log.error("Failed to start bridge process", e);
            updateStatus("error", e.getMessage());
            return false;
        }
    }

    /**
     * Stop the bridge subprocess gracefully.
     */
    public synchronized void stop() {
        stopping = true;
        if (bridgeProcess != null && bridgeProcess.isAlive()) {
            log.info("Stopping bridge process (PID {})...", bridgeProcess.pid());

            // Send shutdown command via stdin
            try {
                OutputStream os = bridgeProcess.getOutputStream();
                os.write("shutdown\n".getBytes());
                os.flush();
            } catch (IOException e) {
                log.debug("Could not write shutdown to stdin: {}", e.getMessage());
            }

            // Wait briefly for graceful shutdown
            try {
                boolean exited = bridgeProcess.waitFor(
                        5, java.util.concurrent.TimeUnit.SECONDS);
                if (!exited) {
                    log.warn("Bridge did not exit gracefully, force-killing...");
                    bridgeProcess.destroyForcibly();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                bridgeProcess.destroyForcibly();
            }

            log.info("Bridge process stopped");
        }
        bridgeProcess = null;
        updateStatus("stopped", null);
    }

    /**
     * Restart the bridge.
     */
    public void restart() {
        stop();
        // Brief pause to let port/resources release
        try { Thread.sleep(1000); } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        start();
    }

    /**
     * Get current status as a map for the REST endpoint.
     */
    public Map<String, Object> getStatusMap() {
        BridgeStatus s = currentStatus.get();
        Map<String, Object> map = new java.util.HashMap<>();
        map.put("status", s.status());
        map.put("message", s.message());
        map.put("since", s.since().toString());
        map.put("telemetryCount", s.telemetryCount());
        map.put("processAlive", bridgeProcess != null && bridgeProcess.isAlive());
        if (bridgeProcess != null && bridgeProcess.isAlive()) {
            map.put("pid", bridgeProcess.pid());
        }
        return map;
    }

    public boolean isRunning() {
        return bridgeProcess != null && bridgeProcess.isAlive();
    }

    // ── Internal ────────────────────────────────────────────

    private void readStdout(InputStream is) {
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(is))) {
            String line;
            while ((line = reader.readLine()) != null) {
                parseStatusLine(line);
            }
        } catch (IOException e) {
            if (!stopping) {
                log.debug("Stdout reader ended: {}", e.getMessage());
            }
        }
    }

    private void readStderr(InputStream is) {
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(is))) {
            String line;
            while ((line = reader.readLine()) != null) {
                // Forward Python logging to Java logging
                if (line.contains("[WARNING]") || line.contains("[WARN]")) {
                    log.warn("[bridge] {}", line);
                } else if (line.contains("[ERROR]")) {
                    log.error("[bridge] {}", line);
                } else {
                    log.info("[bridge] {}", line);
                }
            }
        } catch (IOException e) {
            if (!stopping) {
                log.debug("Stderr reader ended: {}", e.getMessage());
            }
        }
    }

    private void parseStatusLine(String line) {
        try {
            JsonNode node = objectMapper.readTree(line);
            String status = node.path("status").asText("unknown");
            int count = node.path("count").asInt(currentStatus.get().telemetryCount());
            String message = node.has("message") ? node.get("message").asText()
                    : node.has("reason") ? node.get("reason").asText()
                    : null;

            updateStatus(status, message, count);

            switch (status) {
                case "connected" -> log.info("Bridge: AirSim connected");
                case "streaming" -> log.debug("Bridge: streaming ({} packets)", count);
                case "waiting_airsim" -> log.info("Bridge: waiting for AirSim...");
                case "waiting_backend" -> log.info("Bridge: waiting for backend...");
                case "reconnecting" -> log.warn("Bridge: reconnecting ({})", message);
                case "error" -> log.error("Bridge error: {}", message);
                case "shutdown" -> log.info("Bridge: clean shutdown");
            }
        } catch (Exception e) {
            // Not a JSON line — might be plain Python output
            log.debug("[bridge-stdout] {}", line);
        }
    }

    private void monitorProcess() {
        try {
            int exitCode = bridgeProcess.waitFor();
            if (!stopping) {
                log.warn("Bridge process exited unexpectedly (code {}), restarting...",
                        exitCode);
                updateStatus("restarting", "Exit code " + exitCode);
                Thread.sleep(3000);
                if (!stopping) {
                    start();
                }
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private void updateStatus(String status, String message) {
        updateStatus(status, message, currentStatus.get().telemetryCount());
    }

    private void updateStatus(String status, String message, int telemetryCount) {
        currentStatus.set(new BridgeStatus(status, message, Instant.now(), telemetryCount));
    }

    private String resolvePythonPath() {
        if (configuredPythonPath != null && !configuredPythonPath.isBlank()) {
            return configuredPythonPath;
        }

        // Auto-detect common Python locations on Windows
        String[] candidates = {
                System.getenv("PYTHON_PATH"),
                "C:\\Users\\" + System.getProperty("user.name")
                        + "\\AppData\\Local\\Programs\\Python\\Python311\\python.exe",
                "C:\\Users\\" + System.getProperty("user.name")
                        + "\\AppData\\Local\\Programs\\Python\\Python312\\python.exe",
                "C:\\Users\\" + System.getProperty("user.name")
                        + "\\AppData\\Local\\Programs\\Python\\Python310\\python.exe",
                "python",
                "python3",
        };

        for (String candidate : candidates) {
            if (candidate == null) continue;
            try {
                Path p = Paths.get(candidate);
                if (Files.exists(p)) {
                    return candidate;
                }
            } catch (Exception ignored) {
                // "python" / "python3" won't be valid paths — try running them
                try {
                    Process test = new ProcessBuilder(candidate, "--version")
                            .redirectErrorStream(true).start();
                    if (test.waitFor(3, java.util.concurrent.TimeUnit.SECONDS)
                            && test.exitValue() == 0) {
                        return candidate;
                    }
                } catch (Exception ignored2) {
                    // continue
                }
            }
        }
        return null;
    }

    private String resolveScriptPath() {
        if (configuredScriptPath != null && !configuredScriptPath.isBlank()) {
            return configuredScriptPath;
        }

        // Auto-detect: look for the script relative to common project locations
        String userHome = System.getProperty("user.home");
        String[] candidates = {
                userHome + "\\Desktop\\Projects\\NavRL-main\\capstone\\airsim_testing\\airsim_auto_bridge.py",
                "..\\..\\NavRL-main\\capstone\\airsim_testing\\airsim_auto_bridge.py",
                ".\\airsim_auto_bridge.py",
        };

        for (String candidate : candidates) {
            Path p = Paths.get(candidate);
            if (Files.exists(p)) {
                return p.toAbsolutePath().toString();
            }
        }
        return candidates[0]; // Return default path even if not found (error will be logged)
    }

    // ── Status record ───────────────────────────────────────
    public record BridgeStatus(String status, String message, Instant since, int telemetryCount) {}
}
