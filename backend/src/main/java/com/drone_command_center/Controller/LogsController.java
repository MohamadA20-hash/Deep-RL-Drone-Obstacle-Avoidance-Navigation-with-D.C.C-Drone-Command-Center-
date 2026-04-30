package com.drone_command_center.Controller;

import com.drone_command_center.DTO.response.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.*;
import java.util.regex.Pattern;

/**
 * Read-only access to the rolling backend log file.
 *
 * Used by the dashboard "Logs" page to surface real-time backend activity to
 * operators without forcing them onto the host machine.
 *
 * Endpoint: GET /api/logs/recent?limit=200&level=ERROR&q=bridge
 *   limit  - max number of lines to return (1..2000), default 200
 *   level  - optional level filter (TRACE|DEBUG|INFO|WARN|ERROR)
 *   q      - optional case-insensitive substring filter
 *
 * The file is tail-read (last ~2MB scanned) so the response stays cheap even
 * for multi-GB rolling logs.
 */
@RestController
@RequestMapping("/api/logs")
@Tag(name = "Logs", description = "Read-only backend log access")
@SecurityRequirement(name = "bearerAuth")
public class LogsController {

    private static final Pattern LINE_HEAD = Pattern.compile(
            "^(\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}\\.\\d{3})\\s+(TRACE|DEBUG|INFO|WARN|ERROR)\\s+\\[([^\\]]*)\\]\\s+([^\\s]+)\\s+-\\s+(.*)$");

    /** Max bytes we'll tail-scan per request. */
    private static final long MAX_TAIL_BYTES = 2L * 1024 * 1024;

    @Value("${app.logs.path:logs/drone-command-center.log}")
    private String logFilePath;

    @GetMapping("/recent")
    @Operation(summary = "Tail the backend log file with optional filters")
    public ResponseEntity<ApiResponse<Map<String, Object>>> recent(
            @RequestParam(defaultValue = "200") int limit,
            @RequestParam(required = false) String level,
            @RequestParam(required = false) String q) {

        int cap = Math.max(1, Math.min(2000, limit));
        String levelFilter = (level == null || level.isBlank()) ? null : level.trim().toUpperCase(Locale.ROOT);
        String textFilter = (q == null || q.isBlank()) ? null : q.toLowerCase(Locale.ROOT);

        List<Map<String, Object>> entries = new ArrayList<>();
        Path path = resolvePath();
        boolean fileExists = path != null && Files.exists(path);

        if (fileExists) {
            try {
                List<String> lines = tailLines(path, cap * 4); // overscan for filtering
                List<Map<String, Object>> parsed = new ArrayList<>(lines.size());
                Map<String, Object> current = null;
                StringBuilder stack = null;

                for (String line : lines) {
                    var m = LINE_HEAD.matcher(line);
                    if (m.matches()) {
                        if (current != null) {
                            if (stack != null && stack.length() > 0) {
                                current.put("stack", stack.toString());
                            }
                            parsed.add(current);
                        }
                        current = new LinkedHashMap<>();
                        current.put("ts", m.group(1));
                        current.put("level", m.group(2));
                        current.put("thread", m.group(3));
                        current.put("logger", m.group(4));
                        current.put("message", m.group(5));
                        stack = null;
                    } else if (current != null) {
                        if (stack == null) stack = new StringBuilder();
                        if (stack.length() > 0) stack.append('\n');
                        stack.append(line);
                    }
                }
                if (current != null) {
                    if (stack != null && stack.length() > 0) {
                        current.put("stack", stack.toString());
                    }
                    parsed.add(current);
                }

                // Filter newest-first then cap to limit.
                for (int i = parsed.size() - 1; i >= 0 && entries.size() < cap; i--) {
                    Map<String, Object> e = parsed.get(i);
                    if (levelFilter != null && !levelFilter.equals(e.get("level"))) continue;
                    if (textFilter != null) {
                        String haystack = (String.valueOf(e.get("message")) + " "
                                + String.valueOf(e.getOrDefault("logger", "")) + " "
                                + String.valueOf(e.getOrDefault("stack", ""))).toLowerCase(Locale.ROOT);
                        if (!haystack.contains(textFilter)) continue;
                    }
                    entries.add(e);
                }
            } catch (IOException ignored) {
                // fall through with empty entries
            }
        }

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("path", path == null ? logFilePath : path.toAbsolutePath().toString());
        body.put("exists", fileExists);
        body.put("count", entries.size());
        body.put("limit", cap);
        body.put("level", levelFilter);
        body.put("q", q);
        body.put("entries", entries);
        return ResponseEntity.ok(ApiResponse.success(body));
    }

    private Path resolvePath() {
        if (logFilePath == null || logFilePath.isBlank()) return null;
        Path p = Paths.get(logFilePath);
        if (p.isAbsolute()) return p;
        // Resolve against working directory (Spring Boot's CWD when launched).
        return Paths.get(System.getProperty("user.dir")).resolve(p).normalize();
    }

    /** Read up to ~MAX_TAIL_BYTES from the end of the file and split into lines. */
    private List<String> tailLines(Path file, int approxLineCount) throws IOException {
        long size = Files.size(file);
        long readFrom = Math.max(0, size - MAX_TAIL_BYTES);
        try (RandomAccessFile raf = new RandomAccessFile(file.toFile(), "r")) {
            raf.seek(readFrom);
            byte[] buf = new byte[(int) (size - readFrom)];
            raf.readFully(buf);
            String text = new String(buf, StandardCharsets.UTF_8);
            // Drop the partial first line if we didn't start at byte 0.
            int firstNl = text.indexOf('\n');
            if (readFrom > 0 && firstNl >= 0) {
                text = text.substring(firstNl + 1);
            }
            String[] split = text.split("\\r?\\n", -1);
            List<String> out = new ArrayList<>(split.length);
            for (String s : split) {
                if (!s.isEmpty()) out.add(s);
            }
            // Keep only the last N lines (cheap if approxLineCount < total).
            if (out.size() > approxLineCount) {
                return new ArrayList<>(out.subList(out.size() - approxLineCount, out.size()));
            }
            return out;
        }
    }
}
