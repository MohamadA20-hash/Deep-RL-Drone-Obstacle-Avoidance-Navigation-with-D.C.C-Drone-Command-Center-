package com.drone_command_center.exception;

public class DroneNotConnectedException extends RuntimeException {
    
    public DroneNotConnectedException(String droneId) {
        super(String.format("Drone '%s' is not connected. Cannot execute command.", droneId));
    }
}
