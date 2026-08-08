---
id: quarkus-onion-architecture
title: "From Hello World to Onion Architecture: Refactoring Step by Step With ArchUnit"
summary: Refactor a plain Java hello world into a full Onion Architecture — domain, application, an existing CLI consumer, and Quarkus as an optional second consumer — with ArchUnit guarding every step so the boundary never silently rots.
date: 2026-08-07
image: /images/quarkus-onion-header.png
---

# From Hello World to Onion Architecture: Refactoring Step by Step With ArchUnit

Onion Architecture keeps your business logic independent of the framework, so the same core can serve a CLI today and Quarkus tomorrow without changing a line of domain code. You reach that structure the same way you refactor any real system — one guarded step at a time — and ArchUnit makes each step prove itself before you take the next one.

Every step below shows four things: the architecture concept it introduces, the exact `main` after the change, the ArchUnit rule, and the build output that proves the step is green. The whole path was validated with a real `mvn test` at every step, on Java 25 with Quarkus 3.33.3 and ArchUnit 1.5.0 — but nothing here needs a bleeding-edge toolchain; the refactoring technique is what matters.

## Where We Start: Hello World

One class. No framework, no packages, no ports. This is the "existing system" we are going to refactor.

```java
// src/main/java/com/example/HelloWorld.java
package com.example;

public class HelloWorld {

    public static void main(String[] args) {
        System.out.println("Hello, World!");
    }
}
```

The greeting text, the formatting rule, and the output all live in one method. It works, and it is trivial — but the moment this program needs a name from a database, or a second consumer, the tangle becomes painful.

Build proof:

```
$ mvn compile
[INFO] BUILD SUCCESS

$ java -cp target/classes com.example.HelloWorld
Hello, World!
```

## Step 1: The Guardrail Comes First

**Architecture concept: the boundary is declared before it is needed.** Do not add structure first. Add ArchUnit first, so the destination is defined before you start moving code. The rule states the dream state from day one: the domain and application layers must never touch the framework.

Add the test dependencies to `pom.xml`:

```xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.10.2</version>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>com.tngtech.archunit</groupId>
    <artifactId>archunit-junit5</artifactId>
    <version>1.5.0</version>
    <scope>test</scope>
</dependency>
```

**`main` does not change.** The entry point is untouched in this step.

**The first ArchUnit rule.** `@AnalyzeClasses` tells ArchUnit which packages to inspect. `@ArchTest` marks a rule that JUnit runs on every build:

```java
// src/test/java/com/example/ArchitectureTest.java
package com.example;

import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

@AnalyzeClasses(packages = "com.example")
class ArchitectureTest {

    @ArchTest
    static final ArchRule core_is_framework_free = noClasses()
            .that().resideInAnyPackage("com.example.domain..", "com.example.application..")
            .should().dependOnClassesThat()
            .resideInAnyPackage("jakarta..", "io.quarkus..", "com.example.infrastructure..")
            .allowEmptyShould(true);
}
```

Two details matter here:

- The packages `com.example.domain` and `com.example.application` do not exist yet. ArchUnit does not care. The rule matches nothing and passes. That is the point: the boundary is declared **before** the architecture is built.
- ArchUnit by default **fails** a rule that matched no classes (`failOnEmptyShould`). This protects against vacuous rules, and it is exactly the behavior we must opt out of while the layers are empty. `.allowEmptyShould(true)` says: "pass for now, start enforcing as soon as real classes match."

Build proof:

```
$ mvn test
Running com.example.ArchitectureTest
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0

Results:
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0

BUILD SUCCESS
```

The guardrail is in place. Every remaining step happens underneath it.

## Step 2: The Domain Layer — Value Object and Domain Logic

**Architecture concept: the domain layer holds business rules.** The greeting is not just a string. It always starts with "Hello,", it greets a name, and a blank name falls back to "World". Those rules belong in a `domain` package that contains no framework imports. A value object (`Greeting`) carries immutable data; a domain service (`Greeter`) owns the rules. This is the classic case for a Java `record` — the value object's boilerplate (constructor, accessor, `equals`, `hashCode`, `toString`) disappears, and the domain intent stays readable:

```java
// src/main/java/com/example/domain/model/Greeting.java
package com.example.domain.model;

import java.util.Objects;

public record Greeting(String message) {

    public Greeting {
        Objects.requireNonNull(message, "message must not be null");
    }
}
```

