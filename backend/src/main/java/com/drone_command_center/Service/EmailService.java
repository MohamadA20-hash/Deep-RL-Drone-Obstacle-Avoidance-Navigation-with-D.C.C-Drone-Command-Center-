package com.drone_command_center.Service;

import com.drone_command_center.Entity.Drone;
import com.drone_command_center.Entity.Mission;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

/**
 * Service for sending email notifications.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class EmailService {

    private final JavaMailSender mailSender;

    @Value("${app.email.from:noreply@dronecommandcenter.com}")
    private String fromAddress;

    @Value("${app.frontend.url:http://localhost:3000}")
    private String frontendUrl;

    @Value("${app.email.enabled:false}")
    private boolean emailEnabled;

    /**
     * Send password reset email.
     */
    @Async
    public void sendPasswordResetEmail(String toEmail, String token) {
        if (!emailEnabled) {
            log.info("Email disabled - Password reset token for {}: {}", toEmail, token);
            return;
        }

        try {
            SimpleMailMessage message = new SimpleMailMessage();
            message.setFrom(fromAddress);
            message.setTo(toEmail);
            message.setSubject("Drone Command Center - Password Reset");
            message.setText(String.format("""
                Hello,
                
                You have requested to reset your password for Drone Command Center.
                
                Click the link below to reset your password:
                %s/reset-password?token=%s
                
                This link will expire in 1 hour.
                
                If you did not request this password reset, please ignore this email.
                
                Best regards,
                Drone Command Center Team
                """, frontendUrl, token));

            mailSender.send(message);
            log.info("Password reset email sent to: {}", toEmail);
        } catch (Exception e) {
            log.error("Failed to send password reset email to {}: {}", toEmail, e.getMessage());
        }
    }

    /**
     * Send password changed confirmation email.
     */
    @Async
    public void sendPasswordChangedEmail(String toEmail) {
        if (!emailEnabled) {
            log.info("Email disabled - Password changed notification for {}", toEmail);
            return;
        }

        try {
            SimpleMailMessage message = new SimpleMailMessage();
            message.setFrom(fromAddress);
            message.setTo(toEmail);
            message.setSubject("Drone Command Center - Password Changed");
            message.setText("""
                Hello,
                
                Your password for Drone Command Center has been successfully changed.
                
                If you did not make this change, please contact support immediately.
                
                Best regards,
                Drone Command Center Team
                """);

            mailSender.send(message);
            log.info("Password changed email sent to: {}", toEmail);
        } catch (Exception e) {
            log.error("Failed to send password changed email to {}: {}", toEmail, e.getMessage());
        }
    }

    /**
     * Send low battery alert email.
     */
    @Async
    public void sendLowBatteryAlert(String toEmail, Drone drone) {
        if (!emailEnabled) {
            log.info("Email disabled - Low battery alert for drone {}", drone.getName());
            return;
        }

        try {
            SimpleMailMessage message = new SimpleMailMessage();
            message.setFrom(fromAddress);
            message.setTo(toEmail);
            message.setSubject("⚠️ Drone Command Center - Low Battery Alert");
            message.setText(String.format("""
                ALERT: Low Battery Warning
                
                Drone: %s
                Serial Number: %s
                Current Battery Level: %.1f%%
                
                Please take immediate action to avoid potential issues.
                
                Best regards,
                Drone Command Center Team
                """, drone.getName(), drone.getSerialNumber(), drone.getBatteryLevel()));

            mailSender.send(message);
            log.info("Low battery alert email sent to: {}", toEmail);
        } catch (Exception e) {
            log.error("Failed to send low battery alert to {}: {}", toEmail, e.getMessage());
        }
    }

    /**
     * Send mission completed notification.
     */
    @Async
    public void sendMissionCompletedEmail(String toEmail, Mission mission) {
        if (!emailEnabled) {
            log.info("Email disabled - Mission completed notification for mission {}", mission.getName());
            return;
        }

        try {
            SimpleMailMessage message = new SimpleMailMessage();
            message.setFrom(fromAddress);
            message.setTo(toEmail);
            message.setSubject("✅ Drone Command Center - Mission Completed");
            message.setText(String.format("""
                Mission Completed Successfully
                
                Mission Name: %s
                Description: %s
                Status: %s
                
                View mission details in the Drone Command Center dashboard.
                
                Best regards,
                Drone Command Center Team
                """, mission.getName(), 
                    mission.getDescription() != null ? mission.getDescription() : "N/A",
                    mission.getStatus().name()));

            mailSender.send(message);
            log.info("Mission completed email sent to: {}", toEmail);
        } catch (Exception e) {
            log.error("Failed to send mission completed email to {}: {}", toEmail, e.getMessage());
        }
    }

    /**
     * Send mission failed notification.
     */
    @Async
    public void sendMissionFailedEmail(String toEmail, Mission mission, String reason) {
        if (!emailEnabled) {
            log.info("Email disabled - Mission failed notification for mission {}", mission.getName());
            return;
        }

        try {
            SimpleMailMessage message = new SimpleMailMessage();
            message.setFrom(fromAddress);
            message.setTo(toEmail);
            message.setSubject("❌ Drone Command Center - Mission Failed");
            message.setText(String.format("""
                Mission Failed Alert
                
                Mission Name: %s
                Reason: %s
                
                Please review the mission logs for more details.
                
                Best regards,
                Drone Command Center Team
                """, mission.getName(), reason));

            mailSender.send(message);
            log.info("Mission failed email sent to: {}", toEmail);
        } catch (Exception e) {
            log.error("Failed to send mission failed email to {}: {}", toEmail, e.getMessage());
        }
    }
}
