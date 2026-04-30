package com.drone_command_center;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableAsync
@EnableScheduling
public class DroneCommandCenterApplication {

	public static void main(String[] args) {
		SpringApplication.run(DroneCommandCenterApplication.class, args);
	}

}
