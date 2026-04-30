package com.drone_command_center.config;

import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.info.License;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import io.swagger.v3.oas.models.servers.Server;
import io.swagger.v3.oas.models.tags.Tag;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;

@Configuration
public class SwaggerConfig {

    @Bean
    public OpenAPI customOpenAPI() {
        return new OpenAPI()
                .info(new Info()
                        .title("Drone Command Center API")
                        .version("1.0.0")
                        .description("""
                                REST API for managing drone fleet operations, missions, telemetry, and commands.
                                
                                ## Features
                                - **Authentication**: JWT-based auth with refresh tokens and rate limiting
                                - **Drone Management**: Register, update, and monitor drone fleet
                                - **Mission Control**: Create, assign, and manage drone missions with waypoints
                                - **Command System**: Send real-time commands to drones (takeoff, land, navigate)
                                - **Telemetry**: Ingest and query real-time drone telemetry data
                                - **NavRL Navigation**: Autonomous navigation with RL-based path planning
                                - **Real-time Updates**: WebSocket support for live telemetry streaming
                                - **Event System**: RabbitMQ-based event publishing for system integration
                                """)
                        .contact(new Contact()
                                .name("Drone Command Center Team")
                                .email("support@dronecommandcenter.com"))
                        .license(new License()
                                .name("MIT License")
                                .url("https://opensource.org/licenses/MIT")))
                .servers(List.of(
                        new Server().url("http://localhost:8080").description("Development Server")
                ))
                .tags(List.of(
                        new Tag().name("Authentication").description("User registration, login, token management"),
                        new Tag().name("Drone Management").description("Drone fleet CRUD and status management"),
                        new Tag().name("Mission Management").description("Mission lifecycle, waypoints, and statistics"),
                        new Tag().name("Command Management").description("Send and track commands to drones"),
                        new Tag().name("Telemetry").description("Drone telemetry ingestion and history"),
                        new Tag().name("User Management").description("User administration (Admin only)"),
                        new Tag().name("NavRL Navigation").description("Autonomous navigation with RL-based planning")
                ))
                .components(new Components()
                        .addSecuritySchemes("bearerAuth", new SecurityScheme()
                                .type(SecurityScheme.Type.HTTP)
                                .scheme("bearer")
                                .bearerFormat("JWT")
                                .description("JWT Authentication - Enter your token without the 'Bearer' prefix")))
                .addSecurityItem(new SecurityRequirement().addList("bearerAuth"));
    }

    @Bean
    public GroupedOpenApi authApi() {
        return GroupedOpenApi.builder()
                .group("1-auth")
                .displayName("Authentication")
                .pathsToMatch("/api/auth/**")
                .build();
    }

    @Bean
    public GroupedOpenApi droneApi() {
        return GroupedOpenApi.builder()
                .group("2-drones")
                .displayName("Drones")
                .pathsToMatch("/api/drones/**")
                .build();
    }

    @Bean
    public GroupedOpenApi missionApi() {
        return GroupedOpenApi.builder()
                .group("3-missions")
                .displayName("Missions")
                .pathsToMatch("/api/missions/**")
                .build();
    }

    @Bean
    public GroupedOpenApi commandApi() {
        return GroupedOpenApi.builder()
                .group("4-commands")
                .displayName("Commands")
                .pathsToMatch("/api/commands/**")
                .build();
    }

    @Bean
    public GroupedOpenApi telemetryApi() {
        return GroupedOpenApi.builder()
                .group("5-telemetry")
                .displayName("Telemetry")
                .pathsToMatch("/api/telemetry/**")
                .build();
    }

    @Bean
    public GroupedOpenApi allApi() {
        return GroupedOpenApi.builder()
                .group("0-all")
                .displayName("All APIs")
                .pathsToMatch("/api/**")
                .build();
    }
}