```java
// src/main/java/com/example/domain/service/Greeter.java
package com.example.domain.service;

import com.example.domain.model.Greeting;

public final class Greeter {

    public Greeting greet(String name) {
        if (name == null || name.isBlank()) {
            name = "World";
        }
        return new Greeting("Hello, " + name.trim() + "!");
    }
}
```

**`main` transforms** — it shrinks to a single call:

```java
// src/main/java/com/example/HelloWorld.java
package com.example;

import com.example.domain.service.Greeter;

public class HelloWorld {

    public static void main(String[] args) {
        var greeter = new Greeter();
        System.out.println(greeter.greet("Onion").message());
    }
}
```

Note the deliberate behavior change: the name is no longer baked into the string. It is passed in, and later steps will decide where it comes from. And note `var` — the constructor call on the right already names the type, so the local variable declares no redundant type.

**ArchUnit: unchanged from Step 1.** The rule still governs. Both new classes are pure Java, so it has nothing to flag.

Build proof:

```
$ mvn test
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0   -- in com.example.ArchitectureTest
BUILD SUCCESS

$ java -cp target/classes com.example.HelloWorld
Hello, Onion!
```

## Step 3: The Port — Dependency Inversion

**Architecture concept: the port is a seam.** The greeter needs a name, but it must not care where the name comes from. The domain declares what it needs as an interface — a **port** — and the outside world provides implementations, called **adapters**. This inverts the dependency: the domain defines the contract, the adapters obey it.

```java
// src/main/java/com/example/domain/service/GreetingRepository.java
package com.example.domain.service;

public interface GreetingRepository {

    String findName();
}
```

**`main` transforms** — the name now flows through the port. For now the caller supplies a temporary inline implementation:

```java
// src/main/java/com/example/HelloWorld.java
package com.example;

import com.example.domain.service.Greeter;
import com.example.domain.service.GreetingRepository;

public class HelloWorld {

    public static void main(String[] args) {
        GreetingRepository repository = () -> "Onion";
        var greeter = new Greeter();
        System.out.println(greeter.greet(repository.findName()).message());
    }
}
```

**ArchUnit: unchanged.** The interface is pure Java, so the Step 1 rule still has nothing to flag.

Build proof:

```
$ mvn test
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0   -- in com.example.ArchitectureTest
BUILD SUCCESS

$ java -cp target/classes com.example.HelloWorld
Hello, Onion!
```

## Step 4: The Application Layer — the Use Case

**Architecture concept: orchestration leaves the caller.** The caller still holds the repository, the greeter, and the wiring. In a larger system that is exactly the coordination logic you want to centralize. The **application layer** sits between the domain and the outside world: it knows the ports and the domain logic, and it decides how they combine. It is still framework-free.

```java
// src/main/java/com/example/application/GreetingUseCase.java
package com.example.application;

import com.example.domain.model.Greeting;
import com.example.domain.service.Greeter;
import com.example.domain.service.GreetingRepository;

public final class GreetingUseCase {

    private final GreetingRepository repository;
    private final Greeter greeter;

    public GreetingUseCase(GreetingRepository repository, Greeter greeter) {
        this.repository = repository;
        this.greeter = greeter;
    }

    public Greeting generateGreeting() {
        return greeter.greet(repository.findName());
    }
}
```

**`main` transforms** — it now sees a single entry point. The orchestration disappears from the caller:

```java
// src/main/java/com/example/HelloWorld.java
package com.example;

import com.example.application.GreetingUseCase;
import com.example.domain.service.Greeter;
import com.example.domain.service.GreetingRepository;

public class HelloWorld {

    public static void main(String[] args) {
        GreetingRepository repository = () -> "Onion";
        var greeter = new Greeter();
        var useCase = new GreetingUseCase(repository, greeter);
        System.out.println(useCase.generateGreeting().message());
    }
}
```

**ArchUnit: unchanged — and now it has real teeth.** The core (domain + application) contains zero framework imports, and the Step 1 rule would fail the build the moment anyone imported `jakarta` into these packages.

Build proof:

```
$ mvn test
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0   -- in com.example.ArchitectureTest
BUILD SUCCESS

$ java -cp target/classes com.example.HelloWorld
Hello, Onion!
```

