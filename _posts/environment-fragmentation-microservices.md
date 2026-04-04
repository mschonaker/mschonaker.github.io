---
id: env-fragmentation
title: Environment Fragmentation Defined
summary: Why your dev/QA/staging environments become a distributed monolith and how to fix it.
date: 2025-05-20
---

# Environment Fragmentation Defined

![Microservices Environment](/images/maven-header.png)

You pip install a library from a stranger on the internet. It works. You npm install a package from a maintainer you've never met. It works. You docker pull an image from a random GitHub repo. It works. You use a third-party public REST API. It works.

So why can't two teams in the same organization share a staging environment?

---

## Artifact Chaining

Here's how it usually starts: your User service in Dev depends on Team B's Payment service—but the unreleased version, not the one running in production. When Payment ships their update, User breaks. Now you're in a Mexican standoff: Payment can't deploy because User breaks, and User can't update because Payment is mid-sprint.

In a microservices architecture, your checkout flow might touch six services. Updating any one of them makes the entire stack temporarily invalid for testing. You've built a distributed monolith.

**The fix is surprisingly simple**: consume production, not other teams' lower environments. Create your own namespace on their production cluster. Think of how you use Azure Redis—you're using Azure's production service, but you've named your instances "dev-cache" and "qa-cache". Same idea. Each team drinks from production, but from their own cup.

---

## Shared Fan-in

Now picture this: your services B and C both depend on service D (maybe a MySQL instance, a Redis cache, or a Kafka topic). When you want to upgrade D, you suddenly need to upgrade B and C simultaneously. One team's upgrade blocks two other teams, and those teams are busy with their own priorities.

Sound familiar? This is the "shared database" anti-pattern wearing a microservices costume.

**The fix**: one service "owns" its view of the shared dependency. Service B gets its own MySQL-1 instance. Service C gets its own MySQL-2 instance. Each team's dependency is completely isolated—zero coordination required.

### Major versions = new instances

Strict SemVer is what makes this work at scale. When Service B needs a schema change that breaks backward compatibility, they don't coordinate with Service C—they deploy MySQL-2. Service C keeps running MySQL-1, unaffected. Now both teams are on independent major versions: B on MySQL-2, C on MySQL-1. Neither team's breaking change blocks the other. Patches and minors flow frictionlessly; major bumps mean spinning up a new instance. The dependency graph stays acyclic because there's no shared state to coordinate around.

---

## Dependency Cycles

Imagine a world where Service A calls B, B calls C, and C calls A. Congratulations, you've invented the environment fragmentation party game where nobody wins. Cycles create tight coupling across time: A can't upgrade without understanding C, and C can't refactor without breaking A.

**The fix**: keep your dependency graph acyclic. Your service dependencies should form a tree, not a web. This isn't just about clean architecture—it's about organizational independence. One service "owns" its consumers' view of it, and everyone else treats it as a stable, versioned contract.

---

## Environment Drift

Here's the quiet killer: over time, each team's "staging" environment diverges from production. Team A's notification service has different retry logic. Team B's auth service has different token expiry settings. Slowly, almost invisibly, "it works in staging" becomes a reliable indicator that it *won't* work in production.

**The fix**: contract testing. Tools like Pact let you verify that your services speak the same language—without ever sharing an environment. You test your side of the contract, they test theirs, and you both sleep better at night.

---

Jeff Bezos mandated that internal communication happen over email rather than meetings—so information could flow asynchronously, without forcing people to synchronize their calendars. The same principle applies to environments: if your lower environments require synchronous coordination to function, you've already lost.

Your production microservices are independently deployable. Your lower environments should be too.