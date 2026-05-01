# syntax=docker/dockerfile:1.6
# ---------- Build stage ----------
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace

# Cache dependencies first
COPY pom.xml ./
COPY .mvn .mvn
COPY mvnw mvnw.cmd ./
RUN mvn -B -q dependency:go-offline

# Build the app
COPY src src
RUN mvn -B -q -DskipTests clean package \
    && cp target/*.jar /workspace/app.jar

# ---------- Runtime stage ----------
FROM eclipse-temurin:17-jre-jammy
WORKDIR /app

# Non-root user for safety
RUN useradd -r -u 1001 -g root spring
USER 1001

COPY --from=build /workspace/app.jar /app/app.jar

EXPOSE 8080

# Health check uses Spring Actuator
HEALTHCHECK --interval=10s --timeout=3s --start-period=40s --retries=10 \
  CMD wget --quiet --spider http://localhost:8080/actuator/health || exit 1

ENV JAVA_OPTS=""
ENTRYPOINT ["sh","-c","java $JAVA_OPTS -jar /app/app.jar"]
