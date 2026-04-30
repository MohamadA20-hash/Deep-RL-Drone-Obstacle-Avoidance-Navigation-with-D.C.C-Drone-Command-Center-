package com.drone_command_center.Entity.enums;

public enum FlightStatus {
    IDLE,
    LANDED,
    IN_FLIGHT,
    FLYING,
    HOVERING,
    LANDING,
    TAKING_OFF,
    RETURNING_HOME,
    EMERGENCY,

    // NavRL autonomous navigation states
    NAVIGATING,
    REPLANNING,
    GOAL_REACHED
}
