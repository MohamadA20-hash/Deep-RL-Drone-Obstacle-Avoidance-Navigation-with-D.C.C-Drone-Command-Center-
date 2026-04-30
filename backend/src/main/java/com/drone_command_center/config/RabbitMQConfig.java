package com.drone_command_center.config;

import org.springframework.amqp.core.*;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@ConditionalOnProperty(name = "app.rabbitmq.enabled", havingValue = "true")
public class RabbitMQConfig {

    // Exchange
    public static final String DRONE_EVENTS_EXCHANGE = "drone.events";

    // Queues
    public static final String DRONE_STATUS_QUEUE = "drone.status";
    public static final String MISSION_EVENTS_QUEUE = "mission.events";
    public static final String COMMAND_EVENTS_QUEUE = "command.events";
    public static final String TELEMETRY_ALERTS_QUEUE = "telemetry.alerts";

    // Routing keys
    public static final String DRONE_REGISTERED_KEY = "drone.registered";
    public static final String DRONE_STATUS_CHANGED_KEY = "drone.status.changed";
    public static final String DRONE_DELETED_KEY = "drone.deleted";
    public static final String MISSION_CREATED_KEY = "mission.created";
    public static final String MISSION_STARTED_KEY = "mission.started";
    public static final String MISSION_COMPLETED_KEY = "mission.completed";
    public static final String MISSION_ABORTED_KEY = "mission.aborted";
    public static final String COMMAND_SENT_KEY = "command.sent";
    public static final String COMMAND_ACKNOWLEDGED_KEY = "command.acknowledged";
    public static final String TELEMETRY_LOW_BATTERY_KEY = "telemetry.low_battery";
    public static final String TELEMETRY_OBSTACLE_KEY = "telemetry.obstacle";

    @Bean
    public TopicExchange droneEventsExchange() {
        return new TopicExchange(DRONE_EVENTS_EXCHANGE);
    }

    @Bean
    public Queue droneStatusQueue() {
        return QueueBuilder.durable(DRONE_STATUS_QUEUE).build();
    }

    @Bean
    public Queue missionEventsQueue() {
        return QueueBuilder.durable(MISSION_EVENTS_QUEUE).build();
    }

    @Bean
    public Queue commandEventsQueue() {
        return QueueBuilder.durable(COMMAND_EVENTS_QUEUE).build();
    }

    @Bean
    public Queue telemetryAlertsQueue() {
        return QueueBuilder.durable(TELEMETRY_ALERTS_QUEUE).build();
    }

    @Bean
    public Binding droneRegisteredBinding(Queue droneStatusQueue, TopicExchange droneEventsExchange) {
        return BindingBuilder.bind(droneStatusQueue).to(droneEventsExchange).with("drone.#");
    }

    @Bean
    public Binding missionEventsBinding(Queue missionEventsQueue, TopicExchange droneEventsExchange) {
        return BindingBuilder.bind(missionEventsQueue).to(droneEventsExchange).with("mission.#");
    }

    @Bean
    public Binding commandEventsBinding(Queue commandEventsQueue, TopicExchange droneEventsExchange) {
        return BindingBuilder.bind(commandEventsQueue).to(droneEventsExchange).with("command.#");
    }

    @Bean
    public Binding telemetryAlertsBinding(Queue telemetryAlertsQueue, TopicExchange droneEventsExchange) {
        return BindingBuilder.bind(telemetryAlertsQueue).to(droneEventsExchange).with("telemetry.#");
    }

    @Bean
    public MessageConverter jackson2JsonMessageConverter() {
        return new Jackson2JsonMessageConverter();
    }

    @Bean
    public RabbitTemplate rabbitTemplate(ConnectionFactory connectionFactory, MessageConverter messageConverter) {
        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        template.setMessageConverter(messageConverter);
        return template;
    }
}
