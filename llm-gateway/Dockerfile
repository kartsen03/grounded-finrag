# Build with the Maven wrapper, run on a JRE as an unprivileged user.
FROM eclipse-temurin:21-jdk AS build
WORKDIR /src
COPY .mvn .mvn
COPY mvnw pom.xml ./
RUN chmod +x mvnw && ./mvnw -q -B dependency:go-offline
COPY src src
RUN ./mvnw -q -B package -DskipTests

FROM eclipse-temurin:21-jre
RUN useradd --system --uid 10001 gateway
COPY --from=build /src/target/llm-gateway-0.0.1-SNAPSHOT.jar /app/app.jar
USER 10001
ENV GATEWAY_BIND_ADDRESS=0.0.0.0
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
