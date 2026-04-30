-- V1__Initial_schema.sql
-- Initial database schema for Drone Command Center

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- User roles table
CREATE TABLE IF NOT EXISTS user_roles (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL,
    PRIMARY KEY (user_id, role)
);

-- Drones table
CREATE TABLE IF NOT EXISTS drones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    serial_number VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    model_type VARCHAR(100) NOT NULL,
    firmware_version VARCHAR(50),
    connection_status VARCHAR(50) NOT NULL,
    flight_status VARCHAR(50) NOT NULL,
    battery_level DOUBLE PRECISION DEFAULT 100.0,
    latitude DOUBLE PRECISION DEFAULT 0.0,
    longitude DOUBLE PRECISION DEFAULT 0.0,
    altitude DOUBLE PRECISION DEFAULT 0.0,
    autonomy_level VARCHAR(50),
    navigation_mode VARCHAR(50),
    failsafe_enabled BOOLEAN DEFAULT true,
    obstacle_detected BOOLEAN DEFAULT false,
    last_heartbeat TIMESTAMP WITH TIME ZONE,
    registered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    home_latitude DOUBLE PRECISION,
    home_longitude DOUBLE PRECISION,
    home_altitude DOUBLE PRECISION
);

-- Missions table
CREATE TABLE IF NOT EXISTS missions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    description TEXT,
    status VARCHAR(50) NOT NULL,
    priority INTEGER DEFAULT 0,
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    estimated_duration_minutes INTEGER,
    actual_duration_minutes INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE,
    assigned_drone_id UUID REFERENCES drones(id),
    created_by_id UUID REFERENCES users(id)
);

-- Waypoints table
CREATE TABLE IF NOT EXISTS waypoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    altitude DOUBLE PRECISION NOT NULL,
    sequence_order INTEGER NOT NULL,
    action VARCHAR(50),
    hover_duration_seconds INTEGER DEFAULT 0,
    speed DOUBLE PRECISION,
    heading DOUBLE PRECISION,
    reached BOOLEAN DEFAULT false,
    reached_at TIMESTAMP WITH TIME ZONE,
    mission_id UUID NOT NULL REFERENCES missions(id) ON DELETE CASCADE
);

-- Commands table
CREATE TABLE IF NOT EXISTS commands (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    command_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    payload TEXT,
    response TEXT,
    issued_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    executed_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    drone_id UUID NOT NULL REFERENCES drones(id) ON DELETE CASCADE,
    issued_by_id UUID REFERENCES users(id)
);

-- Telemetry table
CREATE TABLE IF NOT EXISTS telemetry (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    altitude DOUBLE PRECISION,
    speed DOUBLE PRECISION,
    heading DOUBLE PRECISION,
    battery_level DOUBLE PRECISION,
    signal_strength DOUBLE PRECISION,
    gps_satellites INTEGER,
    temperature DOUBLE PRECISION,
    humidity DOUBLE PRECISION,
    wind_speed DOUBLE PRECISION,
    wind_direction DOUBLE PRECISION,
    flight_mode VARCHAR(50),
    drone_id UUID NOT NULL REFERENCES drones(id) ON DELETE CASCADE
);

-- Sensors table
CREATE TABLE IF NOT EXISTS sensors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    last_reading TEXT,
    last_reading_at TIMESTAMP WITH TIME ZONE,
    drone_id UUID NOT NULL REFERENCES drones(id) ON DELETE CASCADE
);

-- User-Drone assignments table
CREATE TABLE IF NOT EXISTS user_drone_assignments (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    drone_id UUID NOT NULL REFERENCES drones(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, drone_id)
);

-- Refresh tokens table
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token VARCHAR(255) NOT NULL UNIQUE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expiry_date TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Password reset tokens table
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token VARCHAR(255) NOT NULL UNIQUE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expiry_date TIMESTAMP WITH TIME ZONE NOT NULL,
    used BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_drones_connection_status ON drones(connection_status);
CREATE INDEX IF NOT EXISTS idx_drones_flight_status ON drones(flight_status);
CREATE INDEX IF NOT EXISTS idx_drones_serial_number ON drones(serial_number);
CREATE INDEX IF NOT EXISTS idx_missions_status ON missions(status);
CREATE INDEX IF NOT EXISTS idx_missions_assigned_drone ON missions(assigned_drone_id);
CREATE INDEX IF NOT EXISTS idx_commands_drone ON commands(drone_id);
CREATE INDEX IF NOT EXISTS idx_commands_status ON commands(status);
CREATE INDEX IF NOT EXISTS idx_telemetry_drone ON telemetry(drone_id);
CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp ON telemetry(timestamp);
CREATE INDEX IF NOT EXISTS idx_waypoints_mission ON waypoints(mission_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token ON refresh_tokens(token);
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_token ON password_reset_tokens(token);
