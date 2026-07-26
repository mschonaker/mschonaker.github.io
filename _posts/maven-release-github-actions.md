---
id: maven002
title: Automating Maven Releases with GitHub Actions
summary: Automate the release process from Understanding Maven's Release Lifecycle — deploy SNAPSHOTs on every push and cut releases with a single button click.
image: /images/maven-release-automation.png
date: 2026-07-26
---

# Automating Maven Releases with GitHub Actions

In [Understanding Maven's Release Lifecycle](/#article/maven001), we ran `mvn deploy` and `mvn release:prepare release:perform` from a terminal. That works, but it's manual. Every push to main should deploy a fresh SNAPSHOT, and cutting a release should be a button click — not a sequence of commands you hope you remember correctly.

Let's automate both with GitHub Actions.

## What We're Building

Two workflows in `.github/workflows/`:

- **SNAPSHOT Deploy** — triggers on every push to `main`, runs `mvn deploy`, publishes the snapshot to GitHub Packages.
- **Release** — triggered manually from the Actions tab, runs `mvn release:prepare release:perform`, tags the repo, bumps the version, and publishes a stable release.

## Prerequisites

You need the setup from [Understanding Maven's Release Lifecycle](/#article/maven001):
- A `pom.xml` with `<distributionManagement>` pointing to `https://maven.pkg.github.com/OWNER/REPO`.
- A `<scm>` section pointing to your repo.
- A GitHub personal access token with `repo` and `write:packages` scopes.

The project we'll use is the same `maven-release-hello` from [Understanding Maven's Release Lifecycle](/#article/maven001).

### SCM URLs: HTTPS vs SSH

[Understanding Maven's Release Lifecycle](/#article/maven001) showed SSH URLs (`scm:git:git@github.com:...`). Those work fine locally. But GitHub Actions needs HTTPS URLs because `actions/checkout` authenticates via token, not SSH key. The release plugin uses these URLs to push tags and commits.

You have two options:
1. Change your POM to HTTPS URLs (works everywhere, both local and CI)
2. Keep SSH in the POM and override via `-DconnectionUrl` in the workflow (shown below)

This article uses option 2 — the workflow overrides take precedence, so your POM stays unchanged from the previous article.

## Workflow 1: SNAPSHOT Deploy

```yaml
# .github/workflows/snapshot-deploy.yml
name: SNAPSHOT Deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          java-version: 17
          distribution: temurin
          server-id: github
          server-username: MAVEN_USERNAME
          server-password: MAVEN_PASSWORD

      - name: Deploy SNAPSHOT
        run: mvn deploy
        env:
          MAVEN_USERNAME: ${{ github.actor }}
          MAVEN_PASSWORD: ${{ secrets.GH_PAT }}
```

`actions/setup-java` with `server-id`, `server-username`, `server-password` generates a `~/.m2/settings.xml` on the runner automatically — no need to commit one to your repo.

## Workflow 2: Release

```yaml
# .github/workflows/release.yml
name: Release

on:
  workflow_dispatch:

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.GH_PAT }}

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          java-version: 17
          distribution: temurin
          server-id: github
          server-username: MAVEN_USERNAME
          server-password: MAVEN_PASSWORD

      - name: Configure Git
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"

      - name: Maven Release
        run: |
          mvn -B clean release:prepare release:perform \
            -DconnectionUrl=scm:git:https://github.com/${{ github.repository }}.git \
            -DdeveloperConnectionUrl=scm:git:https://github.com/${{ github.repository }}.git
        env:
          MAVEN_USERNAME: ${{ github.actor }}
          MAVEN_PASSWORD: ${{ secrets.GH_PAT }}
```

The `-DconnectionUrl` and `-DdeveloperConnectionUrl` override the POM's SCM URLs with HTTPS versions for the CI run. `actions/checkout` with the token sets up git's `http.extraheader` config, which authenticates all HTTPS git operations to github.com automatically — including the pushes that `release:prepare` makes.

## The GH_PAT Secret

Both workflows reference `secrets.GH_PAT`. This is a classic GitHub personal access token you create once and store as a repository secret.

**Required scopes:**

| Scope | Purpose |
|-------|---------|
| `repo` | Push commits and tags (for `release:prepare`) |
| `write:packages` | Publish artifacts to GitHub Packages |

**To set it up:**

1. Create a token at `https://github.com/settings/tokens` with `repo` and `write:packages`.
2. Go to your repository: **Settings > Secrets and variables > Actions > New repository secret**.
3. Name it `GH_PAT`, paste the token.

The default `GITHUB_TOKEN` that GitHub Actions provides automatically does not have `write:packages` scope for Maven. A PAT is required.

## How It Works End-to-End

1. You push code to `main`.
2. The **SNAPSHOT Deploy** workflow fires, builds, tests, and deploys the current `-SNAPSHOT` version to GitHub Packages.
3. When you're ready to cut a release, go to the Actions tab, select **Release**, click **Run workflow**.
4. The release workflow runs `release:prepare`: strips `-SNAPSHOT` from the version, creates a git tag (`v1.0.1`), commits the tag, pushes it, then updates the POM to the next development version (`1.0.2-SNAPSHOT`) and commits that too.
5. Then `release:perform` checks out the tag and deploys the stable artifact to GitHub Packages.

All without touching a terminal.

## Testing It Yourself

If you want to verify this end-to-end (the way an LLM or a CI pipeline would), here are the exact steps:

1. **Create the test project** from [Understanding Maven's Release Lifecycle](/#article/maven001) — same `pom.xml` with `groupId com.example`, `artifactId maven-release-hello`, `version 1.0.0-SNAPSHOT`, distribution management pointing to `https://maven.pkg.github.com/YOUR_USER/maven-release-test`.

2. **Create a private GitHub repo** called `maven-release-test`:
   ```bash
   gh repo create YOUR_USER/maven-release-test --private
   ```

3. **Initialize git, push the project**:
   ```bash
   git init && git checkout -b main
   git add -A && git commit -m "Initial commit"
   git remote add origin git@github.com:YOUR_USER/maven-release-test.git
   git push -u origin main
   ```

4. **Set up Maven settings** for GitHub Packages auth:
   ```bash
   mkdir -p ~/.m2
   cat > ~/.m2/settings.xml << 'EOF'
   <settings>
     <servers>
       <server>
         <id>github</id>
         <username>YOUR_USER</username>
         <password>YOUR_TOKEN</password>
       </server>
     </servers>
   </settings>
   EOF
   ```
   Your token must have `repo` and `write:packages` scopes.

5. **Verify local SNAPSHOT deploy** works:
   ```bash
   mvn deploy
   ```
   Look for `BUILD SUCCESS` and artifacts uploaded to `https://maven.pkg.github.com/YOUR_USER/maven-release-test`.

6. **Create the workflow files** in `.github/workflows/` as shown above.

7. **Add the GH_PAT secret** to the repo:
   ```bash
   gh secret set GH_PAT --repo YOUR_USER/maven-release-test --body "YOUR_TOKEN"
   ```

8. **Push the workflows**:
   ```bash
   git add -A && git commit -m "Add workflows"
   git push
   ```

9. **Verify the SNAPSHOT workflow** ran automatically — check the Actions tab for a green checkmark on the **SNAPSHOT Deploy** run.

10. **Trigger the release** workflow:
    ```bash
    gh workflow run Release --repo YOUR_USER/maven-release-test
    ```

11. **Verify the release** completed — check Actions for a green checkmark, verify the tag exists (`gh api /repos/YOUR_USER/maven-release-test/tags`), and confirm the versioned artifact is in GitHub Packages (`gh api /users/YOUR_USER/packages/maven/com.example.maven-release-hello/versions`).

## Security Considerations

### Token Scope Discipline

The `GH_PAT` has `repo` scope — it can read and write all your private repos. Treat it like a password. GitHub Actions stores it encrypted at rest, and it's only exposed to workflows in that one repository. Still, consider these practices:

- Use a **dedicated token** for CI, not your daily-development token. If it leaks, you revoke one token without affecting your other tools.
- Set an **expiration date** on the PAT (GitHub allows up to one year). Add a calendar reminder to rotate it.
- If you're on a GitHub team plan, use a **fine-grained PAT** scoped to a single repository instead of a classic token with blanket `repo` access.

### Why GITHUB_TOKEN Won't Work

Every workflow run gets an automatic `GITHUB_TOKEN`. It's convenient, but it lacks `write:packages` scope for Maven. The `actions/setup-java` action uses the token to generate settings.xml, and Maven's deploy plugin will get a 401 when trying to upload. A PAT with explicit `write:packages` is required.

### No Secrets in the POM

The workflows use `actions/setup-java` to generate `settings.xml` on the fly. No credentials are committed to your repository. The token is referenced via `${{ secrets.GH_PAT }}`, which GitHub's secret scrubbing protects from unintended exposure in logs.

## Summary

| What | How | Trigger |
|------|-----|---------|
| SNAPSHOT deploy | `mvn deploy` | Push to `main` |
| Release | `mvn release:prepare release:perform` | Manual (`workflow_dispatch`) |

The two workflows replace the manual commands from [Understanding Maven's Release Lifecycle](/#article/maven001). Every push publishes a SNAPSHOT. Every release is a button click away.

## See Also

- [Understanding Maven's Release Lifecycle](/#article/maven001) — Maven's release process and GitHub Packages setup
- [Trunk-Based Maven Releases with GitHub Actions](/#article/maven003) — Extending automation with release branches for patch releases
