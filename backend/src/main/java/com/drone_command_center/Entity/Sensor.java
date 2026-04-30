package com.drone_command_center.Entity;

import com.drone_command_center.Entity.enums.SensorType;
import jakarta.persistence.*;
import lombok.*;
import java.util.UUID;

@Entity
@Table(name = "sensors")
@Getter @Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Sensor {

    @Id
    @GeneratedValue
    private UUID id;

    @Enumerated(EnumType.STRING)
    private SensorType type;

    private String model;
    private double rangeMeters;
    private double frequencyHz;
    private boolean enabled;

    @ManyToOne
    @JoinColumn(name = "drone_id")
    private Drone drone;
}
