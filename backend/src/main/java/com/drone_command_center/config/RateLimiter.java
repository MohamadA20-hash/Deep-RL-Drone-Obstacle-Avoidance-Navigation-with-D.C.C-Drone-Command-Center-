package com.drone_command_center.config;

import io.github.bucket4j.Bandwidth;
import io.github.bucket4j.Bucket;
import io.github.bucket4j.Refill;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Rate limiter for protecting against brute force attacks.
 * Uses Bucket4j token bucket algorithm.
 */
@Slf4j
@Component
public class RateLimiter {

    // Store rate limit buckets per IP address
    private final Map<String, Bucket> buckets = new ConcurrentHashMap<>();
    
    // Store login attempt counts per username
    private final Map<String, Integer> loginAttempts = new ConcurrentHashMap<>();
    
    // Max failed login attempts before lockout
    private static final int MAX_LOGIN_ATTEMPTS = 5;
    
    // Lockout duration in minutes
    private static final int LOCKOUT_DURATION_MINUTES = 15;
    
    // Store lockout timestamps
    private final Map<String, Long> lockoutTimestamps = new ConcurrentHashMap<>();

    /**
     * Get or create a rate limit bucket for an IP address.
     * Allows 10 requests per minute for login attempts.
     */
    public Bucket resolveBucket(String ipAddress) {
        return buckets.computeIfAbsent(ipAddress, this::createNewBucket);
    }

    private Bucket createNewBucket(String key) {
        // 10 tokens, refill 10 tokens per minute
        Bandwidth limit = Bandwidth.classic(10, Refill.greedy(10, Duration.ofMinutes(1)));
        return Bucket.builder()
                .addLimit(limit)
                .build();
    }

    /**
     * Check if the request is allowed based on rate limiting.
     */
    public boolean tryConsume(String ipAddress) {
        Bucket bucket = resolveBucket(ipAddress);
        return bucket.tryConsume(1);
    }

    /**
     * Record a failed login attempt for a username.
     */
    public void recordFailedLogin(String username) {
        int attempts = loginAttempts.merge(username, 1, Integer::sum);
        log.warn("Failed login attempt {} for user: {}", attempts, username);
        
        if (attempts >= MAX_LOGIN_ATTEMPTS) {
            lockoutTimestamps.put(username, System.currentTimeMillis());
            log.warn("User {} has been locked out due to {} failed login attempts", username, attempts);
        }
    }

    /**
     * Clear failed login attempts after successful login.
     */
    public void clearFailedAttempts(String username) {
        loginAttempts.remove(username);
        lockoutTimestamps.remove(username);
    }

    /**
     * Check if a user is currently locked out.
     */
    public boolean isLockedOut(String username) {
        Long lockoutTime = lockoutTimestamps.get(username);
        if (lockoutTime == null) {
            return false;
        }
        
        long elapsedMinutes = (System.currentTimeMillis() - lockoutTime) / (1000 * 60);
        if (elapsedMinutes >= LOCKOUT_DURATION_MINUTES) {
            // Lockout has expired, clear it
            clearFailedAttempts(username);
            return false;
        }
        
        return true;
    }

    /**
     * Get remaining lockout time in minutes.
     */
    public long getRemainingLockoutMinutes(String username) {
        Long lockoutTime = lockoutTimestamps.get(username);
        if (lockoutTime == null) {
            return 0;
        }
        
        long elapsedMinutes = (System.currentTimeMillis() - lockoutTime) / (1000 * 60);
        return Math.max(0, LOCKOUT_DURATION_MINUTES - elapsedMinutes);
    }

    /**
     * Get remaining failed login attempts before lockout.
     */
    public int getRemainingAttempts(String username) {
        int attempts = loginAttempts.getOrDefault(username, 0);
        return Math.max(0, MAX_LOGIN_ATTEMPTS - attempts);
    }
}