## Step 5: The Existing CLI Becomes an Adapter

**Architecture concept: consumers live in the outer ring.** The "caller" from all previous steps is really an existing command-line application. It moves into the adapter ring (`infrastructure.cli`), gets a named in-memory repository, and becomes a full consumer of the core. Each consumer is responsible for its own composition — its own wiring of the core classes.

```java
// src/main/java/com/example/infrastructure/cli/InMemoryGreetingRepository.java
package com.example.infrastructure.cli;

import com.example.domain.service.GreetingRepository;

public final class InMemoryGreetingRepository implements GreetingRepository {

    @Override
    public String findName() {
        return "Onion";
    }
}
```

**`main` transforms** — it relocates and specializes. The generic `HelloWorld` becomes `GreetingCli`, the CLI's own composition root:

```java
// src/main/java/com/example/infrastructure/cli/GreetingCli.java
package com.example.infrastructure.cli;

import com.example.application.GreetingUseCase;
import com.example.domain.service.Greeter;
import com.example.domain.service.GreetingRepository;

public final class GreetingCli {

    public static void main(String[] args) {
        var repository = new InMemoryGreetingRepository();
        var greeter = new Greeter();
        var useCase = new GreetingUseCase(repository, greeter);
        var greeting = useCase.generateGreeting();
        System.out.println(greeting.message());
    }
}
```

Because the core is pure Java, the CLI runs with nothing but the JDK on the classpath:

```
$ java -cp target/classes com.example.infrastructure.cli.GreetingCli
Hello, Onion!
```

No Quarkus. No CDI. No containers.

The core is also testable without any framework. A plain JUnit test wires the port with a lambda stub:

```java
// src/test/java/com/example/application/GreetingUseCaseTest.java
package com.example.application;

import com.example.domain.service.Greeter;
import com.example.domain.service.GreetingRepository;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingUseCaseTest {

    @Test
    void generatesGreetingFromPort() {
        GreetingRepository repository = () -> "Onion";
        var useCase = new GreetingUseCase(repository, new Greeter());
        assertEquals("Hello, Onion!", useCase.generateGreeting().message());
    }
}
```

**ArchUnit transforms.** The structure now exists, so the architecture test grows a second rule. The built-in `onionArchitecture()` rule — the one from the ArchUnit user guide — checks the dependency directions between layers, and the `cli` adapter is registered. The Step 1 rule stays as the stricter zero-bleed net:

```java
// src/test/java/com/example/ArchitectureTest.java
package com.example;

import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import static com.tngtech.archunit.library.Architectures.onionArchitecture;

@AnalyzeClasses(packages = "com.example")
class ArchitectureTest {

    @ArchTest
    static final ArchRule onion_architecture_is_respected = onionArchitecture()
            .domainModels("..domain.model..")
            .domainServices("..domain.service..")
            .applicationServices("..application..")
            .adapter("cli", "..infrastructure.cli..");

    @ArchTest
    static final ArchRule core_is_framework_free = noClasses()
            .that().resideInAnyPackage("com.example.domain..", "com.example.application..")
            .should().dependOnClassesThat()
            .resideInAnyPackage("jakarta..", "io.quarkus..", "com.example.infrastructure..")
            .allowEmptyShould(true);
}
```

Build proof:

```
$ mvn test
Running com.example.application.GreetingUseCaseTest
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0, Time elapsed: 0.016 s
Running com.example.ArchitectureTest
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0

Results:
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0

BUILD SUCCESS
```

The CLI is now a registered adapter in the architecture.

## Step 6: Quarkus as a Second Consumer

**Architecture concept: the same core, another adapter set.** Adding Quarkus changes no domain and no application code. Quarkus gets its own adapters: a CDI-registered port implementation in the database adapter, a JAX-RS endpoint in the web adapter, and a composition root that wires the pure core.

First, the Quarkus dependencies join `pom.xml`. Quarkus 3.33.x is the current LTS line — it supports Java 25 and ships with Mandrel/GraalVM 25 for native image builds, so the same core can go AOT later without a stack change:

```xml
<dependency>
    <groupId>io.quarkus</groupId>
    <artifactId>quarkus-rest</artifactId>
</dependency>
<dependency>
    <groupId>io.quarkus</groupId>
    <artifactId>quarkus-arc</artifactId>
</dependency>
```

