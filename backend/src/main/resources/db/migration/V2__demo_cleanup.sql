-- V2__demo_cleanup.sql
-- Demo-day cleanup: drop unused tables (roles, user-drone assignments, password reset tokens)
-- and clear stale telemetry / commands so the demo starts fresh.

DROP TABLE IF EXISTS user_roles CASCADE;
DROP TABLE IF EXISTS user_drone_assignments CASCADE;
DROP TABLE IF EXISTS password_reset_tokens CASCADE;

-- Clear stale runtime data so the demo starts from a clean slate.
TRUNCATE TABLE telemetry, commands RESTART IDENTITY CASCADE;
