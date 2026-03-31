# Hexagonal Architecture in Spring Boot: Breaking Free from Annotations

The web layer in Spring Boot is fine. Controllers, REST endpoints - they need those annotations to work with Spring MVC's infrastructure. But I've always felt uneasy about scattering `@Component`, `@Service`, and `@Repository` throughout my core business logic. That's not architecture; that's Stockholm syndrome.

After discussing this with a friend, I started thinking harder about this. Here's the path to a cleaner Spring Boot application that keeps your core logic pure.

## The Problem with Spring's Default Approach

When you use component scanning, your core domain becomes contaminated with framework annotations. Your business logic shouldn't know (or care) that it's running in Spring. But more practically:

- Testing becomes harder - you need a Spring context to test anything
- It's harder to swap implementations (want to use an in-memory map instead of Redis in tests? Good luck)
- Your core module can't be reused outside Spring

## The Solution: Explicit Bean Registration

Move your business logic to a separate Maven module. Strip out all Spring annotations. Then wire everything explicitly in a `@Configuration` class.

```java
@Configuration
public class AppConfig {
    @Bean
    public MyService myService(MyRepository repository) {
        return new MyService(repository);
    }
}
```

This is essentially what Guice does - explicit module definitions instead of classpath scanning.

## What About Redis, Elasticsearch, and Other Infrastructure?

Same pattern. Define a "port" (interface) in your core module with generics:

```java
public interface SearchService<T> {
    void index(String id, T document);
    Optional<T> get(String id);
}
```

Implement the "adapter" in your infrastructure module:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

public class ElasticSearchAdapter<T> implements SearchService<T> {
    private final ElasticsearchOperations operations;

    public ElasticSearchAdapter(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public void index(String id, T document) {
        operations.save(document, IndexCoordinates.of(id));
    }

    @Override
    public Optional<T> get(String id) {
        return Optional.ofNullable(operations.load(id, (Class<T>) null));
    }
}
```

## The Functional Approach

Skip `@Configuration` entirely. Use Spring's Functional Bean Definition API:

```java
public static void main(String[] args) {
    new SpringApplicationBuilder(MyApplication.class)
        .initializers((GenericApplicationContext context) -> {
            context.registerBean(SearchService.class, () -> 
                new ElasticSearchAdapter(context.getBean(ElasticsearchOperations.class)));
        })
        .run(args);
}
```

No annotations anywhere. Just pure Java registration.

## Why Bother?

1. **Testability** - Swap Redis for a HashMap in unit tests without loading a Spring context
2. **Portability** - Your core logic is just Java, reusable anywhere
3. **Control** - You decide initialization order, not Spring's auto-configuration
4. **Cleaner architecture** - Infrastructure adapters are clearly separated from business logic

The web layer will always need Spring annotations. But everything behind it? That can be pure Java.
