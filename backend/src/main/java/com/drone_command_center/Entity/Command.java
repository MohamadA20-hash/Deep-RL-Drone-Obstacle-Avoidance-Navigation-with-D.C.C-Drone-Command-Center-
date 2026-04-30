package com.drone_command_center.Entity;


import com.drone_command_center.Entity.enums.CommandStatus;
import com.drone_command_center.Entity.enums.CommandType;
import jakarta.persistence.*;
import jakarta.validation.constraints.NotNull;
import lombok.*;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "commands")
@Getter @Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Command {

    @Id
    @GeneratedValue
    private UUID id;

    @NotNull(message = "Command type is required")
    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private CommandType commandType;

    @Column(columnDefinition = "TEXT")
    private String parameters;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private CommandStatus status;

    private Instant createdAt;
    private Instant executedAt;

    // Who issued this command
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "issued_by_user_id")
    private User issuedBy;

    // Which drone receives this command
    @NotNull(message = "Drone is required")
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "drone_id", nullable = false)
    private Drone drone;

    // Optional: if this command is part of a mission
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "mission_id")
    private Mission mission;
}

