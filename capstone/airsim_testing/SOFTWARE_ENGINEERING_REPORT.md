# Software Engineering Report
## Drone Command Center — Autonomous Fleet Management System

---

**Document Reference:** DCC-SER-2026-01  
**Version:** 1.0  
**Date:** April 26, 2026  
**Status:** Final  
**Classification:** Academic / Professional Capstone Submission  

---

## Table of Contents

1. [Preface](#preface)
2. [Introduction](#introduction)
3. [User Requirements](#user-requirements)
4. [System Architecture](#system-architecture)
5. [System Requirements Specifications](#system-requirements-specifications)
   - 5.1 Functional Requirements
   - 5.2 Non-Functional Requirements
6. [System Models](#system-models)
7. [System Evolution](#system-evolution)
8. [Appendices](#appendices)
9. [Index](#index)

---

---

# PREFACE

## About This Document

This report constitutes the full software engineering documentation for the **Drone Command Center (DCC)** — a full-stack autonomous drone fleet management platform developed as a capstone software engineering project. The system was designed, architected, implemented, and tested over a period of several weeks, culminating in a production-ready application comprising a Spring Boot REST API backend and a Flutter cross-platform mobile frontend.

## Acknowledgements

The development of this system drew on the collective body of knowledge in software engineering, distributed systems, real-time communications, and modern mobile application development. Special acknowledgement is given to the open-source communities behind the frameworks and libraries that made this system possible: the Spring ecosystem, the Flutter/Dart community, PostgreSQL, and the many library authors whose work underpins this platform.

## Scope of This Document

This document is intended to serve as both a technical reference and an academic software engineering deliverable. It covers the full lifecycle of the system: from requirements elicitation through architectural design, detailed specifications, modelling, and forward-looking evolution planning. It is written to conform to standard software engineering documentation conventions and is suitable for review by technical and non-technical stakeholders alike.

## Document Conventions

| Convention | Meaning |
|---|---|
| **Bold** | Key terms, system component names |
| `Monospace` | Code identifiers, API paths, configuration keys |
| *Italic* | Emphasis, document references |
| FR-XX | Functional Requirement identifier |
| NFR-XX | Non-Functional Requirement identifier |

---

---

# 1. INTRODUCTION

## 1.1 Background and Motivation

The rapid proliferation of autonomous unmanned aerial vehicles (UAVs) — commonly known as drones — across commercial, military, agricultural, and emergency-response domains has created a pressing need for sophisticated command-and-control infrastructure. Managing a fleet of drones in real time demands capabilities far beyond simple remote control: operators require a unified platform through which they can register and monitor assets, plan and execute complex multi-waypoint missions, receive live telemetry feeds, issue emergency commands, and maintain a full audit trail of all operational activity.

The **Drone Command Center** was conceived to address this operational gap. It delivers a mission-critical, tactically-oriented platform that provides fleet operators with a single pane of glass into every aspect of their drone operations. The system's design philosophy draws from the aesthetic and functional language of submarine command centers and military tactical operations centers — emphasising clarity of information, precision of control, and resilience under pressure.

## 1.2 Project Objectives

The primary objectives of the Drone Command Center project are:

1. **Centralised Fleet Visibility** — Provide real-time awareness of the position, status, battery level, and sensor health of every drone in the managed fleet.
2. **Mission Lifecycle Management** — Support the full lifecycle of a drone mission, from planning and waypoint definition through execution monitoring to post-mission reporting.
3. **Secure Multi-Role Access** — Enforce role-based access control so that operators, administrators, maintenance personnel, and viewers each interact with the system according to their privilege level.
4. **Real-Time Command and Telemetry** — Deliver sub-second telemetry updates to connected clients via WebSocket, and allow authorised users to issue commands with immediate effect.
5. **Operational Resilience** — Ensure the backend is protected against abuse through rate limiting, token-based session management, and structured error handling.
6. **Scalability and Maintainability** — Build the system on industry-standard frameworks with clean separation of concerns so that it can grow to support a larger fleet and additional feature sets without architectural rework.

## 1.3 Scope

### In Scope

- User registration, authentication, and session management (JWT + Refresh Tokens)
- Role-based access control (ADMIN, OPERATOR, PILOT, VIEWER, MAINTENANCE, RESEARCHER)
- Drone asset registration, status tracking, and fleet management
- Mission planning with sequential waypoints, priority levels, and assigned drones
- Real-time telemetry ingestion and streaming via WebSocket
- Command issuance (TAKEOFF, LAND, RTH, HOVER, WAYPOINT, EMERGENCY_STOP, etc.)
- Sensor status monitoring per drone
- Email-based password reset workflow
- Caching, rate limiting, and health monitoring
- Flutter mobile frontend for all of the above features
- PostgreSQL persistence with versioned schema migrations
- RESTful API documentation via Swagger/OpenAPI 3.0

### Out of Scope

- Physical drone hardware integration (hardware-specific SDK bridging)
- Federal aviation authority compliance tooling
- Video feed streaming
- AI-based autonomous mission planning (noted as future work)
- Multi-tenant / multi-organisation support

## 1.4 Definitions and Abbreviations

| Term | Definition |
|---|---|
| UAV | Unmanned Aerial Vehicle (drone) |
| DCC | Drone Command Center |
| JWT | JSON Web Token |
| RTH | Return-to-Home |
| RBAC | Role-Based Access Control |
| REST | Representational State Transfer |
| WebSocket | Full-duplex communication protocol over a persistent TCP connection |
| STOMP | Simple Text Oriented Messaging Protocol |
| ORM | Object-Relational Mapping |
| DTO | Data Transfer Object |
| API | Application Programming Interface |

## 1.5 Document Organisation

This document is structured as follows:

- **Chapter 2 — User Requirements** identifies the stakeholders and captures their needs in the form of user stories and use case descriptions.
- **Chapter 3 — System Architecture** presents the high-level architectural design, component decomposition, and deployment view.
- **Chapter 4 — System Requirements Specifications** enumerates the formal functional and non-functional requirements.
- **Chapter 5 — System Models** provides use case models, entity-relationship diagrams, sequence diagrams, and data flow descriptions.
- **Chapter 6 — System Evolution** discusses planned enhancements and the maintainability roadmap.
- **Appendices** contain supporting reference material: the full API catalogue, database schema, technology stack, and configuration reference.

---

---

# 2. USER REQUIREMENTS

## 2.1 Stakeholder Identification

The Drone Command Center serves a diverse set of stakeholders, each with distinct operational needs:

| Stakeholder | Role | Primary Concern |
|---|---|---|
| **Fleet Operator** | Day-to-day drone operations | Real-time fleet status, mission creation, command issuance |
| **System Administrator** | Platform governance | User management, system health, access control |
| **Pilot / Remote Operator** | Controlling individual drones | Receiving commands, telemetry feedback |
| **Maintenance Technician** | Fleet upkeep | Sensor status, battery health, firmware versions |
| **Mission Planner** | Strategic mission design | Waypoint planning, priority assignment, drone allocation |
| **Analyst / Researcher** | Post-mission analysis | Historical telemetry, flight path data |
| **Viewer** | Read-only monitoring | Dashboard overview, no write access |

## 2.2 User Stories

### 2.2.1 Authentication and Account Management

> **US-01** — As a **new user**, I want to register with a username, email, and strong password so that I can access the command center.

> **US-02** — As a **registered user**, I want to log in with my credentials and receive a session token so that I can access protected resources.

> **US-03** — As a **logged-in user**, I want my session to be automatically refreshed using a refresh token so that I am not interrupted during active operations.

> **US-04** — As a **user who has forgotten their password**, I want to receive a password reset link via email so that I can regain access to my account.

> **US-05** — As a **system administrator**, I want to assign roles to users so that each person can only perform actions appropriate to their clearance level.

---

### 2.2.2 Fleet Management

> **US-06** — As a **fleet operator**, I want to register a new drone with its serial number, model type, and firmware version so that it is tracked by the system.

> **US-07** — As a **fleet operator**, I want to view a live dashboard showing all drones, their connection status, flight status, and battery level so that I maintain full situational awareness.

> **US-08** — As a **fleet operator**, I want to view detailed telemetry for any individual drone, including GPS coordinates, altitude, speed, heading, and signal strength.

> **US-09** — As a **maintenance technician**, I want to view the status of each sensor on a drone (camera, LIDAR, GPS) so that I can schedule maintenance before failure.

> **US-10** — As a **fleet operator**, I want to filter and sort the drone list by status, battery, or model so that I can quickly find the asset I need.

---

### 2.2.3 Mission Planning and Execution

> **US-11** — As a **mission planner**, I want to create a mission with a name, description, priority, and an assigned drone so that operational tasks are formally tracked.

> **US-12** — As a **mission planner**, I want to define an ordered sequence of waypoints (latitude, longitude, altitude, action, hover duration, speed) so that a drone follows a precise flight path.

> **US-13** — As a **fleet operator**, I want to start, pause, complete, or abort a mission so that I retain control of execution at all times.

> **US-14** — As a **fleet operator**, I want to view the current status and progress of an active mission, including which waypoints have been reached.

> **US-15** — As a **fleet operator**, I want to see all missions on a map view with their waypoint paths rendered so that I can assess operational geography.

---

### 2.2.4 Command and Control

> **US-16** — As an **operator**, I want to issue a TAKEOFF command to a drone so that it begins its flight from the ground.

> **US-17** — As an **operator**, I want to issue a LAND command to a drone so that it safely returns to the ground.

> **US-18** — As an **operator**, I want to issue a RETURN_TO_HOME command so that the drone autonomously returns to its registered home coordinates.

> **US-19** — As an **operator**, I want to issue an EMERGENCY_STOP command with highest priority so that a drone immediately halts all operations in a critical situation.

> **US-20** — As an **operator**, I want to see the history of all commands issued to a drone, including their status (PENDING, SENT, EXECUTED, FAILED).

---

### 2.2.5 Real-Time Telemetry

> **US-21** — As an **operator**, I want to see live telemetry data updating on screen without refreshing the page so that I have an uninterrupted operational picture.

> **US-22** — As an **operator**, I want to view historical telemetry charts (battery, altitude, speed over time) so that I can identify trends and anomalies.

> **US-23** — As an **operator**, I want to see the flight path of a drone rendered on a map so that I can trace its historical or current route.

---

### 2.2.6 System Administration

> **US-24** — As an **administrator**, I want to access system health endpoints so that I can monitor API uptime, memory usage, and database connectivity.

> **US-25** — As an **administrator**, I want rate limiting to be enforced on authentication endpoints so that brute force attacks are mitigated automatically.

> **US-26** — As an **administrator**, I want all database schema changes to be applied automatically via versioned migrations so that the database is always in a consistent state.

## 2.3 Use Case Summary Table

| Use Case ID | Name | Actor(s) | Priority |
|---|---|---|---|
| UC-01 | Register Account | Anonymous User | High |
| UC-02 | Authenticate / Login | Registered User | High |
| UC-03 | Refresh Session | Authenticated User | High |
| UC-04 | Reset Password | Registered User | Medium |
| UC-05 | Register Drone | Operator, Admin | High |
| UC-06 | View Fleet Dashboard | Operator, Admin, Viewer | High |
| UC-07 | View Drone Telemetry | Operator, Admin | High |
| UC-08 | Create Mission | Operator, Admin | High |
| UC-09 | Define Waypoints | Operator, Admin | High |
| UC-10 | Execute Mission | Operator, Admin | High |
| UC-11 | Issue Command | Operator, Admin | High |
| UC-12 | Monitor Live Telemetry | Operator, Admin | High |
| UC-13 | View Historical Telemetry | Operator, Admin, Researcher | Medium |
| UC-14 | Manage Users | Admin | High |
| UC-15 | Monitor System Health | Admin | Medium |

---

---

# 3. SYSTEM ARCHITECTURE

## 3.1 Architectural Overview

The Drone Command Center follows a **three-tier client-server architecture** with an additional real-time messaging layer. The system is decomposed into the following major tiers:

```
┌───────────────────────────────────────────────────────────────┐
│                    PRESENTATION TIER                          │
│                                                               │
│   ┌─────────────────────────────────────────────────────┐    │
│   │          Flutter Mobile / Web Application           │    │
│   │  (Riverpod State Management, GoRouter Navigation)   │    │
│   └─────────────────────────────────────────────────────┘    │
│                 ▲ HTTP/REST     ▲ WebSocket                   │
└─────────────────┼───────────────┼─────────────────────────────┘
                  │               │
┌─────────────────┼───────────────┼─────────────────────────────┐
│                 ▼               ▼    APPLICATION TIER         │
│   ┌─────────────────────────────────────────────────────┐    │
│   │        Spring Boot 4.0.2 REST API Backend           │    │
│   │                                                     │    │
│   │  ┌──────────┐ ┌──────────┐ ┌──────────────────┐    │    │
│   │  │  Auth    │ │  Drone   │ │ Mission/Command  │    │    │
│   │  │Controller│ │Controller│ │   Controllers    │    │    │
│   │  └──────────┘ └──────────┘ └──────────────────┘    │    │
│   │                                                     │    │
│   │  ┌──────────┐ ┌──────────┐ ┌──────────────────┐    │    │
│   │  │  Auth    │ │  Drone   │ │  Mission/Telem.  │    │    │
│   │  │ Service  │ │ Service  │ │    Services      │    │    │
│   │  └──────────┘ └──────────┘ └──────────────────┘    │    │
│   │                                                     │    │
│   │  ┌──────────────┐  ┌───────────┐  ┌────────────┐   │    │
│   │  │  JWT Filter  │  │  Rate     │  │  Cache     │   │    │
│   │  │  + Security  │  │  Limiter  │  │  (Caffeine)│   │    │
│   │  └──────────────┘  └───────────┘  └────────────┘   │    │
│   │                                                     │    │
│   │  ┌──────────────────────────────────────────────┐   │    │
│   │  │     WebSocket Handler (Telemetry Stream)     │   │    │
│   │  └──────────────────────────────────────────────┘   │    │
│   └─────────────────────────────────────────────────┘    │
│                 │ JPA / Hibernate                         │
└─────────────────┼───────────────────────────────────────-┘
                  │
┌─────────────────┼──────────────────────────────────────────┐
│                 ▼               DATA TIER                   │
│   ┌──────────────────────────────────────────────────┐     │
│   │           PostgreSQL 15+ Database                │     │
│   │                                                  │     │
│   │  users · user_roles · drones · missions          │     │
│   │  waypoints · commands · telemetry · sensors      │     │
│   │  refresh_tokens · password_reset_tokens          │     │
│   │                                                  │     │
│   │    (Schema managed by Flyway Migrations)         │     │
│   └──────────────────────────────────────────────────┘     │
└────────────────────────────────────────────────────────────┘
```

## 3.2 Backend Architecture

### 3.2.1 Technology Stack

| Component | Technology | Version |
|---|---|---|
| Application Framework | Spring Boot | 4.0.2 |
| Language | Java | 17 |
| Build System | Apache Maven | 3.x |
| Persistence | Spring Data JPA + Hibernate | 6.x |
| Database Driver | PostgreSQL JDBC | Latest |
| Schema Migration | Flyway | Latest |
| Security Framework | Spring Security | 6.x |
| Authentication | JJWT (JSON Web Token) | 0.11.5 |
| Rate Limiting | Bucket4j | 8.10.1 |
| Caching | Caffeine + Spring Cache | Latest |
| Real-Time Messaging | Spring WebSocket + SockJS | Latest |
| Message Broker | RabbitMQ (Spring AMQP) | Latest |
| Email | Spring Mail (SMTP) | Latest |
| API Documentation | SpringDoc OpenAPI 3.0 | 2.8.4 |
| Monitoring | Spring Actuator | Latest |
| Utility | Lombok | Latest |

### 3.2.2 Package Structure

The backend follows a layered package architecture organised by concern:

```
com.drone_command_center/
├── DroneCommandCenterApplication.java   ← Entry point
├── config/                              ← Cross-cutting configuration
│   ├── SecurityConfig.java
│   ├── WebSocketConfig.java
│   ├── CacheConfig.java
│   ├── RateLimiter.java
│   ├── SwaggerConfig.java
│   ├── JacksonConfig.java
│   ├── PasswordConfig.java
│   ├── RabbitMQConfig.java
│   └── DataSeeder.java
├── Security/                            ← JWT infrastructure
│   ├── JwtFilter.java
│   └── JwtUtil.java
├── Controller/                          ← HTTP request handlers
│   ├── AuthController.java
│   ├── DroneController.java
│   ├── MissionController.java
│   ├── CommandController.java
│   ├── TelemetryController.java
│   ├── UserController.java
│   ├── AirSimBridgeController.java
│   └── NavRLController.java
├── Service/                             ← Business logic
│   ├── AuthService.java
│   ├── DroneService.java
│   ├── MissionService.java
│   ├── CommandService.java
│   ├── TelemetryService.java
│   ├── UserService.java
│   ├── EmailService.java
│   ├── RefreshTokenService.java
│   ├── PasswordResetService.java
│   ├── EventPublisher.java
│   ├── EventConsumer.java
│   ├── AirSimBridgeManager.java
│   └── NavRLBridgeService.java
├── Repository/                          ← Data access layer (Spring Data JPA)
├── Entity/                              ← JPA domain entities
│   ├── User.java
│   ├── Drone.java
│   ├── Mission.java
│   ├── Waypoint.java
│   ├── Command.java
│   ├── Telemetry.java
│   ├── Sensor.java
│   ├── RefreshToken.java
│   ├── PasswordResetToken.java
│   └── enums/
├── DTO/                                 ← Request and response objects
├── exception/                           ← Custom exception types + handlers
├── validation/                          ← Custom validators
├── scheduler/                           ← Scheduled background tasks
└── websocket/                           ← WebSocket handler + session management
```

### 3.2.3 Security Architecture

Security is implemented as a layered defence-in-depth strategy:

1. **Rate Limiting (Bucket4j)** — The outermost protection layer. Authentication endpoints are limited to 10 requests per minute per IP address. After 5 failed login attempts per username, the account is locked out for 15 minutes. The token-bucket algorithm ensures smooth rate enforcement.

2. **JWT Authentication Filter** — Every incoming request (except public endpoints) passes through `JwtFilter`, which validates the `Authorization: Bearer <token>` header, extracts the subject and roles, and populates the Spring Security `SecurityContext`.

3. **Spring Security Authorization** — Method-level and URL-level authorization is enforced via `@PreAuthorize` annotations and `authorizeHttpRequests` configuration. The RBAC matrix governs which roles may access which operations.

4. **Stateless Sessions** — The server maintains no session state. All authentication context is self-contained in the JWT. Refresh tokens (stored in the database) allow session extension without re-authentication.

5. **HTTPS + Security Headers** — HSTS, `X-Content-Type-Options`, and `X-Frame-Options: DENY` headers are enforced to harden against common web vulnerabilities.

6. **Password Validation** — Passwords must satisfy: minimum 8 characters, at least one uppercase letter, one lowercase letter, one digit, and one special character.

### 3.2.4 Role-Based Access Control Matrix

| Resource | ADMIN | OPERATOR | PILOT | MAINTENANCE | VIEWER | RESEARCHER |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Register/Login | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Create Drone | ✓ | ✓ | — | — | — | — |
| Update Drone | ✓ | ✓ | — | ✓ | — | — |
| Delete Drone | ✓ | — | — | — | — | — |
| Create Mission | ✓ | ✓ | — | — | — | — |
| Execute Mission | ✓ | ✓ | ✓ | — | — | — |
| Issue Commands | ✓ | ✓ | ✓ | — | — | — |
| View Telemetry | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Manage Users | ✓ | — | — | — | — | — |
| Access Actuator | ✓ | — | — | — | — | — |

## 3.3 Frontend Architecture

### 3.3.1 Technology Stack

| Component | Technology | Version |
|---|---|---|
| Framework | Flutter | SDK ≥ 3.0.0 |
| Language | Dart | ≥ 3.0 |
| State Management | flutter_riverpod | ^2.4.9 |
| Navigation | go_router | ^13.0.1 |
| HTTP Client | dio | ^5.4.0 |
| WebSocket | web_socket_channel | ^2.4.0 |
| Secure Storage | flutter_secure_storage | ^9.0.0 |
| Charts | fl_chart | ^0.66.0 |
| Maps | flutter_map (OpenStreetMap) | ^6.1.0 |
| Animations | lottie, animate_do, shimmer | Latest |
| Code Generation | riverpod_generator, json_serializable | Latest |

### 3.3.2 Application Structure

```
lib/
├── main.dart                        ← App entry point
├── core/
│   ├── cache/                       ← Local caching utilities
│   ├── config/                      ← App-wide configuration
│   ├── constants/                   ← API base URLs, route names
│   ├── network/                     ← Dio client, interceptors, token refresh
│   ├── notifications/               ← Local notification service
│   ├── router/                      ← GoRouter route definitions
│   ├── shell/                       ← App shell with bottom navigation
│   ├── theme/                       ← Tactical dark theme (colours, typography)
│   ├── utils/                       ← Date formatters, validators
│   └── widgets/                     ← Shared reusable widgets
└── features/
    ├── auth/                        ← Login, Register, Password Reset screens
    ├── dashboard/                   ← Fleet summary, stat cards
    ├── drones/                      ← Drone list, drone detail, telemetry charts
    ├── map/                         ← Interactive map with drone positions
    ├── missions/                    ← Mission list, mission detail, create mission
    ├── settings/                    ← User preferences, logout
    ├── simulator/                   ← Drone simulation controls
    └── telemetry/                   ← Real-time telemetry stream UI
```

### 3.3.3 State Management Pattern

The application uses **Riverpod** with code generation for state management. Each feature follows a consistent provider pattern:

- **`StateNotifierProvider`** — For complex mutable state (e.g., `DroneListNotifier`, `MissionDetailNotifier`)
- **`FutureProvider`** — For single async fetch operations
- **`StreamProvider`** — For WebSocket telemetry streams
- **`Provider`** — For services (Dio client, navigation router)

Authentication state persists across app restarts by storing the JWT and refresh token in `flutter_secure_storage` (hardware-backed secure enclave on mobile platforms).

### 3.3.4 Design Language

The UI implements a **Tactical Military Command Center** aesthetic:

| Element | Specification |
|---|---|
| Background | `#0A0A0A` (near-black) |
| Primary Accent | `#00FF88` (neon green — "tactical green") |
| Secondary Accent | `#00D4FF` (electric cyan) |
| Warning | `#FF6B35` (amber-orange) |
| Danger | `#FF0040` (critical red) |
| Primary Font | Rajdhani (headings, tactical labels) |
| Monospace Font | Space Mono (data values, coordinates) |
| Card Style | Dark glass with subtle neon border glow |

## 3.4 Deployment Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      PRODUCTION ENVIRONMENT                  │
│                                                              │
│  ┌────────────────────┐     ┌──────────────────────────┐    │
│  │  Flutter Client    │     │    Spring Boot API       │    │
│  │  (Mobile / Web)    │────▶│    :8080 / :8443 (TLS)  │    │
│  └────────────────────┘     └──────────┬───────────────┘    │
│                                        │                     │
│  ┌────────────────────┐     ┌──────────▼───────────────┐    │
│  │   RabbitMQ         │◀────│    PostgreSQL 15+         │    │
│  │   Message Broker   │     │    Database               │    │
│  └────────────────────┘     └──────────────────────────┘    │
│                                                              │
│  ┌────────────────────────────────────────────────────┐     │
│  │              Docker Compose (Local Dev)             │     │
│  │  postgres:15 · rabbitmq:management · backend app   │     │
│  └────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────┘
```

The `docker-compose.yml` at the project root orchestrates the backend service, PostgreSQL database, and RabbitMQ message broker for local development. The Flutter application communicates with the backend over HTTP/REST and maintains a persistent WebSocket connection for real-time telemetry.

---

---

# 4. SYSTEM REQUIREMENTS SPECIFICATIONS

## 4.1 Functional Requirements

### 4.1.1 Authentication and User Management

| ID | Requirement | Priority |
|---|---|---|
| FR-01 | The system shall allow anonymous users to register by providing a unique username, unique email address, and a password satisfying the strength policy. | Must Have |
| FR-02 | The system shall authenticate registered users via a username-and-password challenge and return a signed JWT access token and a refresh token upon success. | Must Have |
| FR-03 | The system shall validate the JWT on every protected request and reject expired or tampered tokens with HTTP 401. | Must Have |
| FR-04 | The system shall allow clients to exchange a valid refresh token for a new access token without re-authentication. | Must Have |
| FR-05 | The system shall invalidate the refresh token on logout, preventing further token renewal. | Must Have |
| FR-06 | The system shall enforce a password strength policy: minimum 8 characters, at least one uppercase letter, one lowercase letter, one digit, and one special character. | Must Have |
| FR-07 | The system shall support email-based password reset: a time-limited reset token is emailed to the user, which may be exchanged for a new password once. | Should Have |
| FR-08 | The system shall support the following roles: ADMIN, OPERATOR, PILOT, VIEWER, MAINTENANCE, RESEARCHER. | Must Have |
| FR-09 | The system shall enforce role-based access control on all protected API endpoints. | Must Have |
| FR-10 | The system shall allow administrators to list, update, and deactivate user accounts. | Should Have |

---

### 4.1.2 Drone Fleet Management

| ID | Requirement | Priority |
|---|---|---|
| FR-11 | The system shall allow authorised users to register a new drone with: serial number (unique), name, model type, firmware version, home coordinates, and initial status. | Must Have |
| FR-12 | The system shall persist the following real-time drone state: connection status (CONNECTED, DISCONNECTED, CONNECTING, ERROR), flight status (IDLE, TAKING_OFF, IN_FLIGHT, LANDING, HOVERING, RETURNING_HOME, EMERGENCY, OFFLINE), battery level (%), GPS coordinates (lat/lon/alt), heading, speed, and last heartbeat timestamp. | Must Have |
| FR-13 | The system shall return a paginated list of all drones, sortable by name, battery level, or status. | Must Have |
| FR-14 | The system shall return the full details of a single drone by its UUID identifier. | Must Have |
| FR-15 | The system shall allow authorised users to update drone configuration and status. | Must Have |
| FR-16 | The system shall allow administrators to delete a drone record and cascade-delete all associated telemetry, sensors, and commands. | Should Have |
| FR-17 | The system shall filter drones by connection status and flight status. | Should Have |
| FR-18 | The system shall cache drone list results in-memory (Caffeine) for up to 5 minutes to reduce database load. | Should Have |

---

### 4.1.3 Mission Management

| ID | Requirement | Priority |
|---|---|---|
| FR-19 | The system shall allow authorised users to create a mission with: name, description, assigned drone (optional), priority (integer), and estimated duration. | Must Have |
| FR-20 | The system shall support mission states: PLANNED, IN_PROGRESS, COMPLETED, ABORTED, FAILED, PAUSED. | Must Have |
| FR-21 | The system shall allow missions to include an ordered list of waypoints, each specifying: latitude, longitude, altitude, sequence order, waypoint action (HOVER, TAKE_PHOTO, SCAN, INSPECT, DELIVER, LAND), hover duration, speed, and heading. | Must Have |
| FR-22 | The system shall allow operators to add, update, and remove individual waypoints from a mission. | Should Have |
| FR-23 | The system shall allow operators to start, pause, resume, complete, and abort missions, updating the status accordingly. | Must Have |
| FR-24 | The system shall record `start_time`, `end_time`, and `actual_duration_minutes` when a mission's lifecycle state changes. | Must Have |
| FR-25 | The system shall return paginated lists of missions, filterable by status. | Must Have |
| FR-26 | The system shall return all waypoints for a given mission in sequence order. | Must Have |

---

### 4.1.4 Command and Control

| ID | Requirement | Priority |
|---|---|---|
| FR-27 | The system shall accept commands from authorised users targeting a specific drone. | Must Have |
| FR-28 | The system shall support the following command types: TAKEOFF, LAND, RETURN_TO_HOME (RTH), HOVER, GO_TO_WAYPOINT, START_MISSION, ABORT_MISSION, EMERGENCY_STOP, SET_ALTITUDE, SET_SPEED, ROTATE, TAKE_PHOTO, START_STREAMING, STOP_STREAMING. | Must Have |
| FR-29 | The system shall assign command statuses: PENDING, SENT, ACKNOWLEDGED, EXECUTED, FAILED, CANCELLED. | Must Have |
| FR-30 | The system shall record the timestamp when a command is issued, when it is sent to the drone, when executed, and when completed. | Must Have |
| FR-31 | The system shall return the command history for a given drone, paginated and sorted by issued time. | Should Have |
| FR-32 | The system shall store the optional JSON payload for commands that carry parameters (e.g., target coordinates for GO_TO_WAYPOINT). | Should Have |

---

### 4.1.5 Telemetry and Sensor Monitoring

| ID | Requirement | Priority |
|---|---|---|
| FR-33 | The system shall accept telemetry ingestion requests from drones or bridge adapters, recording: timestamp, GPS (lat/lon/alt), speed, heading, battery level, signal strength, GPS satellite count, temperature, humidity, wind speed, wind direction, and flight mode. | Must Have |
| FR-34 | The system shall stream the most recent telemetry for each drone to all connected WebSocket clients within 1 second of receipt. | Must Have |
| FR-35 | The system shall maintain a persistent WebSocket endpoint at `/ws/telemetry`, supporting both native WebSocket and SockJS fallback. | Must Have |
| FR-36 | The system shall return the latest telemetry record for a given drone via REST. | Must Have |
| FR-37 | The system shall return paginated historical telemetry, optionally filtered by a time range. | Should Have |
| FR-38 | The system shall return the historical flight path (lat/lon sequence) for a drone for map rendering. | Should Have |
| FR-39 | The system shall persist sensor records per drone with: name, sensor type (CAMERA, LIDAR, GPS, BAROMETER, IMU, RADAR, THERMAL_CAMERA, ULTRASONIC, MAGNETOMETER), status (ACTIVE, INACTIVE, ERROR, CALIBRATING), last reading, and last reading timestamp. | Should Have |

---

### 4.1.6 System Operations

| ID | Requirement | Priority |
|---|---|---|
| FR-40 | The system shall expose Spring Actuator health and info endpoints publicly, and restrict all other Actuator endpoints to ADMIN role. | Must Have |
| FR-41 | The system shall apply rate limiting on authentication endpoints: 10 requests per minute per IP; 5 failed attempts per username triggers a 15-minute lockout. | Must Have |
| FR-42 | The system shall apply all database schema changes automatically via Flyway versioned migration scripts on startup. | Must Have |
| FR-43 | The system shall expose a Swagger/OpenAPI 3.0 UI at `/swagger-ui/index.html` documenting all API endpoints. | Should Have |
| FR-44 | The system shall publish domain events to RabbitMQ for asynchronous inter-service communication. | Could Have |
| FR-45 | The system shall run scheduled background tasks (e.g., clearing expired tokens, checking drone heartbeats). | Should Have |

---

## 4.2 Non-Functional Requirements

### 4.2.1 Performance

| ID | Requirement | Metric |
|---|---|---|
| NFR-01 | The REST API shall respond to 95% of read requests within 200ms under normal load. | Response time ≤ 200ms (p95) |
| NFR-02 | The WebSocket telemetry stream shall deliver new data to subscribed clients within 1 second of ingestion. | Latency ≤ 1,000ms |
| NFR-03 | The Caffeine in-memory cache shall serve repeated read requests without database round-trips for up to 5 minutes per cached entry. | Cache TTL = 5 min |
| NFR-04 | The system shall support at least 50 concurrent WebSocket connections without degradation. | Concurrency ≥ 50 |
| NFR-05 | Database queries shall use appropriate indexes; the system shall not execute N+1 query patterns. | Zero N+1 queries in production paths |

---

### 4.2.2 Security

| ID | Requirement |
|---|---|
| NFR-06 | All passwords shall be stored as BCrypt hashes with a strength factor of at least 10. |
| NFR-07 | JWT access tokens shall have an expiry of no more than 24 hours. Refresh tokens shall have a configurable expiry (default: 7 days). |
| NFR-08 | All API communication shall support TLS encryption in production (HTTPS). |
| NFR-09 | The application shall be protected against SQL injection through exclusive use of parameterised queries via JPA/Hibernate. |
| NFR-10 | The application shall be protected against Cross-Site Request Forgery (CSRF) by maintaining stateless JWT authentication with no server-side session cookies. |
| NFR-11 | HTTP security headers shall include `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, and `X-Frame-Options: DENY`. |
| NFR-12 | Sensitive configuration values (DB credentials, JWT secret, mail credentials) shall be externalised via environment variables and never committed to source control. |
| NFR-13 | Rate limiting shall be applied to all authentication endpoints to mitigate credential-stuffing and brute-force attacks. |

---

### 4.2.3 Reliability and Availability

| ID | Requirement |
|---|---|
| NFR-14 | The backend application shall target 99.5% uptime in production. |
| NFR-15 | The database shall have automated daily backups with a retention period of 30 days. |
| NFR-16 | On application startup, Flyway shall verify that the current schema version matches the deployed application version and refuse to start if a destructive migration conflict is detected. |
| NFR-17 | The system shall gracefully handle WebSocket disconnections and allow clients to reconnect and resume telemetry reception without data loss of more than one polling interval. |
| NFR-18 | All unhandled exceptions shall return structured error responses (timestamp, status code, message, path) rather than stack traces. |

---

### 4.2.4 Usability

| ID | Requirement |
|---|---|
| NFR-19 | The Flutter frontend shall provide an intuitive tactical UI that allows a trained operator to locate any drone's status within 2 interactions from the dashboard. |
| NFR-20 | The application shall provide meaningful validation error messages for all form inputs, displayed inline near the relevant field. |
| NFR-21 | The application shall display loading indicators (shimmer skeletons) during all asynchronous data fetch operations to prevent perceived unresponsiveness. |
| NFR-22 | The application shall support both portrait and landscape orientations on mobile devices without layout degradation. |
| NFR-23 | The Swagger UI shall provide complete descriptions, request/response schemas, and example values for every API endpoint. |

---

### 4.2.5 Scalability

| ID | Requirement |
|---|---|
| NFR-24 | The backend application shall be stateless (no server-side HTTP session) to allow horizontal scaling behind a load balancer. |
| NFR-25 | The caching layer shall be replaceable with a distributed cache (e.g., Redis) by changing configuration only, without code changes to business logic. |
| NFR-26 | The database connection pool shall be configurable via `application.properties` to accommodate varying load profiles. |
| NFR-27 | RabbitMQ integration shall decouple telemetry ingestion from downstream processing, allowing consumers to be scaled independently. |

---

### 4.2.6 Maintainability

| ID | Requirement |
|---|---|
| NFR-28 | The codebase shall maintain a clear separation between presentation (Controllers/DTOs), business logic (Services), and persistence (Repositories/Entities) layers. |
| NFR-29 | All public API endpoints shall be documented via OpenAPI 3.0 annotations. |
| NFR-30 | All database schema changes shall be made exclusively through Flyway versioned migration scripts; direct DDL changes on the production database are prohibited. |
| NFR-31 | The application shall emit structured, levelled log output (ERROR, WARN, INFO, DEBUG) via Logback/SLF4J, with separate log files for application and audit events. |
| NFR-32 | The system shall achieve a minimum unit test coverage of 70% for all Service layer classes. |

---

### 4.2.7 Portability

| ID | Requirement |
|---|---|
| NFR-33 | The backend shall be deployable as a self-contained JAR on any JVM 17+ runtime, or as a Docker container. |
| NFR-34 | The Flutter application shall compile to Android APK, iOS IPA, and web bundle from a single codebase. |
| NFR-35 | The `docker-compose.yml` shall allow any developer to bring up a complete local development environment with a single command (`docker-compose up`). |

---

---

# 5. SYSTEM MODELS

## 5.1 Use Case Model

### 5.1.1 Authentication Use Case

```
         ┌──────────────────────────────────────────┐
         │            Authentication System          │
         │                                          │
User ───▶│  ○ Register Account                      │
         │  ○ Login                                 │
         │  ○ Refresh Token                         │
         │  ○ Logout                                │
         │  ○ Request Password Reset                │
         │  ○ Confirm Password Reset                │
         │                                          │
Admin ───▶│  ○ Manage User Accounts                 │
         └──────────────────────────────────────────┘
```

### 5.1.2 Fleet Operations Use Case

```
         ┌──────────────────────────────────────────────────┐
         │               Fleet Operations                    │
         │                                                  │
Operator ▶│  ○ Register Drone                               │
         │  ○ View Fleet Dashboard                          │
         │  ○ View Drone Detail                             │
         │  ○ Update Drone Configuration                    │
         │  ○ View Sensor Status                            │
         │  ○ Issue Command ──────────────────────────────▶ │── Drone
         │  ○ View Command History                          │
         │                                                  │
Viewer ──▶│  ○ View Fleet Dashboard (read-only)             │
         │  ○ View Drone Detail (read-only)                 │
         └──────────────────────────────────────────────────┘
```

### 5.1.3 Mission Planning Use Case

```
         ┌────────────────────────────────────────────────────┐
         │               Mission Management                    │
         │                                                    │
Operator ▶│  ○ Create Mission                                │
         │  ○ Define Waypoints                               │
         │  ○ Assign Drone                                   │
         │  ○ Start / Pause / Resume Mission                 │
         │  ○ Complete / Abort Mission                       │
         │  ○ View Mission on Map                            │
         │                                                   │
Pilot ───▶│  ○ View Assigned Mission                        │
         │  ○ Mark Waypoint Reached                         │
         └───────────────────────────────────────────────────┘
```

## 5.2 Entity-Relationship Model

The following describes the key entity relationships in the system:

```
USER ──< USER_ROLES
  │
  ├──< MISSIONS (created_by)
  └──< COMMANDS (issued_by)

DRONE ──< TELEMETRY
  │
  ├──< SENSORS
  ├──< COMMANDS
  ├──< MISSIONS (assigned_drone)
  │
  └── HOME_LOCATION (lat/lon/alt embedded)

MISSION ──< WAYPOINTS (ordered, ON DELETE CASCADE)
  │
  ├──── DRONE (assigned, nullable)
  └──── USER (created_by)

COMMAND ──── DRONE
  └──── USER (issued_by)

TELEMETRY ──── DRONE
SENSOR ──── DRONE
REFRESH_TOKEN ──── USER
PASSWORD_RESET_TOKEN ──── USER
```

**Cardinality Summary:**
- One **User** may have many **Roles** (many-to-many via `user_roles` junction table)
- One **User** may create many **Missions** (one-to-many)
- One **User** may issue many **Commands** (one-to-many)
- One **Drone** may have many **Telemetry** records (one-to-many, time-series)
- One **Drone** may have many **Sensors** (one-to-many)
- One **Drone** may have many **Commands** (one-to-many)
- One **Drone** may be assigned to many **Missions** over time (one-to-many)
- One **Mission** has one ordered list of **Waypoints** (one-to-many, cascade delete)
- One **User** has at most one active **RefreshToken** at a time

## 5.3 Sequence Diagrams

### 5.3.1 User Authentication Flow

```
Client          RateLimiter       AuthController      AuthService       JwtUtil       Database
  │                  │                 │                   │                │               │
  │─POST /auth/login▶│                 │                   │                │               │
  │                  │─tryConsume()───▶│                   │                │               │
  │                  │◀── allowed ─────│                   │                │               │
  │                  │                 │─login(req,ip)────▶│                │               │
  │                  │                 │                   │─findByUsername▶│               │
  │                  │                 │                   │               │────SELECT─────▶│
  │                  │                 │                   │               │◀───User────────│
  │                  │                 │                   │─verifyPassword │               │
  │                  │                 │                   │─generateToken()────────────────▶
  │                  │                 │                   │◀──JWT + RefreshToken───────────│
  │                  │                 │                   │─saveRefreshToken───────────────▶│
  │                  │                 │◀─AuthResponse─────│                │               │
  │◀──200 + JWT ─────│                 │                   │                │               │
```

### 5.3.2 Create Mission Flow

```
Client          JwtFilter         MissionController   MissionService    DroneRepo     MissionRepo
  │                 │                   │                  │                │               │
  │─POST /missions─▶│                   │                  │                │               │
  │                 │─validateJWT()─────│                  │                │               │
  │                 │◀──SecurityCtx─────│                  │                │               │
  │                 │                   │─createMission()─▶│                │               │
  │                 │                   │                  │─findDroneById─▶│               │
  │                 │                   │                  │◀───Drone───────│               │
  │                 │                   │                  │─validateStatus │               │
  │                 │                   │                  │─buildMission() │               │
  │                 │                   │                  │─saveWaypoints  │               │
  │                 │                   │                  │────────────────────────────────▶│
  │                 │                   │◀──MissionDTO─────│                │               │
  │◀──201 Created───│                   │                  │                │               │
```

### 5.3.3 Real-Time Telemetry Flow

```
Drone/Bridge    TelemetryController  TelemetryService    TelemetryRepo   WebSocketHandler  Client(s)
  │                   │                   │                   │                  │              │
  │─POST /telemetry──▶│                   │                   │                  │              │
  │                   │─ingestTelemetry()▶│                   │                  │              │
  │                   │                   │─saveTelemetry()──▶│                  │              │
  │                   │                   │◀──Saved────────────│                  │              │
  │                   │                   │─broadcastTelemetry()──────────────────▶│              │
  │                   │                   │                   │                  │─sendToAll()──▶│
  │                   │◀──201──────────────│                   │                  │              │
  │◀──201 Response────│                   │                   │                  │              │
```

### 5.3.4 Password Reset Flow

```
Client          AuthController      PasswordResetService    EmailService    Database
  │                  │                    │                      │               │
  │─POST /auth/forgot│                    │                      │               │
  │─  password──────▶│                    │                      │               │
  │                  │─initiateReset()───▶│                      │               │
  │                  │                    │─generateToken()       │               │
  │                  │                    │─saveToken()──────────────────────────▶│
  │                  │                    │─sendResetEmail()──────▶│              │
  │                  │                    │                       │─sendMail()    │
  │◀──200 OK─────────│                    │                       │               │
  │                  │                    │                       │               │
  │─POST /auth/reset │                    │                       │               │
  │─  password──────▶│                    │                       │               │
  │                  │─confirmReset()────▶│                       │               │
  │                  │                    │─validateToken()──────────────────────▶│
  │                  │                    │─hashNewPassword()     │               │
  │                  │                    │─updatePassword()─────────────────────▶│
  │                  │                    │─invalidateToken()────────────────────▶│
  │◀──200 OK─────────│                    │                       │               │
```

## 5.4 Data Flow Description

### 5.4.1 Telemetry Ingestion Pipeline

```
Physical Drone / Simulator
        │
        ▼ HTTP POST /api/telemetry
┌───────────────────┐
│  TelemetryController   │  ← Request validation (Bean Validation)
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  TelemetryService │  ← Business logic, drone lookup, entity mapping
└────────┬──────────┘
         │
         ├──▶ PostgreSQL (persist telemetry record)
         │
         ├──▶ Update Drone position in-place (lat/lon/alt/battery)
         │
         ├──▶ Caffeine Cache (invalidate stale drone cache)
         │
         └──▶ WebSocket Broadcast (push JSON to all /ws/telemetry subscribers)
```

### 5.4.2 Authentication Token Lifecycle

```
Registration
    │
    ▼ BCrypt hash stored in DB
    
Login Request
    │
    ▼ Credential verification
    ├──▶ JWT (short-lived, 24h)     → sent to client, used in Authorization header
    └──▶ Refresh Token (7 days)    → stored in DB + sent to client

API Request
    │
    ▼ JwtFilter validates JWT
    └──▶ Spring SecurityContext populated with UserDetails + Roles

Token Expiry
    │
    ▼ Client sends Refresh Token to /api/auth/refresh
    ├──▶ Server validates DB record
    ├──▶ Issues new JWT
    └──▶ Optionally rotates Refresh Token

Logout
    │
    ▼ Refresh Token invalidated in DB
```

## 5.5 State Models

### 5.5.1 Drone State Machine

```
                ┌─────────────┐
                │    OFFLINE  │◀──── Hardware disconnected
                └──────┬──────┘
                       │ Power on + connect
                       ▼
                ┌─────────────┐
                │    IDLE     │◀──── Mission complete / Land
                └──────┬──────┘
                       │ TAKEOFF command
                       ▼
                ┌─────────────┐
                │  TAKING_OFF │
                └──────┬──────┘
                       │ Altitude reached
                       ▼
              ┌────────────────────┐
    HOVER ────│    IN_FLIGHT       │──── WAYPOINT
              └────────┬───────────┘
                       │
              ┌────────┴──────────┐
              │                   │
              ▼                   ▼
         ┌─────────┐       ┌──────────────────┐
         │HOVERING │       │ RETURNING_HOME   │◀── RTH command
         └─────────┘       └──────────────────┘
                                  │
                                  ▼
                           ┌────────────┐
                           │  LANDING   │
                           └─────┬──────┘
                                 │
                ┌────────────────▼─────────────────┐
                │                                  │
                ▼                                  ▼
         ┌────────────┐                  ┌──────────────────┐
         │    IDLE    │                  │    EMERGENCY     │◀── EMERGENCY_STOP
         └────────────┘                  └──────────────────┘
```

### 5.5.2 Mission State Machine

```
  PLANNED ──(start)──▶ IN_PROGRESS ──(complete)──▶ COMPLETED
     │                      │
     │                      ├──(pause)──▶ PAUSED ──(resume)──▶ IN_PROGRESS
     │                      │
     │                      └──(abort)──▶ ABORTED
     │
     └──(cancel before start)──▶ ABORTED
     
  IN_PROGRESS ──(error/timeout)──▶ FAILED
```

### 5.5.3 Command State Machine

```
  PENDING ──(dispatched)──▶ SENT ──(ACK received)──▶ ACKNOWLEDGED
                                                            │
                                  ┌─────────────────────────┤
                                  ▼                         ▼
                             EXECUTED                    FAILED
  
  Any state ──(operator cancel)──▶ CANCELLED
```

---

---

# 6. SYSTEM EVOLUTION

## 6.1 Planned Near-Term Enhancements

### 6.1.1 AirSim / SITL Integration

The codebase already includes stub controllers (`AirSimBridgeController`, `NavRLController`) and service classes (`AirSimBridgeManager`, `NavRLBridgeService`) for integration with the Microsoft AirSim UAV simulation environment and a Neural Reinforcement Learning (NavRL) autonomous navigation bridge. The next phase of development will implement these bridges to allow the command center to control simulated drones in a physics-accurate 3D environment, providing a safe testbed for mission planning algorithms.

### 6.1.2 AI-Assisted Mission Planning

A NavRL integration layer will enable autonomous waypoint optimisation and obstacle avoidance planning. Operators will be able to define mission objectives at a high level (e.g., "survey this bounding box") and the system will compute an optimal flight path, taking into account terrain, battery constraints, and no-fly zones.

### 6.1.3 Live Video Feed Integration

Integration with drone video feeds via WebRTC or HLS streaming will be added, allowing operators to view live camera output from any drone within the command center UI.

### 6.1.4 Multi-Operator Coordination

Support for simultaneous multi-operator sessions, including real-time conflict detection when two operators attempt to command the same drone, with lock/reservation semantics.

### 6.1.5 Geofencing

Operators will be able to define virtual geographic boundaries (polygons and circles). The system will alert operators and optionally issue RTH commands when a drone approaches or breaches a geofence boundary.

## 6.2 Medium-Term Evolution

### 6.2.1 Push Notifications

Integration with Firebase Cloud Messaging (FCM) / Apple Push Notification Service (APNs) to deliver real-time alerts to operators' devices when critical events occur (battery critical, emergency stop triggered, drone lost connection).

### 6.2.2 Multi-Tenancy

Evolving the data model to support multiple organisations within the same deployment, with complete data isolation between tenants. This would allow the platform to be offered as a SaaS product.

### 6.2.3 Distributed Cache

Replacing the in-process Caffeine cache with a Redis cluster to support horizontal backend scaling. The service layer already uses Spring Cache annotations (`@Cacheable`, `@CacheEvict`) which are cache-provider agnostic — migration requires only configuration changes.

### 6.2.4 Kubernetes Deployment

Providing a Helm chart for Kubernetes deployment, enabling autoscaling of the backend pod based on CPU and WebSocket connection count metrics exposed via Spring Actuator to Prometheus.

### 6.2.5 Time-Series Database

For high-frequency telemetry ingestion (multiple messages per second per drone at scale), migrating the telemetry table to a dedicated time-series database such as TimescaleDB (a PostgreSQL extension) or InfluxDB, while retaining the existing REST API contract.

## 6.3 Long-Term Vision

| Timeframe | Initiative |
|---|---|
| Year 1 | Full AirSim bridge + NavRL autonomous planning |
| Year 1 | Mobile push notifications + geofencing |
| Year 2 | Multi-tenancy + SaaS model |
| Year 2 | Kubernetes + Redis + Prometheus/Grafana observability stack |
| Year 3 | Video streaming (WebRTC) per drone |
| Year 3 | Regulatory compliance module (FAA Part 107 / EASA U-Space) |
| Year 3+ | Swarm coordination: multi-drone formation flying and collaborative missions |

## 6.4 Maintenance Considerations

### 6.4.1 Dependency Management

All dependencies are managed via Apache Maven. The `spring-boot-starter-parent` BOM provides aligned dependency versions. Security advisories should be monitored via GitHub Dependabot or OWASP Dependency-Check, and patch upgrades should be applied within 14 days of a CVE disclosure.

### 6.4.2 Schema Migration Governance

Any schema change must be introduced as a new Flyway versioned migration script (`V{n}__description.sql`). Destructive migrations (column drops, table renames) must be preceded by a deprecation migration in the previous release to allow rolling deployments.

### 6.4.3 API Versioning

As the API evolves, breaking changes will be introduced under a new version prefix (e.g., `/api/v2/`) while `/api/v1/` is maintained for a deprecation period of no less than 90 days.

### 6.4.4 Monitoring and Alerting

Spring Actuator exposes health, metrics, info, and environment endpoints. In production, these should feed a Prometheus scrape job, with Grafana dashboards for:
- JVM heap usage
- HTTP request rate and error rate (4xx/5xx)
- Active WebSocket connections
- Cache hit/miss rates
- Database connection pool utilisation

---

---

# 7. APPENDICES

## Appendix A — Technology Stack Summary

### A.1 Backend Dependencies

| Library | Purpose | Version |
|---|---|---|
| Spring Boot | Application framework | 4.0.2 |
| Spring Data JPA | ORM / database access | Managed by BOM |
| Spring Security | Authentication, authorization | Managed by BOM |
| Spring WebSocket | Real-time telemetry | Managed by BOM |
| Spring Actuator | Health monitoring | Managed by BOM |
| Spring Mail | Email notifications | Managed by BOM |
| Spring AMQP | RabbitMQ integration | Managed by BOM |
| Spring Cache | Caching abstraction | Managed by BOM |
| PostgreSQL JDBC | Database driver | Managed by BOM |
| Flyway Core | Schema migration | Managed by BOM |
| Flyway PostgreSQL | PostgreSQL dialect for Flyway | Managed by BOM |
| Caffeine | In-memory cache implementation | Managed by BOM |
| Bucket4j | Token bucket rate limiting | 8.10.1 |
| JJWT API | JWT creation and parsing | 0.11.5 |
| JJWT Impl | JWT implementation | 0.11.5 |
| JJWT Jackson | JWT Jackson integration | 0.11.5 |
| SpringDoc OpenAPI | Swagger UI generation | 2.8.4 |
| Lombok | Boilerplate reduction | Managed by BOM |
| H2 Database | In-memory DB for testing | Test scope |

### A.2 Frontend Dependencies

| Library | Purpose | Version |
|---|---|---|
| flutter_riverpod | State management | ^2.4.9 |
| riverpod_annotation | Code generation annotations | ^2.3.3 |
| dio | HTTP client with interceptors | ^5.4.0 |
| web_socket_channel | WebSocket client | ^2.4.0 |
| shared_preferences | Local preferences storage | ^2.2.2 |
| flutter_secure_storage | Encrypted JWT storage | ^9.0.0 |
| fl_chart | Telemetry line/bar charts | ^0.66.0 |
| flutter_map | Interactive map (OpenStreetMap) | ^6.1.0 |
| latlong2 | Geographic coordinate types | ^0.9.0 |
| lottie | JSON-based animations | ^3.0.0 |
| shimmer | Loading skeleton effects | ^3.0.0 |
| animate_do | Widget entrance animations | ^3.1.2 |
| intl | Date/number formatting | ^0.18.1 |
| go_router | Declarative navigation | ^13.0.1 |
| equatable | Value equality for models | ^2.0.5 |
| json_annotation | JSON serialisation annotations | ^4.8.1 |
| google_fonts | Rajdhani + Space Mono fonts | ^6.1.0 |
| iconsax | Tactical icon set | ^0.0.8 |
| flutter_svg | SVG asset rendering | ^2.0.9 |

---

## Appendix B — REST API Endpoint Catalogue

### B.1 Authentication (`/api/auth`)

| Method | Path | Auth Required | Role | Description |
|---|---|---|---|---|
| POST | `/api/auth/register` | No | — | Register a new user account |
| POST | `/api/auth/login` | No | — | Authenticate and receive JWT + refresh token |
| POST | `/api/auth/refresh` | No | — | Exchange refresh token for new JWT |
| POST | `/api/auth/logout` | Yes | Any | Invalidate refresh token |
| POST | `/api/auth/forgot-password` | No | — | Request password reset email |
| POST | `/api/auth/reset-password` | No | — | Confirm password reset with token |
| GET | `/api/auth/me` | Yes | Any | Get current authenticated user profile |

### B.2 Drone Management (`/api/drones`)

| Method | Path | Auth Required | Role | Description |
|---|---|---|---|---|
| POST | `/api/drones` | Yes | ADMIN, OPERATOR | Register a new drone |
| GET | `/api/drones` | Yes | Any | List all drones (paginated) |
| GET | `/api/drones/all` | Yes | Any | List all drones (unpaginated) |
| GET | `/api/drones/{id}` | Yes | Any | Get drone by UUID |
| PUT | `/api/drones/{id}` | Yes | ADMIN, OPERATOR | Update drone details |
| DELETE | `/api/drones/{id}` | Yes | ADMIN | Delete drone |
| GET | `/api/drones/status/{status}` | Yes | Any | Filter by connection status |
| GET | `/api/drones/flight-status/{status}` | Yes | Any | Filter by flight status |

### B.3 Mission Management (`/api/missions`)

| Method | Path | Auth Required | Role | Description |
|---|---|---|---|---|
| POST | `/api/missions` | Yes | ADMIN, OPERATOR | Create a new mission |
| GET | `/api/missions/{id}` | Yes | Any | Get mission by UUID |
| GET | `/api/missions` | Yes | Any | List all missions (paginated) |
| GET | `/api/missions/status/{status}` | Yes | Any | Filter missions by status |
| GET | `/api/missions/drone/{droneId}` | Yes | Any | List missions for a drone |
| PUT | `/api/missions/{id}` | Yes | ADMIN, OPERATOR | Update mission |
| DELETE | `/api/missions/{id}` | Yes | ADMIN | Delete mission |
| POST | `/api/missions/{id}/start` | Yes | ADMIN, OPERATOR | Start mission |
| POST | `/api/missions/{id}/pause` | Yes | ADMIN, OPERATOR | Pause mission |
| POST | `/api/missions/{id}/resume` | Yes | ADMIN, OPERATOR | Resume mission |
| POST | `/api/missions/{id}/complete` | Yes | ADMIN, OPERATOR | Mark mission complete |
| POST | `/api/missions/{id}/abort` | Yes | ADMIN, OPERATOR | Abort mission |
| GET | `/api/missions/{id}/waypoints` | Yes | Any | Get mission waypoints |
| POST | `/api/missions/{id}/waypoints` | Yes | ADMIN, OPERATOR | Add waypoint to mission |
| DELETE | `/api/missions/{id}/waypoints/{wId}` | Yes | ADMIN, OPERATOR | Remove waypoint |

### B.4 Commands (`/api/commands`)

| Method | Path | Auth Required | Role | Description |
|---|---|---|---|---|
| POST | `/api/commands` | Yes | ADMIN, OPERATOR, PILOT | Issue a command to a drone |
| GET | `/api/commands/drone/{droneId}` | Yes | Any | Get command history for drone |
| PUT | `/api/commands/{id}/status` | Yes | ADMIN, OPERATOR | Update command status |

### B.5 Telemetry (`/api/telemetry`)

| Method | Path | Auth Required | Role | Description |
|---|---|---|---|---|
| POST | `/api/telemetry` | No | — | Ingest telemetry data from drone |
| GET | `/api/telemetry/drone/{id}/latest` | Yes | Any | Get latest telemetry record |
| GET | `/api/telemetry/drone/{id}` | Yes | Any | Get telemetry history (paginated) |
| GET | `/api/telemetry/drone/{id}/range` | Yes | Any | Get telemetry in time range |
| GET | `/api/telemetry/drone/{id}/flight-path` | Yes | Any | Get flight path coordinates |

### B.6 User Management (`/api/users`)

| Method | Path | Auth Required | Role | Description |
|---|---|---|---|---|
| GET | `/api/users` | Yes | ADMIN | List all users |
| GET | `/api/users/{id}` | Yes | ADMIN, OPERATOR | Get user by UUID |
| PUT | `/api/users/{id}` | Yes | ADMIN | Update user |
| DELETE | `/api/users/{id}` | Yes | ADMIN | Deactivate user |

### B.7 System (`/actuator`)

| Method | Path | Auth Required | Role | Description |
|---|---|---|---|---|
| GET | `/actuator/health` | No | — | Application health status |
| GET | `/actuator/info` | No | — | Application build information |
| GET | `/actuator/metrics` | Yes | ADMIN | JVM and application metrics |
| GET | `/actuator/env` | Yes | ADMIN | Environment properties |
| GET | `/actuator/loggers` | Yes | ADMIN | Logger level management |

### B.8 WebSocket

| Endpoint | Protocol | Description |
|---|---|---|
| `/ws/telemetry` | WebSocket / SockJS | Real-time telemetry broadcast. All subscribers receive telemetry JSON when data is ingested. |

---

## Appendix C — Database Schema Reference

### C.1 Table: `users`

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK, DEFAULT gen_random_uuid() | User unique identifier |
| `username` | VARCHAR(50) | NOT NULL, UNIQUE | Login username |
| `password` | VARCHAR(255) | NOT NULL | BCrypt hashed password |
| `email` | VARCHAR(100) | NOT NULL, UNIQUE | Email address |
| `enabled` | BOOLEAN | NOT NULL, DEFAULT true | Account active flag |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Registration timestamp |

### C.2 Table: `user_roles`

| Column | Type | Constraints | Description |
|---|---|---|---|
| `user_id` | UUID | FK → users(id), CASCADE | User reference |
| `role` | VARCHAR(50) | NOT NULL | Role name (e.g., ROLE_ADMIN) |

### C.3 Table: `drones`

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | Drone unique identifier |
| `serial_number` | VARCHAR(50) | NOT NULL, UNIQUE | Hardware serial number |
| `name` | VARCHAR(100) | NOT NULL | Display name |
| `model_type` | VARCHAR(100) | NOT NULL | Manufacturer model string |
| `firmware_version` | VARCHAR(50) | | Current firmware version |
| `connection_status` | VARCHAR(50) | NOT NULL | CONNECTED / DISCONNECTED / etc. |
| `flight_status` | VARCHAR(50) | NOT NULL | IDLE / IN_FLIGHT / etc. |
| `battery_level` | DOUBLE | DEFAULT 100.0 | Battery % |
| `latitude` | DOUBLE | DEFAULT 0.0 | Current latitude |
| `longitude` | DOUBLE | DEFAULT 0.0 | Current longitude |
| `altitude` | DOUBLE | DEFAULT 0.0 | Current altitude (metres) |
| `autonomy_level` | VARCHAR(50) | | MANUAL / SEMI_AUTONOMOUS / AUTONOMOUS |
| `navigation_mode` | VARCHAR(50) | | GPS / WAYPOINT / MANUAL / etc. |
| `failsafe_enabled` | BOOLEAN | DEFAULT true | Failsafe system active |
| `obstacle_detected` | BOOLEAN | DEFAULT false | Obstacle avoidance flag |
| `last_heartbeat` | TIMESTAMPTZ | | Last heartbeat received |
| `registered_at` | TIMESTAMPTZ | DEFAULT NOW() | Registration time |
| `home_latitude` | DOUBLE | | RTH home latitude |
| `home_longitude` | DOUBLE | | RTH home longitude |
| `home_altitude` | DOUBLE | | RTH home altitude |

### C.4 Table: `missions`

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | Mission identifier |
| `name` | VARCHAR(100) | NOT NULL | Mission name |
| `description` | TEXT | | Mission description |
| `status` | VARCHAR(50) | NOT NULL | Mission status enum |
| `priority` | INTEGER | DEFAULT 0 | Priority (higher = more urgent) |
| `start_time` | TIMESTAMPTZ | | Actual start time |
| `end_time` | TIMESTAMPTZ | | Actual end time |
| `estimated_duration_minutes` | INTEGER | | Planned duration |
| `actual_duration_minutes` | INTEGER | | Actual duration |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | | Last update timestamp |
| `assigned_drone_id` | UUID | FK → drones(id) | Assigned drone |
| `created_by_id` | UUID | FK → users(id) | Creating user |

### C.5 Table: `waypoints`

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | Waypoint identifier |
| `latitude` | DOUBLE | NOT NULL | Waypoint latitude |
| `longitude` | DOUBLE | NOT NULL | Waypoint longitude |
| `altitude` | DOUBLE | NOT NULL | Waypoint altitude (metres) |
| `sequence_order` | INTEGER | NOT NULL | Order in mission sequence |
| `action` | VARCHAR(50) | | HOVER / TAKE_PHOTO / SCAN / etc. |
| `hover_duration_seconds` | INTEGER | DEFAULT 0 | Time to hover at waypoint |
| `speed` | DOUBLE | | Target speed (m/s) |
| `heading` | DOUBLE | | Target heading (degrees) |
| `reached` | BOOLEAN | DEFAULT false | Reached confirmation |
| `reached_at` | TIMESTAMPTZ | | Time waypoint was reached |
| `mission_id` | UUID | FK → missions(id), CASCADE | Parent mission |

### C.6 Table: `telemetry`

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Record identifier |
| `timestamp` | TIMESTAMPTZ | Measurement time |
| `latitude` | DOUBLE | Position latitude |
| `longitude` | DOUBLE | Position longitude |
| `altitude` | DOUBLE | Altitude (metres) |
| `speed` | DOUBLE | Ground speed (m/s) |
| `heading` | DOUBLE | Heading (degrees 0-360) |
| `battery_level` | DOUBLE | Battery % |
| `signal_strength` | DOUBLE | Signal strength % |
| `gps_satellites` | INTEGER | Satellites in view |
| `temperature` | DOUBLE | Ambient temperature (°C) |
| `humidity` | DOUBLE | Relative humidity % |
| `wind_speed` | DOUBLE | Wind speed (m/s) |
| `wind_direction` | DOUBLE | Wind direction (degrees) |
| `flight_mode` | VARCHAR(50) | Active flight mode |
| `drone_id` | UUID FK | Source drone |

### C.7 Table: `sensors`

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Sensor identifier |
| `name` | VARCHAR(100) | Sensor name |
| `type` | VARCHAR(50) | CAMERA / LIDAR / GPS / IMU / etc. |
| `status` | VARCHAR(50) | ACTIVE / INACTIVE / ERROR / CALIBRATING |
| `last_reading` | TEXT | Last sensor reading (JSON) |
| `last_reading_at` | TIMESTAMPTZ | Time of last reading |
| `drone_id` | UUID FK | Parent drone |

### C.8 Table: `commands`

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Command identifier |
| `command_type` | VARCHAR(50) | TAKEOFF / LAND / RTH / etc. |
| `status` | VARCHAR(50) | PENDING / SENT / EXECUTED / FAILED |
| `payload` | TEXT | JSON command parameters |
| `response` | TEXT | Drone response message |
| `issued_at` | TIMESTAMPTZ | When command was issued |
| `executed_at` | TIMESTAMPTZ | When command was sent to drone |
| `completed_at` | TIMESTAMPTZ | When drone confirmed execution |
| `drone_id` | UUID FK | Target drone |
| `issued_by_id` | UUID FK | Issuing user |

---

## Appendix D — Enumeration Reference

| Enum | Values |
|---|---|
| `ConnectionStatus` | CONNECTED, DISCONNECTED, CONNECTING, ERROR, UNKNOWN |
| `FlightStatus` | IDLE, TAKING_OFF, IN_FLIGHT, LANDING, HOVERING, RETURNING_HOME, EMERGENCY, OFFLINE |
| `MissionStatus` | PLANNED, IN_PROGRESS, COMPLETED, ABORTED, FAILED, PAUSED |
| `CommandType` | TAKEOFF, LAND, RETURN_TO_HOME, HOVER, GO_TO_WAYPOINT, START_MISSION, ABORT_MISSION, EMERGENCY_STOP, SET_ALTITUDE, SET_SPEED, ROTATE, TAKE_PHOTO, START_STREAMING, STOP_STREAMING |
| `CommandStatus` | PENDING, SENT, ACKNOWLEDGED, EXECUTED, FAILED, CANCELLED |
| `WaypointAction` | HOVER, TAKE_PHOTO, SCAN, INSPECT, DELIVER, LAND, NONE |
| `SensorType` | CAMERA, LIDAR, GPS, BAROMETER, IMU, RADAR, THERMAL_CAMERA, ULTRASONIC, MAGNETOMETER |
| `AutonomyLevel` | MANUAL, SEMI_AUTONOMOUS, AUTONOMOUS, EMERGENCY |
| `NavigationMode` | MANUAL, GPS, WAYPOINT, FOLLOW_ME, ORBIT, RETURN_HOME |
| `Role` | ROLE_ADMIN, ROLE_OPERATOR, ROLE_PILOT, ROLE_VIEWER, ROLE_MAINTENANCE, ROLE_RESEARCHER |

---

## Appendix E — Configuration Reference

### E.1 Key `application.properties` Parameters

| Key | Default / Example | Description |
|---|---|---|
| `server.port` | `8080` | HTTP listening port |
| `spring.datasource.url` | `jdbc:postgresql://localhost:5432/drone_db` | Database URL |
| `spring.jpa.hibernate.ddl-auto` | `update` | Schema management (Flyway handles migrations) |
| `spring.flyway.enabled` | `true` | Enable Flyway migrations |
| `spring.flyway.locations` | `classpath:db/migration` | Migration script location |
| `jwt.secret` | *(environment variable)* | JWT signing secret (min 256-bit) |
| `jwt.expiration` | `86400000` | JWT expiry in milliseconds (24h) |
| `jwt.refresh-expiration` | `604800000` | Refresh token expiry (7 days) |
| `spring.cache.type` | `caffeine` | Cache provider |
| `spring.mail.host` | `smtp.gmail.com` | SMTP server |
| `spring.rabbitmq.host` | `localhost` | RabbitMQ host |
| `management.endpoints.web.exposure.include` | `health,info,metrics` | Exposed Actuator endpoints |

### E.2 Environment Variables (Secrets)

The following values must **never** be committed to source control and must be provided via environment variables or a secrets manager:

- `DB_PASSWORD` — PostgreSQL database password
- `JWT_SECRET` — JWT HMAC signing key (minimum 32 characters)
- `MAIL_PASSWORD` — SMTP account password
- `RABBITMQ_PASSWORD` — RabbitMQ user password

---

## Appendix F — Flutter Screen Inventory

| Screen | Route | Description |
|---|---|---|
| Splash Screen | `/` | Animated boot screen with JWT validation redirect |
| Login Screen | `/login` | Authentication form with validation |
| Register Screen | `/register` | New account creation form |
| Dashboard | `/dashboard` | Fleet overview: stat cards, drone list summary |
| Drone List | `/drones` | Paginated drone list with status indicators |
| Drone Detail | `/drones/:id` | Full drone data: telemetry charts, sensor grid, command panel |
| Mission List | `/missions` | Mission list with status badges |
| Mission Detail | `/missions/:id` | Mission overview, waypoint list, status controls |
| Create Mission | `/missions/create` | Mission creation form with waypoint builder |
| Map Screen | `/map` | Interactive OpenStreetMap with drone markers |
| Settings | `/settings` | User preferences and logout |

---

---

# 8. INDEX

| Term | Section |
|---|---|
| AirSim | §3.2.2, §6.1.1 |
| API Documentation (Swagger) | §3.2.1, §4.1.6, Appendix B |
| Authentication | §3.2.3, §4.1.1, §5.3.1 |
| Bucket4j | §3.2.1, §3.2.3, §4.1.6 |
| BCrypt | §4.2.2 |
| Cache (Caffeine) | §3.2.1, §4.1.2, §5.4.1 |
| Command Types | §4.1.4, Appendix D |
| CORS | §3.2.3 |
| Database Schema | §5.2, Appendix C |
| Docker | §3.4, Appendix E |
| Drone Entity | §4.1.2, Appendix C.3 |
| Drone State Machine | §5.5.1 |
| Email (Password Reset) | §4.1.1, §5.3.4 |
| Entity-Relationship Model | §5.2 |
| Enumerations | Appendix D |
| Flyway | §3.2.1, §4.1.6, §4.2.3, §4.2.6 |
| Flutter | §3.3, Appendix F |
| Functional Requirements | §4.1 |
| GoRouter | §3.3.1 |
| HSTS | §3.2.3, §4.2.2 |
| JWT | §1.4, §3.2.3, §4.1.1, §5.4.2 |
| Lombok | Appendix A.1 |
| Mission State Machine | §5.5.2 |
| Non-Functional Requirements | §4.2 |
| OpenAPI | §3.2.1, Appendix B |
| PostgreSQL | §3.2.1, Appendix C |
| RabbitMQ | §3.2.1, §4.1.6, §4.2.5 |
| RBAC | §2.1, §3.2.4 |
| Rate Limiting | §3.2.3, §4.1.6, §4.2.2 |
| Refresh Token | §3.2.3, §4.1.1, §5.4.2 |
| REST API | §3.2.2, Appendix B |
| Riverpod | §3.3.1, §3.3.2 |
| Role | §2.1, §3.2.4, Appendix D |
| Sensor | §4.1.5, Appendix C.7 |
| Sequence Diagrams | §5.3 |
| Spring Actuator | §3.2.1, §4.1.6, Appendix B.7 |
| Spring Boot | §3.2.1 |
| Spring Security | §3.2.3 |
| Telemetry | §4.1.5, §5.3.3, §5.4.1, Appendix C.6 |
| UAV | §1.1, §1.4 |
| Use Cases | §2.3, §5.1 |
| User Requirements | Chapter 2 |
| User Stories | §2.2 |
| Waypoint | §4.1.3, Appendix C.5 |
| WebSocket | §3.2.1, §3.2.2, §4.1.5, §5.3.3, Appendix B.8 |

---

*End of Document*

---

**Document Control**

| Version | Date | Author | Description |
|---|---|---|---|
| 0.1 | 2026-04-01 | Development Team | Initial draft |
| 0.5 | 2026-04-15 | Development Team | Architecture and requirements complete |
| 1.0 | 2026-04-26 | Development Team | Final version for submission |
