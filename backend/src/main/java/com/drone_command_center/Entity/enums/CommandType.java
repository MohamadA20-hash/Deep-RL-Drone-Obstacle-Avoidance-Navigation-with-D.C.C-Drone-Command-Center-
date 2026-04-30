package com.drone_command_center.Entity.enums;

public enum CommandType {
    TAKEOFF,
    LAND,
    MOVE,
    SET_MODE,
    EMERGENCY_STOP,

    // NavRL autonomous navigation commands
    SET_GOAL,
    START_AUTONOMOUS_NAV,
    STOP_AUTONOMOUS_NAV,
    FORCE_REPLAN,
    PAUSE_NAV,
    RESUME_NAV,
    SET_PLANNER_CONFIG
}

