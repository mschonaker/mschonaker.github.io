---
id: maven003
title: Trunk-Based Maven Releases with GitHub Actions
summary: Extend the automation from Automating Maven Releases with GitHub Actions with a trunk-based branching model — major/minor releases from main, patch releases from release branches, all automated.
date: 2026-07-26
---

# Trunk-Based Maven Releases with GitHub Actions

![Trunk-based development header](/images/maven-trunk-based-development.png)

This is the third article in the Maven release trilogy. In [Understanding Maven's Release Lifecycle](/#article/maven001), we learned how `mvn release:prepare release:perform` works. In [Automating Maven Releases with GitHub Actions](/#article/maven002), we wrapped those commands in CI/CD workflows. Now we extend that automation to support a proper branching model.

Trunk-based development (TBD) is a branching strategy where `main` is the single source of truth. All development happens on short-lived feature branches that integrate into `main` frequently — daily or even multiple times per day. Releases are cut from `main` for major and minor versions. Patch releases happen on dedicated release branches created from the release tag, avoiding the need to stabilize `main` before shipping a hotfix.

The key rules in our model:
- **Major and minor releases** come from `main`. After release, `main` advances to the next minor snapshot.
- **Patch releases** happen on `releases-X.Y.x` branches. Only cherry-picks from `main` go here — no merges.
- **Release branches** are created automatically by the main release workflow, pre-configured for the next patch version.

This gives you the flexibility of release branches without sacrificing the simplicity of trunk-based development.

## The Branching Model

- **main** — active development, `X.Y.0-SNAPSHOT` (next minor). Every push deploys a SNAPSHOT.
- **releases-X.Y.x** — created after each major/minor release from main. Holds `X.Y.Z-SNAPSHOT` (next patch). Only patch releases happen here.
- **Tags** — `v1.0.0`, `v1.0.1`, `v1.1.0`, etc. Immutable releases.

After releasing `v1.1.0` from main:
- Tag `v1.1.0` is created
- Branch `releases-1.1.x` is created from the tag
- `main` becomes `1.2.0-SNAPSHOT` (next minor)
- `releases-1.1.x` becomes `1.1.1-SNAPSHOT` (next patch)

## The Three Workflows

### 1. SNAPSHOT Deploy

Identical to [Automating Maven Releases with GitHub Actions](/#article/maven002), but the branch filter widens to include release branches:

```yaml
name: SNAPSHOT Deploy

on:
  push:
    branches: [main, releases-**]

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

Both `main` and any `releases-*` branch get automatic SNAPSHOT deployments. The `-SNAPSHOT` version in the POM distinguishes them.

### 2. Release (Main) — Major/Minor

This is the new workflow. It releases from main, then creates and prepares the release branch:

```yaml
name: Release (Main)

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
          git config --global credential.helper "store --file=$HOME/.git-credentials"
          echo "https://x-access-token:${{ secrets.GH_PAT }}@github.com" > $HOME/.git-credentials

      - name: Compute versions
        id: version
        run: |
          CURRENT_VERSION=$(mvn help:evaluate -Dexpression=project.version -q -DforceStdout)
          RELEASE_VERSION=${CURRENT_VERSION%-SNAPSHOT}
          MAJOR=$(echo "$RELEASE_VERSION" | cut -d. -f1)
          MINOR=$(echo "$RELEASE_VERSION" | cut -d. -f2)
          PATCH=$(echo "$RELEASE_VERSION" | cut -d. -f3)
          NEXT_MINOR=$((MINOR + 1))
          NEXT_PATCH=$((PATCH + 1))
          MAIN_DEV_VERSION="$MAJOR.$NEXT_MINOR.0-SNAPSHOT"
          BRANCH="releases-$MAJOR.$MINOR.x"
          BRANCH_VERSION="$MAJOR.$MINOR.$NEXT_PATCH-SNAPSHOT"
          echo "release-version=$RELEASE_VERSION" >> "$GITHUB_OUTPUT"
          echo "tag=v$RELEASE_VERSION" >> "$GITHUB_OUTPUT"
          echo "dev-version=$MAIN_DEV_VERSION" >> "$GITHUB_OUTPUT"
          echo "branch=$BRANCH" >> "$GITHUB_OUTPUT"
          echo "branch-version=$BRANCH_VERSION" >> "$GITHUB_OUTPUT"

      - name: Maven Release
        run: |
          mvn -B clean release:prepare release:perform \
            -DdevelopmentVersion=${{ steps.version.outputs.dev-version }} \
            -DconnectionUrl=scm:git:https://github.com/${{ github.repository }}.git \
            -DdeveloperConnectionUrl=scm:git:https://github.com/${{ github.repository }}.git
        env:
          MAVEN_USERNAME: ${{ github.actor }}
          MAVEN_PASSWORD: ${{ secrets.GH_PAT }}

      - name: Create and prepare release branch
        run: |
          git fetch origin main --tags
          git checkout -b "${{ steps.version.outputs.branch }}" "${{ steps.version.outputs.tag }}"
          # Overlay latest workflow files from main so the branch has up-to-date workflows
          git restore --source origin/main -- .github/workflows/
          git add .github/workflows/
          if ! git diff --cached --quiet; then
            git commit -m "Update workflow files from main"
          fi
          # Prepare for next patch development
          mvn versions:set -DnewVersion=${{ steps.version.outputs.branch-version }}
          git commit -am "Prepare for next patch development"
          git push origin "${{ steps.version.outputs.branch }}"
        env:
          MAVEN_USERNAME: ${{ github.actor }}
          MAVEN_PASSWORD: ${{ secrets.GH_PAT }}
```

Key details:

**Version computation.** The `Compute versions` step reads the POM's current version (e.g. `1.1.0-SNAPSHOT`) and derives:
- `release-version`: strips `-SNAPSHOT` (`1.1.0`)
- `dev-version`: next minor (`1.2.0-SNAPSHOT`) — overrides Maven's default patch bump
- `branch`: `releases-1.1.x`
- `branch-version`: next patch (`1.1.1-SNAPSHOT`)

**Explicit `-DdevelopmentVersion`.** By default, `mvn release:prepare -B` bumps to the next patch (`1.2.1-SNAPSHOT`). We override to next minor (`1.2.0-SNAPSHOT`) because all patch releases should happen on release branches.

**Global credential store.** `release:perform` clones the tag into `target/checkout/` — a separate git operation that doesn't inherit the per-repository credentials from `actions/checkout`. The credential store ensures authentication works for that clone too. Without it, `release:perform` fails with `could not read Username for 'https://github.com'`.

**Workflow file overlay.** When the release branch is created from the tag, it inherits the workflow files that existed at that commit. If the workflows have been updated since then (e.g. with the credential store fix), the branch would have stale versions. Since `workflow_dispatch` loads the workflow definition from the branch it runs on, stale workflows break patch releases. The overlay step restores the latest `.github/workflows/` files from `origin/main` to keep them current.

### 3. Release (Patch) — Patch Releases

This workflow has no custom inputs — the user picks the release branch from the built-in branch selector in the Actions tab:

```yaml
name: Release (Patch)

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
          git config --global credential.helper "store --file=$HOME/.git-credentials"
          echo "https://x-access-token:${{ secrets.GH_PAT }}@github.com" > $HOME/.git-credentials

      - name: Maven Release
        run: |
          mvn -B clean release:prepare release:perform \
            -DconnectionUrl=scm:git:https://github.com/${{ github.repository }}.git \
            -DdeveloperConnectionUrl=scm:git:https://github.com/${{ github.repository }}.git
        env:
          MAVEN_USERNAME: ${{ github.actor }}
          MAVEN_PASSWORD: ${{ secrets.GH_PAT }}
```

Batch mode's default version bumps are correct here: `1.1.1-SNAPSHOT` → release `1.1.1` → dev `1.1.2-SNAPSHOT`. No overrides needed.

## How It Works End-to-End

1. You develop on `main` at `1.1.0-SNAPSHOT`. Every push deploys a SNAPSHOT to GitHub Packages.

2. When `1.1.0` is ready, you go to the Actions tab, select **Release (Main)**, click **Run workflow**.

3. The workflow runs `release:prepare release:perform`:
   - Creates tag `v1.1.0`
   - Deploys the `1.1.0` artifact to GitHub Packages
   - Sets `main` to `1.2.0-SNAPSHOT`

4. The workflow then creates branch `releases-1.1.x` from the `v1.1.0` tag, overlays the latest workflow files from `main`, and sets the POM to `1.1.1-SNAPSHOT`. All pushed automatically.

5. Later, a bug is found in production. You fix it on `main`, cherry-pick the commit to `releases-1.1.x`:

   ```bash
   git checkout releases-1.1.x
   git cherry-pick <fix-commit-hash>
   git push origin releases-1.1.x
   ```

   The SNAPSHOT deploy workflow pushes `1.1.1-SNAPSHOT` to GitHub Packages automatically.

6. You go to the Actions tab, select **Release (Patch)**, pick `releases-1.1.x` from the branch dropdown, and run. The workflow releases `1.1.1`, tags `v1.1.1`, and sets the branch to `1.1.2-SNAPSHOT`.

7. `main` continues at `1.2.0-SNAPSHOT` with the fix — it will ship in the next minor release.

## Why the Workflow Overlay Matters

When you create a release branch from a tag, the `.github/workflows/` directory on that branch reflects the workflows as they existed at that commit. If you later improve the workflows on `main` (a bug fix, a new feature), the release branch won't have those improvements.

Since GitHub Actions loads workflow definitions from the branch the workflow runs on, triggering **Release (Patch)** on a release branch uses that branch's (potentially stale) `release-patch.yml`. The overlay step in `release-main.yml` prevents this: it copies the latest workflow files from `origin/main` onto the release branch before pushing it.

The check `git diff --cached --quiet` avoids committing if the files haven't changed — no unnecessary noise.

## Summary

| Workflow | What | Trigger | Branch | Post-Release |
|----------|------|---------|--------|--------------|
| `snapshot-deploy.yml` | SNAPSHOT deploy | Push | `main`, `releases-**` | Nothing |
| `release-main.yml` | Major/minor release | Manual | `main` | Create `releases-X.Y.x`, bump main to next minor |
| `release-patch.yml` | Patch release | Manual | User picks from dropdown | Nothing (branch auto-bumps via batch mode) |

The three workflows implement a complete trunk-based Maven release pipeline:

- **Main** handles major and minor releases. After each release, a release branch is created and main advances to the next minor version.
- **Release branches** handle only patches. Cherry-pick fixes from main, run the patch workflow, ship the fix without deploying unfinished work.
- **Both branches** get automatic SNAPSHOT deployments on every push, so the latest version is always available for testing.

## See Also

- [Understanding Maven's Release Lifecycle](/#article/maven001) — Maven's release process and GitHub Packages setup
- [Automating Maven Releases with GitHub Actions](/#article/maven002) — CI/CD workflows for SNAPSHOT and release deployment
