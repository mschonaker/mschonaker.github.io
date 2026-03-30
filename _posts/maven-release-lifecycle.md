# Understanding Maven's Release Lifecycle with GitHub Packages

The Maven release process is a cornerstone of Java artifact management. At its core, Maven's release lifecycle orchestrates a crucial transition: moving from development versions (SNAPSHOTs) to stable, immutable releases.

Traditionally, hosting Maven artifacts meant paying for solutions like Sonatype Nexus, JFrog Artifactory, or cloud repositories. **GitHub Packages changed this** - it offers free hosting for Maven artifacts on public repositories, meaning you can publish and consume Java packages without paying a dime. This democratizes the release process for open source projects and individual developers alike.

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

Add SCM and distribution management to your `pom.xml`:

```xml
<scm>
  <connection>scm:git:git@github.com:user/repo.git</connection>
  <developerConnection>scm:git:git@github.com:user/repo.git</developerConnection>
  <url>https://github.com/user/repo</url>
</scm>

<distributionManagement>
  <repository>
    <id>github</id>
    <url>https://maven.pkg.github.com/OWNER/REPOSITORY</url>
  </repository>
</distributionManagement>
```

With this setup, running `mvn clean release:prepare release:perform` will tag your code in GitHub and push the final artifacts to your free GitHub Packages repository - no paid infrastructure required.

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
