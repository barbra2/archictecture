FROM openjdk:17-alpine
COPY binaries/*.jar app.jar
ENV SERVER_PORT=8080
ENTRYPOINT ["java", "-jar", "app.jar"]