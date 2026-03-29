---
title: Understanding Maven's Release Lifecycle with GitHub Packages
date: 2025-04-29
---

The Maven release process is a cornerstone of Java artifact management. At its core, Maven's release lifecycle orchestrates a crucial transition: moving from development versions (SNAPSHOTs) to stable, immutable releases.

## The Release Process

1. Validates your project is in a releasable state with no SNAPSHOT dependencies
2. Updates version numbers in POM files
3. Runs tests to ensure everything builds correctly
4. Creates an SCM tag for this release
5. Deploys artifacts to the repository

## Key Commands

- Deploy SNAPSHOT: `mvn deploy`
- Create release: `mvn clean release:prepare release:perform`
- Rollback if something goes wrong: `mvn release:rollback`

## Configuring GitHub Packages

Add to `~/.m2/settings.xml`:

```xml
<server>
  <id>github</id>
  <username>your-username</username>
  <password>TOKEN</password>
</server>
```

Add SCM to your `pom.xml`:

```xml
<scm>
  <connection>scm:git:git@github.com:user/repo.git</connection>
  <developerConnection>scm:git:git@github.com:user/repo.git</developerConnection>
  <url>https://github.com/user/repo</url>
</scm>
```

## Consuming Released Artifacts

Add the dependency:

```xml
<dependency>
  <groupId>com.example</groupId>
  <artifactId>maven-release-hello</artifactId>
  <version>1.0.0</version>
</dependency>
```

Use `mvn -U` to force update SNAPSHOT dependencies during development.
