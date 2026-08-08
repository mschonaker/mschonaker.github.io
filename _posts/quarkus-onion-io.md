---
id: quarkus-onion-io
title: "Onion Architecture, Part 2: JSON, HTML, Streams, and File Uploads"
summary: Grow the onion from Part 1 with the I/O the real world demands — JSON POST bodies, an HTML table view, Server-Sent Events, and multipart CSV uploads — and watch every single format land in the adapter ring. The Part 1 rules survive untouched, and one new ArchUnit rule turns the article's thesis — I/O formats are adapter concerns — into a build guard.
date: 2026-08-09
image: /images/quarkus-onion-io-header.png
---

# Onion Architecture, Part 2: JSON, HTML, Streams, and File Uploads

In [Part 1](/#article/quarkus-onion-architecture), we took a plain Java hello world and refactored it step by step into an Onion Architecture — domain, application, and an outer ring of adapters — with ArchUnit guarding every boundary. We stopped when Quarkus and a CLI served the same core. But the greeting API only ever produced a plain text line. Real systems send JSON in, expect HTML tables out, stream data over time, and accept file uploads. This article runs those four experiments against the same onion.

The through-line: **every input and output format is an adapter concern.** JSON binding, HTML rendering, Server-Sent Events, and multipart parsing all belong in `infrastructure`. The core sees only plain Java records and JDK types. The two architecture rules from Part 1 survive this article *byte-for-byte unchanged* — and at the end we add a third rule that turns the through-line into a build guard.

## Where We Start: The Part 1 Core

The onion from Part 1 already has its three layers wired in `src/main/java/com/example/`:

```
domain/                          # pure Java, no framework imports
├── model/Greeting.java          # record — immutable value object
└── service/
    ├── GreetingRepository.java  # port (interface)
    └── Greeter.java             # domain logic
application/
└── GreetingUseCase.java         # orchestrates port + domain logic
infrastructure/                  # adapters, framework allowed
├── cli/                         # the plain-JDK CLI consumer
├── database/SqlGreetingRepository.java
└── web/                         # Quarkus: GreetingResource + QuarkusConfig
```

The core is tiny because the domain is tiny. That is about to change.

## Step 1: A Domain Worth Talking About

**Architecture concept: the domain grows, the boundary does not move.** A greeting is too thin to exercise JSON bodies, tables, streams, and uploads. We add a `Note` domain — a title, a body, and a creation time. The rules are deliberately simple: title and body must not be blank, title caps at 80 characters, body caps at 2000. Those rules belong in the domain, not in the resource class, not in the CSV parser.

```java
// src/main/java/com/example/domain/model/NewNote.java
package com.example.domain.model;

public record NewNote(String title, String body) {
}
```

`NewNote` is the unvalidated input. The domain's validator owns the rules and returns the first problem as an `Optional<String>`, so a caller can decide what "rejected" means — important for the import use case later:

```java
// src/main/java/com/example/domain/model/Note.java
package com.example.domain.model;

import java.time.Instant;

public record Note(Long id, String title, String body, Instant createdAt) {

    public Note {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title must not be blank");
        }
        if (body == null || body.isBlank()) {
            throw new IllegalArgumentException("body must not be blank");
        }
        if (createdAt == null) {
            throw new IllegalArgumentException("createdAt must not be null");
        }
    }
}
```

```java
// src/main/java/com/example/domain/service/NoteValidator.java
package com.example.domain.service;

import com.example.domain.model.NewNote;

import java.util.Optional;

public final class NoteValidator {

    public Optional<String> validate(NewNote note) {
        if (note.title() == null || note.title().isBlank()) {
            return Optional.of("title must not be blank");
        }
        if (note.body() == null || note.body().isBlank()) {
            return Optional.of("body must not be blank");
        }
        if (note.title().length() > 80) {
            return Optional.of("title must be at most 80 characters");
        }
        if (note.body().length() > 2000) {
            return Optional.of("body must be at most 2000 characters");
        }
        return Optional.empty();
    }
}
```

The port follows the pattern from Part 1 — the domain declares what it needs, adapters implement it:

```java
// src/main/java/com/example/domain/service/NoteRepository.java
package com.example.domain.service;

import com.example.domain.model.Note;

import java.util.List;

public interface NoteRepository {

    long nextId();

    Note save(Note note);

    List<Note> findAll();
}
```

**ArchUnit: unchanged.** The Part 1 rule already names `..domain.model..` and `..domain.service..`. The new classes are pure Java, so the framework-free rule has nothing to flag.

## Step 2: The Application Layer — Four Use Cases

**Architecture concept: orchestration stays in the application layer, in plain Java.** Every experiment below is served by a use case. None of them imports `jakarta`, `quarkus`, or `io.smallrye`. The single-note path validates and saves:

```java
// src/main/java/com/example/application/CreateNoteUseCase.java
package com.example.application;

import com.example.domain.model.NewNote;
import com.example.domain.model.Note;
import com.example.domain.service.NoteRepository;
import com.example.domain.service.NoteValidator;

import java.time.Instant;

public final class CreateNoteUseCase {

    private final NoteRepository repository;
    private final NoteValidator validator;

    public CreateNoteUseCase(NoteRepository repository, NoteValidator validator) {
        this.repository = repository;
        this.validator = validator;
    }

    public Note create(NewNote newNote) {
        var error = validator.validate(newNote);
        if (error.isPresent()) {
            throw new ValidationException(error.get());
        }
        var id = repository.nextId();
        return repository.save(new Note(id, newNote.title(), newNote.body(), Instant.now()));
    }
}
```

`ValidationException` is an application-layer type, so the use case does not leak `IllegalArgumentException` into the API's error contract:

```java
// src/main/java/com/example/application/ValidationException.java
package com.example.application;

public class ValidationException extends RuntimeException {

    public ValidationException(String message) {
        super(message);
    }
}
```

Listing is a straight pass-through. Note the JDK `Stream` return type — the core is allowed to speak in streams; it just must not know *which* wire format will consume them:

```java
// src/main/java/com/example/application/ListNotesUseCase.java
package com.example.application;

import com.example.domain.model.Note;
import com.example.domain.service.NoteRepository;

import java.util.List;

public final class ListNotesUseCase {

    private final NoteRepository repository;

    public ListNotesUseCase(NoteRepository repository) {
        this.repository = repository;
    }

    public List<Note> listAll() {
        return repository.findAll();
    }
}
```

```java
// src/main/java/com/example/application/StreamNotesUseCase.java
package com.example.application;

import com.example.domain.model.Note;
import com.example.domain.service.NoteRepository;

import java.util.stream.Stream;

public final class StreamNotesUseCase {

    private final NoteRepository repository;

    public StreamNotesUseCase(NoteRepository repository) {
        this.repository = repository;
    }

    public Stream<Note> streamAll() {
        return repository.findAll().stream();
    }
}
```

The import use case validates every row, saves the valid ones, and reports the rest. This is where the validator's `Optional<String>` pays off — rejected rows become data, not exceptions:

```java
// src/main/java/com/example/application/ImportNotesUseCase.java
package com.example.application;

import com.example.domain.model.NewNote;
import com.example.domain.model.Note;
import com.example.domain.service.NoteRepository;
import com.example.domain.service.NoteValidator;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

public final class ImportNotesUseCase {

    private final NoteRepository repository;
    private final NoteValidator validator;

    public ImportNotesUseCase(NoteRepository repository, NoteValidator validator) {
        this.repository = repository;
        this.validator = validator;
    }

    public ImportResult importAll(List<NewNote> drafts) {
        var accepted = 0;
        var rejected = 0;
        var errors = new ArrayList<String>();
        for (var draft : drafts) {
            var error = validator.validate(draft);
            if (error.isPresent()) {
                rejected++;
                errors.add(error.get());
                continue;
            }
            var id = repository.nextId();
            repository.save(new Note(id, draft.title(), draft.body(), Instant.now()));
            accepted++;
        }
        return new ImportResult(accepted, rejected, List.copyOf(errors));
    }
}
```

The result is another plain record in the application layer:

```java
// src/main/java/com/example/application/ImportResult.java
package com.example.application;

import java.util.List;

public record ImportResult(int accepted, int rejected, List<String> errors) {
}
```

**ArchUnit: unchanged.** The `..application..` layer was registered in Part 1. Nothing new to do.

## The Adapter Ring: One Database, Four Web Experiments

The in-memory repository is the port's adapter. It is the only place a `Note` becomes state:

```java
// src/main/java/com/example/infrastructure/database/InMemoryNoteRepository.java
package com.example.infrastructure.database;

import com.example.domain.model.Note;
import com.example.domain.service.NoteRepository;
import jakarta.enterprise.context.ApplicationScoped;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicLong;

@ApplicationScoped
public class InMemoryNoteRepository implements NoteRepository {

    private final AtomicLong nextId = new AtomicLong(1);
    private final List<Note> notes = new ArrayList<>();

    public InMemoryNoteRepository() {
        seed("Onion", "Layers, from the inside out: domain, application, adapters.");
        seed("Hexagonal", "The same core, different ports and adapters.");
        seed("ArchUnit", "Guardrails prove the boundary holds on every build.");
    }

    private void seed(String title, String body) {
        notes.add(new Note(nextId.getAndIncrement(), title, body, Instant.now()));
    }

    @Override
    public long nextId() {
        return nextId.getAndIncrement();
    }

    @Override
    public Note save(Note note) {
        notes.add(note);
        return note;
    }

    @Override
    public List<Note> findAll() {
        return List.copyOf(notes);
    }
}
```

Three seed notes keep the table and the stream from being empty demos. The wiring lives in `QuarkusConfig`, the composition root from Part 1, which now produces the four use cases and the parser:

```java
// src/main/java/com/example/infrastructure/web/QuarkusConfig.java
package com.example.infrastructure.web;

import com.example.application.CreateNoteUseCase;
import com.example.application.GreetingUseCase;
import com.example.application.ImportNotesUseCase;
import com.example.application.ListNotesUseCase;
import com.example.application.StreamNotesUseCase;
import com.example.domain.service.Greeter;
import com.example.domain.service.GreetingRepository;
import com.example.domain.service.NoteRepository;
import com.example.domain.service.NoteValidator;
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

    @Produces
    public NoteValidator noteValidator() {
        return new NoteValidator();
    }

    @Produces
    public CreateNoteUseCase createNoteUseCase(NoteRepository repository, NoteValidator validator) {
        return new CreateNoteUseCase(repository, validator);
    }

    @Produces
    public ListNotesUseCase listNotesUseCase(NoteRepository repository) {
        return new ListNotesUseCase(repository);
    }

    @Produces
    public StreamNotesUseCase streamNotesUseCase(NoteRepository repository) {
        return new StreamNotesUseCase(repository);
    }

    @Produces
    public ImportNotesUseCase importNotesUseCase(NoteRepository repository, NoteValidator validator) {
        return new ImportNotesUseCase(repository, validator);
    }

    @Produces
    public CsvNoteParser csvNoteParser() {
        return new CsvNoteParser();
    }
}
```

### Experiment 1: JSON POST Input

**Architecture concept: the JSON shape lives in the adapter.** The resource accepts a web-layer DTO, translates it to the domain's `NewNote`, and lets the use case decide what happens. Jackson binds the request body to a record in `infrastructure.web` — the adapter owns the wire shape, so the domain never gains a JSON dependency:

```java
// src/main/java/com/example/infrastructure/web/NewNoteRequest.java
package com.example.infrastructure.web;

public record NewNoteRequest(String title, String body) {
}
```

```java
// src/main/java/com/example/infrastructure/web/NoteResource.java  (create)
@POST
@Consumes(MediaType.APPLICATION_JSON)
@Produces(MediaType.APPLICATION_JSON)
public Response create(NewNoteRequest request) {
    try {
        var note = createNote.create(new NewNote(request.title(), request.body()));
        return Response.status(Response.Status.CREATED).entity(note).build();
    } catch (ValidationException e) {
        return Response.status(Response.Status.BAD_REQUEST)
                .entity(new ApiError(e.getMessage()))
                .build();
    }
}
```

The happy path returns `201 Created` with the persisted note. The domain rule surfaces as a `400` with a JSON error body — again, the adapter's job to translate:

```
$ curl -i -X POST -H "Content-Type: application/json" \
  -d '{"title":"JSON POST","body":"hello onion"}' http://localhost:8080/notes
HTTP/1.1 201 Created
Content-Type: application/json

{"id":4,"title":"JSON POST","body":"hello onion","createdAt":"2026-08-08T04:22:26.450437Z"}

$ curl -X POST -H "Content-Type: application/json" \
  -d '{"title":" ","body":"x"}' http://localhost:8080/notes
{"message":"title must not be blank"}
```

Nothing about HTTP, JSON, or status codes exists below the `infrastructure.web` package.

### Experiment 2: HTML Response With a Table

**Architecture concept: the same use case, a different adapter.** `GET /notes/html` calls the identical `ListNotesUseCase.listAll()` as the JSON list endpoint — and the web adapter decides the representation. A tiny view class renders the table. Escaping is part of the adapter's job, because the adapter owns the output format:

```java
// src/main/java/com/example/infrastructure/web/NotesHtmlView.java
package com.example.infrastructure.web;

import com.example.domain.model.Note;

import java.util.List;

public final class NotesHtmlView {

    public static String render(List<Note> notes) {
        var sb = new StringBuilder();
        sb.append("<!DOCTYPE html>");
        sb.append("<html><head><meta charset=\"utf-8\"><title>Notes</title></head><body>");
        sb.append("<h1>Notes</h1>");
        sb.append("<table border=\"1\" cellpadding=\"4\" cellspacing=\"0\">");
        sb.append("<thead><tr><th>id</th><th>title</th><th>body</th><th>created</th></tr></thead>");
        sb.append("<tbody>");
        for (var note : notes) {
            sb.append("<tr>");
            sb.append("<td>").append(note.id()).append("</td>");
            sb.append("<td>").append(escape(note.title())).append("</td>");
            sb.append("<td>").append(escape(note.body())).append("</td>");
            sb.append("<td>").append(note.createdAt()).append("</td>");
            sb.append("</tr>");
        }
        sb.append("</tbody></table>");
        sb.append("</body></html>");
        return sb.toString();
    }

    private static String escape(String value) {
        return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;");
    }
}
```

```java
// src/main/java/com/example/infrastructure/web/NoteResource.java  (list + html)
@GET
@Produces(MediaType.APPLICATION_JSON)
public List<com.example.domain.model.Note> list() {
    return listNotes.listAll();
}

@GET
@Path("/html")
@Produces(MediaType.TEXT_HTML)
public String listHtml() {
    return NotesHtmlView.render(listNotes.listAll());
}
```

```
$ curl http://localhost:8080/notes/html
<!DOCTYPE html><html>...<table border="1" cellpadding="4" cellspacing="0"><thead><tr><th>id</th><th>title</th><th>body</th><th>created</th></tr></thead><tbody><tr><td>1</td><td>Onion</td>...
```

One use case, two representations. The core never imports a `<table>` tag.

### Experiment 3: Streams

**Architecture concept: the core returns a `Stream<Note>`; the adapter picks the wire format.** `StreamNotesUseCase` speaks only JDK types. The resource converts that stream into a Mutiny `Multi` — SSE is a web concern, so Mutiny appears in `infrastructure.web` and nowhere else. The `500ms` delay exists purely to make the streaming visible in a terminal:

```java
// src/main/java/com/example/infrastructure/web/NoteResource.java  (stream)
@GET
@Path("/stream")
@Produces(MediaType.SERVER_SENT_EVENTS)
public Multi<com.example.domain.model.Note> stream() {
    return Multi.createFrom()
            .iterable(() -> streamNotes.streamAll().iterator())
            .call(item -> Uni.createFrom().item(item)
                    .onItem().delayIt().by(Duration.ofMillis(500)));
}
```

```
$ curl -N http://localhost:8080/notes/stream
data:{"id":1,"title":"Onion","body":"Layers, from the inside out: domain, application, adapters.","createdAt":"..."}

data:{"id":2,"title":"Hexagonal",...

data:{"id":3,"title":"ArchUnit",...
```

The use case never mentions events, channels, or reactive types. If a consumer later wants the same data as NDJSON or a WebSocket, only this resource method changes.

### Experiment 4: File Uploads

**Architecture concept: parsing is an adapter concern; validation is a core concern.** The multipart part arrives as a RESTEasy Reactive `FileUpload`. The resource reads the file, the CSV parser turns bytes into `NewNote` drafts, and `ImportNotesUseCase` decides which drafts are valid:

```java
// src/main/java/com/example/infrastructure/web/CsvNoteParser.java
package com.example.infrastructure.web;

import com.example.domain.model.NewNote;

import java.util.ArrayList;
import java.util.List;

public final class CsvNoteParser {

    public List<NewNote> parse(String csv) {
        var drafts = new ArrayList<NewNote>();
        for (var line : csv.lines().toList()) {
            if (line.isBlank()) {
                continue;
            }
            var parts = line.split(",", 2);
            var title = parts[0].trim();
            var body = parts.length > 1 ? parts[1].trim() : "";
            drafts.add(new NewNote(title, body));
        }
        return drafts;
    }
}
```

```java
// src/main/java/com/example/infrastructure/web/NoteResource.java  (import)
@POST
@Path("/import")
@Consumes(MediaType.MULTIPART_FORM_DATA)
@Produces(MediaType.APPLICATION_JSON)
public Response importCsv(@RestForm("file") FileUpload file) throws IOException {
    var csv = Files.readString(file.filePath(), StandardCharsets.UTF_8);
    var result = importNotes.importAll(csvNoteParser.parse(csv));
    return Response.ok(result).build();
}
```

```
$ cat notes.csv
Imported One,Body one
Imported Two,Body two

$ curl -F "file=@notes.csv" http://localhost:8080/notes/import
{"accepted":2,"rejected":0,"errors":[]}

$ cat notes-bad.csv
Good,Body ok
,blank title

$ curl -F "file=@notes-bad.csv" http://localhost:8080/notes/import
{"accepted":1,"rejected":1,"errors":["title must not be blank"]}
```

The CSV format is invisible to the core. The core sees `List<NewNote>` and answers with a business verdict — how many rows are valid.

## The Guardrail That Never Changed — Plus One New

Now the payoff. The two rules from Part 1 are reproduced here *byte-for-byte unchanged*, and we add a third that turns this article's through-line into an enforceable guarantee:

```java
// src/test/java/com/example/ArchitectureTest.java
package com.example;

import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.classes;
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

    @ArchTest
    static final ArchRule format_adapters_are_adapter_concerns = classes()
            .that().haveSimpleNameEndingWith("View")
            .or().haveSimpleNameEndingWith("Parser")
            .should().resideInAPackage("com.example.infrastructure..")
            .allowEmptyShould(true);
}
```

Everything new landed inside the three layers and three adapters the first two rules already name. The `Note` domain sits in `domain.model`; the use cases sit in `application`; `NoteResource`, `NotesHtmlView`, and `CsvNoteParser` sit in the `web` adapter; `InMemoryNoteRepository` sits in the `database` adapter. That is why the first two rules did not grow: the code did not grow outside the architecture.

The third rule exists because the first two have a blind spot. `NotesHtmlView` and `CsvNoteParser` are plain Java with no outgoing dependencies — the onion rule checks dependency *directions* and sees no edge, and the framework-free rule sees no `jakarta` import. Nothing would stop a future refactor from slipping `CsvNoteParser` into `application`. The new rule closes exactly that gap: a class named `View` or `Parser` must live in `infrastructure`, or the build fails. The through-line stops being prose and becomes a test.

Build proof — every test green, including the three architecture rules:

```
$ mvn test
Running com.example.NoteResourceTest
Tests run: 6, Failures: 0, Errors: 0, Skipped: 0
Running com.example.ArchitectureTest
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
Running com.example.application.NoteUseCaseTest
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
Running com.example.GreetingResourceTest
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
Running com.example.application.GreetingUseCaseTest
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0

Results:
Tests run: 14, Failures: 0, Errors: 0, Skipped: 0

BUILD SUCCESS
```

And the Part 1 CLI still runs on a plain JDK, unchanged:

```
$ java -cp target/classes com.example.infrastructure.cli.GreetingCli
Hello, Onion!
```

## The Final Structure

```
src/main/java/com/example/
├── domain/                          # pure Java, no framework imports
│   ├── model/
│   │   ├── Greeting.java
│   │   ├── NewNote.java             # unvalidated input record
│   │   └── Note.java                # validated record (title, body, createdAt)
│   └── service/
│       ├── GreetingRepository.java  # port
│       ├── NoteRepository.java      # port
│       ├── NoteValidator.java       # business rules
│       └── Greeter.java
├── application/                     # pure Java, no framework imports
│   ├── GreetingUseCase.java
│   ├── CreateNoteUseCase.java       # JSON POST path
│   ├── ListNotesUseCase.java        # JSON list + HTML table path
│   ├── StreamNotesUseCase.java      # SSE path, returns Stream<Note>
│   ├── ImportNotesUseCase.java      # CSV upload path
│   ├── ImportResult.java            # accepted / rejected / errors
│   └── ValidationException.java
└── infrastructure/                  # adapters, framework allowed
    ├── cli/                         # plain-JDK CLI consumer
    ├── database/
    │   ├── SqlGreetingRepository.java
    │   └── InMemoryNoteRepository.java
    └── web/
        ├── GreetingResource.java
        ├── NoteResource.java        # four endpoints
        ├── NewNoteRequest.java      # JSON DTO
        ├── ApiError.java            # JSON error DTO
        ├── NotesHtmlView.java       # HTML table renderer
        ├── CsvNoteParser.java       # multipart CSV parsing
        └── QuarkusConfig.java       # composition root
```

## How This Applies

The four experiments reduce to one rule set:

1. **The wire format lives in the adapter.** JSON shapes, HTML markup, SSE framing, and CSV syntax are all `infrastructure.web` concerns. The core never imports a parser or a serializer.
2. **The adapter owns the translation.** A request DTO maps to a domain record; a `FileUpload` becomes `NewNote` drafts. If the JSON field names change, only the adapter changes.
3. **The core returns domain objects and plain results.** `Note`, `List<Note>`, `Stream<Note>`, `ImportResult` — nothing reactive, nothing framework-specific.
4. **Parse at the edge, validate in the core.** CSV parsing produces raw drafts; `NoteValidator` decides what is a valid note. You can import from JSON tomorrow without touching the rules.
5. **A stream does not force reactive types into the core.** `Stream<Note>` is a JDK type. Mutiny appears only where SSE lives.

The deepest lesson is the quiet one: the guardrails from Part 1 did not change, yet the application gained four real-world I/O patterns — and the only new rule is a naming convention that says where format adapters live. That is the onion working as intended — the boundary holds because the boundary was never about the formats. It is about where the business rules live, and the tests now say it out loud.

The full runnable project lives in `_code/quarkus-onion-architecture`. Run `mvn clean test`, then `mvn quarkus:dev` and hit `/notes`, `/notes/html`, `/notes/stream`, and `/notes/import` with the curl commands above.

## References

- **ArchUnit User Guide, §4.3 Class and Package Containment Checks** — the `classes().that().haveSimpleNameEndingWith(...).should().resideInAPackage(...)` pattern behind the new naming rule. [archunit.org/userguide/html/000_Index.html#_class_and_package_containment_checks](https://www.archunit.org/userguide/html/000_Index.html#_class_and_package_containment_checks)
- **ArchUnit User Guide, §8.1.2 Onion Architecture** — the `onionArchitecture()` API and its semantics. The rule in this article follows that example. [archunit.org/userguide/html/000_Index.html#_onion_architecture](https://www.archunit.org/userguide/html/000_Index.html#_onion_architecture)
- **Quarkus REST (RESTEasy Reactive) Guide, Multipart** — `@RestForm` and `FileUpload` for file uploads. [quarkus.io/guides/rest#multipart](https://quarkus.io/guides/rest#multipart)
- **Quarkus REST (RESTEasy Reactive) Guide, Server-Sent Events** — returning `Multi<T>` with `MediaType.SERVER_SENT_EVENTS`. [quarkus.io/guides/rest#server-sent-events](https://quarkus.io/guides/rest#server-sent-events)
- **Jeffrey Palermo, "The Onion Architecture"** — the original definition that ArchUnit's rule implements. [jeffreypalermo.com/2008/07/the-onion-architecture-part-1](https://jeffreypalermo.com/2008/07/the-onion-architecture-part-1/)
