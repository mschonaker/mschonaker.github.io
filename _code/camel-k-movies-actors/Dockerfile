FROM eclipse-temurin:17-jre

ARG H2_VERSION=2.2.224
ADD https://repo1.maven.org/maven2/com/h2database/h2/${H2_VERSION}/h2-${H2_VERSION}.jar /opt/h2.jar

COPY entrypoint.sh /opt/entrypoint.sh
RUN chmod +x /opt/entrypoint.sh

EXPOSE 9092 8082

ENTRYPOINT ["/opt/entrypoint.sh"]