The port gets a second implementation, registered as a CDI bean:

```java
// src/main/java/com/example/infrastructure/database/SqlGreetingRepository.java
package com.example.infrastructure.database;

import com.example.domain.service.GreetingRepository;
import jakarta.enterprise.context.ApplicationScoped;

@ApplicationScoped
public class SqlGreetingRepository implements GreetingRepository {

    @Override
    public String findName() {
        return "Onion";
    }
}
```

The REST endpoint knows nothing about the domain internals — only the use case:

```java
// src/main/java/com/example/infrastructure/web/GreetingResource.java
package com.example.infrastructure.web;

import com.example.application.GreetingUseCase;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;

@Path("/hello")
public class GreetingResource {

    private final GreetingUseCase useCase;

    public GreetingResource(GreetingUseCase useCase) {
        this.useCase = useCase;
    }

    @GET
    @Produces(MediaType.TEXT_PLAIN)
    public String hello() {
        var greeting = useCase.generateGreeting();
        return greeting.message();
    }
}
```

The composition root wires the pure core. Producer methods are the only place that calls `new` on the core classes:

```java
// src/main/java/com/example/infrastructure/web/QuarkusConfig.java
package com.example.infrastructure.web;

import com.example.application.GreetingUseCase;
import com.example.domain.service.Greeter;
import com.example.domain.service.GreetingRepository;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.inject.Produces;

@ApplicationScoped
public class QuarkusConfig {

    @Produces
    public Greeter greeter() {
        return new Greeter();
    }

    @Produces
    public GreetingUseCase greetingUseCase(GreetingRepository repository, Greeter greeter) {
        return new GreetingUseCase(repository, greeter);
    }
}
```

Note what `QuarkusConfig` deliberately does **not** do: it never references `SqlGreetingRepository` directly. It wires through the port interface. ArchUnit's `onionArchitecture()` treats each named adapter as a leaf that nothing may access — an adapter may not reach into another adapter. A `QuarkusConfig` that instantiated `new SqlGreetingRepository()` would fail the build, which is exactly the design feedback you want.

**ArchUnit transforms** — the two new adapters are registered:

```java
// src/test/java/com/example/ArchitectureTest.java
package com.example;

import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import static com.tngtech.archunit.library.Architectures.onionArchitecture;

@AnalyzeClasses(packages = "com.example")
class ArchitectureTest {

    @ArchTest
    static final ArchRule onion_architecture_is_respected = onionArchitecture()
            .domainModels("..domain.model..")
            .domainServices("..domain.service..")
            .applicationServices("..application..")
            .adapter("database", "..infrastructure.database..")
            .adapter("web", "..infrastructure.web..")
            .adapter("cli", "..infrastructure.cli..");

    @ArchTest
    static final ArchRule core_is_framework_free = noClasses()
            .that().resideInAnyPackage("com.example.domain..", "com.example.application..")
            .should().dependOnClassesThat()
            .resideInAnyPackage("jakarta..", "io.quarkus..", "com.example.infrastructure..")
            .allowEmptyShould(true);
}
```

The end-to-end test boots the real Quarkus server and hits `GET /hello`:

```java
// src/test/java/com/example/GreetingResourceTest.java
package com.example;

import io.quarkus.test.junit.QuarkusTest;
import org.junit.jupiter.api.Test;

import static io.restassured.RestAssured.given;
import static org.hamcrest.CoreMatchers.is;

@QuarkusTest
class GreetingResourceTest {

    @Test
    void helloReturnsOnionGreeting() {
        given()
                .when().get("/hello")
                .then()
                .statusCode(200)
                .body(is("Hello, Onion!"));
    }
}
```

Build proof:

```
$ mvn clean test
Running com.example.GreetingResourceTest
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0, Time elapsed: 0.645 s
Running com.example.application.GreetingUseCaseTest
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0, Time elapsed: 0.003 s
Running com.example.ArchitectureTest
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0, Time elapsed: 0.436 s

Results:
Tests run: 4, Failures: 0, Errors: 0, Skipped: 0

BUILD SUCCESS
```

The CLI from Step 5 still runs untouched, and the Quarkus consumer answers over HTTP:

