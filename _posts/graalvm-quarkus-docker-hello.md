---
id: graalvm-quarkus-hello
title: Hello World with GraalVM, Quarkus, Maven, and Docker
summary: Build a native Java microservice using GraalVM and Quarkus with a multi-stage Dockerfile — no local GraalVM installation required.
date: 2026-07-17
image: /images/graalvm-quarkus-header.png
---

# Hello World with GraalVM, Quarkus, Maven, and Docker

Quarkus is a Kubernetes-native Java framework, and GraalVM compiles Java ahead-of-time into native executables that start in milliseconds. Together they make Java feel like a scripting language — instant startup, tiny memory footprint.

This guide walks through creating a Hello World REST endpoint with Quarkus and Maven, then packaging it as a native Docker image using GraalVM in a multi-stage build. You don't need GraalVM installed locally; everything runs in containers.

## Prerequisites

- Java 17+ and Maven (for project scaffolding only)
- Docker Desktop

## Step 1: Generate the Project

Use the Quarkus Maven plugin to scaffold a new project:

```bash
mvn io.quarkus.platform:quarkus-maven-plugin:3.37.3:create \
  -DprojectGroupId=com.example \
  -DprojectArtifactId=graalvm-quarkus-hello \
  -DclassName="com.example.GreetingResource" \
  -Dpath="/hello" \
  -Dextensions="resteasy-reactive"
```

This creates a directory named `graalvm-quarkus-hello` with:

```
graalvm-quarkus-hello/
  pom.xml
  src/
    main/
      java/com/example/GreetingResource.java
      docker/Dockerfile.native
      docker/Dockerfile.native-micro
      resources/application.properties
    test/
      java/com/example/
```

The generated `GreetingResource` is a simple JAX-RS endpoint:

```java
package com.example;

import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;

@Path("/hello")
public class GreetingResource {

    @GET
    @Produces(MediaType.TEXT_PLAIN)
    public String hello() {
        return "Hello from Quarkus REST";
    }
}
```

## Step 2: Multi-Stage Dockerfile

The generated `Dockerfile.native` expects you to build the native binary locally first. Instead, we'll rewrite it as a multi-stage build that builds the native binary inside Docker using the official Quarkus GraalVM builder image.

Create `src/main/docker/Dockerfile.native`:

```dockerfile
####
# Multi-stage Docker build for Quarkus native image with GraalVM.
#
# Build the image with:
#
# docker build -f src/main/docker/Dockerfile.native -t quarkus/graalvm-quarkus-hello .
#
# Then run the container using:
#
# docker run -i --rm -p 8080:8080 quarkus/graalvm-quarkus-hello
#
# Builder stage: uses the official Quarkus GraalVM CE builder image (UBI 9)
FROM quay.io/quarkus/ubi9-quarkus-graalvmce-builder-image:jdk-21 AS build
WORKDIR /workspace

# Copy pom.xml and maven wrapper
COPY pom.xml .
COPY .mvn .mvn
COPY mvnw mvnw.cmd .

# Download dependencies (cached across builds if pom.xml hasn't changed)
RUN ./mvnw dependency:go-offline -B

# Copy source and build native image
COPY src src
RUN ./mvnw package -Dnative -DskipTests -B

# Runtime stage: minimal UBI 9 image
FROM registry.access.redhat.com/ubi9/ubi-minimal:latest
WORKDIR /work/
RUN chown 1001 /work \
    && chmod "g+rwX" /work \
    && chown 1001:root /work
COPY --from=build --chown=1001:root --chmod=0755 /workspace/target/*-runner /work/application

EXPOSE 8080
USER 1001

ENTRYPOINT ["./application", "-Dquarkus.http.host=0.0.0.0"]
```

Key decisions in this Dockerfile:

- **Builder stage**: Uses `quay.io/quarkus/ubi9-quarkus-graalvmce-builder-image:jdk-21`, the official Quarkus GraalVM CE builder image. It includes GraalVM JDK 21 with `native-image`, Maven, and all necessary tools. The `ubi9` variant uses Red Hat's UBI 9 base, matching the runtime stage.
- **Layer caching**: Dependencies are downloaded in a separate `RUN` step before copying source code. Docker caches this layer and only re-downloads when `pom.xml` changes.
- **Runtime stage**: Uses `ubi9/ubi-minimal`, a ~30MB base image with just the essentials needed to run a native binary (glibc, zlib, etc.).
- **Security**: Runs as non-root user `1001`.

Also update `.dockerignore` to allow source files into the build context:

```
.git
.gitignore
.mvn/wrapper/maven-wrapper.jar
target/
*.md
```

## Step 3: Build the Docker Image

```bash
cd graalvm-quarkus-hello
docker build -f src/main/docker/Dockerfile.native -t quarkus/graalvm-quarkus-hello .
```

The first build takes a few minutes — it downloads the builder image and all Maven dependencies. Subsequent builds are faster thanks to Docker's layer caching.

During the build, you'll see GraalVM compiling the native binary:

```
GraalVM Native Image: Generating 'graalvm-quarkus-hello-1.0.0-SNAPSHOT-runner' (executable)...
========================================================================================================================
[1/8] Initializing...                                                                                    (2.5s @ 0.15GB)
[2/8] Performing analysis...  [*****]                                                                   (13.8s @ 1.26GB)
[3/8] Building universe...                                                                               (2.1s @ 1.48GB)
[4/8] Parsing methods...      [*]                                                                        (1.3s @ 1.55GB)
[5/8] Inlining methods...     [***]                                                                      (0.7s @ 1.55GB)
[6/8] Compiling methods...    [***]                                                                     (11.1s @ 1.39GB)
[7/8] Layouting methods...    [**]                                                                       (2.1s @ 1.19GB)
[8/8] Creating image...       [**]                                                                       (2.7s @ 1.74GB)
------------------------------------------------------------------------------------------------------------------------
47.17MB in total
------------------------------------------------------------------------------------------------------------------------
Finished generating in 36.7s.
```

The resulting native binary is 47MB, and the final Docker image is around 160MB (including the UBI 9 minimal base).

## Step 4: Run and Test

```bash
docker run -i --rm -p 8080:8080 quarkus/graalvm-quarkus-hello
```

In another terminal:

```bash
curl http://localhost:8080/hello
```

Response:

```
Hello from Quarkus REST
```

## Why This Matters

Native compilation with GraalVM changes the character of Java applications:

| Metric | Traditional JVM | GraalVM Native |
|--------|----------------|----------------|
| Startup time | 3-5 seconds | < 0.1 seconds |
| Image size | ~200MB (JRE + fatjar) | ~50MB (binary) |
| Memory (idle) | 100-200MB | ~5-20MB |
| Ready for serverless | No | Yes |

This is why Quarkus + GraalVM is a popular choice for serverless, edge computing, and containerized microservices — the cold start problem disappears.

## Alternative: Build with JVM Mode

If you don't need native performance, you can run the standard JVM Dockerfile:

```bash
docker build -f src/main/docker/Dockerfile.jvm -t quarkus/graalvm-quarkus-hello-jvm .
docker run -i --rm -p 8080:8080 quarkus/graalvm-quarkus-hello-jvm
```

The JVM image is faster to build but slower to start and uses more memory.

## References

- [Quarkus Building Native Image Guide](https://quarkus.io/guides/building-native-image) — official docs
- [Quarkus Container Images](https://quarkus.io/guides/container-image) — available base images
- [GraalVM Native Image](https://www.graalvm.org/latest/reference-manual/native-image/) — official reference
- [quarkus-images repository](https://github.com/quarkusio/quarkus-images) — source for the builder images
