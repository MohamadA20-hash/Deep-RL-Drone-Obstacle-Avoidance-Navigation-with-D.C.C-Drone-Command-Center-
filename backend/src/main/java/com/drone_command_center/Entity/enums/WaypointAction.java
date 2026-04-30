package com.drone_command_center.Entity.enums;

public enum WaypointAction {
    FLY_THROUGH,    // Just pass through, no stop
    HOVER,          // Hover for specified duration
    TAKE_PHOTO,     // Capture photo
    START_VIDEO,    // Start video recording
    STOP_VIDEO,     // Stop video recording
    SCAN_AREA,      // Perform area scan
    DROP_PAYLOAD,   // Release payload
    RETURN_HOME     // Return to launch point
}