```
$ java -cp target/classes com.example.infrastructure.cli.GreetingCli
Hello, Onion!

$ curl http://localhost:8080/hello
Hello, Onion!
```

Two consumers, one core. The CLI proves the core is framework-free; Quarkus proves the core is framework-friendly.

## The Final Structure

```
src/main/java/com/example/
├── domain/                          # pure Java, no framework imports
│   ├── model/
│   │   └── Greeting.java            # record — immutable value object
│   └── service/
│       ├── GreetingRepository.java  # port (interface)
│       └── Greeter.java             # domain logic
├── application/                     # pure Java, no framework imports
│   └── GreetingUseCase.java         # orchestrates port + domain logic
└── infrastructure/                  # adapters, framework allowed
    ├── cli/
    │   ├── GreetingCli.java         # existing CLI consumer
    │   └── InMemoryGreetingRepository.java
    ├── database/
    │   └── SqlGreetingRepository.java  # CDI bean, implements the port
    └── web/
        ├── GreetingResource.java    # JAX-RS endpoint @Path("/hello")
        └── QuarkusConfig.java       # composition root, @Produces wiring
```

## The Guardrails Catch Real Leaks

A guardrail you cannot trigger is not a guardrail. To prove the rules fire, deliberately leak a framework type into the domain:

```java
import jakarta.ws.rs.core.MediaType;  // the leak

public Greeting greet(String name) {
    ...
    return new Greeting("Hello, " + name.trim() + " " + MediaType.valueOf("text/plain") + "!");
}
```

`mvn test` fails with:

```
Architecture Violation [Priority: MEDIUM] - Rule 'no classes that reside in any package
['com.example.domain..', 'com.example.application..'] should depend on classes that reside
in any package ['com.example.infrastructure..', 'jakarta..', 'io.quarkus..']' was violated:
Method <com.example.domain.service.Greeter.greet(java.lang.String)> calls method
<jakarta.ws.rs.core.MediaType.valueOf(java.lang.String)> in (Greeter.java:12)
```

One subtle gotcha while testing this: `MediaType.TEXT_PLAIN` is a `static final String` compile-time constant. `javac` inlines it as the literal `"text/plain"`, so the bytecode contains **no** reference to `jakarta.ws.rs.core.MediaType` and ArchUnit sees nothing. A method call like `MediaType.valueOf(...)` leaves a real bytecode reference and is caught instantly. Architecture tests inspect bytecode, not source, so inline constants are invisible to them.

## How This Applies to a Real Refactor

The path you just walked is the path for an existing system:

1. **Add the framework-free rule first.** It is trivially green and defines the destination before you start moving code.
2. **Extract the domain.** Move the rules and the values into pure Java classes. The build stays green.
3. **Cut the seams.** Replace direct data access with port interfaces defined in the domain.
4. **Centralize orchestration.** Move coordination into use cases in the application layer.
5. **Move consumers out.** Each consumer — CLI, REST, whatever exists today — becomes an adapter in the outer ring.
6. **Let the rule grow.** Register each adapter as it appears, so the architecture test describes what actually exists.

Every step keeps `mvn test` green. That is the difference between a refactor and a rewrite: you can stop at any step, ship it, and the guardrails stay behind to keep the boundary honest.

The full runnable project lives in `_code/quarkus-onion-architecture`. Run `mvn clean test`, then run the CLI with the plain JDK, then try to slip a `jakarta` import into the domain and watch the build refuse.

## References

- **ArchUnit User Guide, §8.1.2 Onion Architecture** — the `onionArchitecture()` API and its semantics. The rule in this article follows that example. [archunit.org/userguide/html/000_Index.html#_onion_architecture](https://www.archunit.org/userguide/html/000_Index.html#_onion_architecture)
- **ArchUnit User Guide, §10.4 Fail Rules on Empty Should** — why `.allowEmptyShould(true)` exists and when to use it. [archunit.org/userguide/html/000_Index.html#_fail_rules_on_empty_should](https://www.archunit.org/userguide/html/000_Index.html#_fail_rules_on_empty_should)
- **Jeffrey Palermo, "The Onion Architecture"** — the original definition that ArchUnit's rule implements. [jeffreypalermo.com/2008/07/the-onion-architecture-part-1](https://jeffreypalermo.com/2008/07/the-onion-architecture-part-1/)
