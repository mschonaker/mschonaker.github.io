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

**Artifact Chaining**: Your User service in Dev depends on unreleased (non-production) artifacts from Team B's Payment service. When Payment advances, User breaks. In microservices, your checkout flow touches 6 services—updating any one makes the entire stack temporarily invalid for testing.

**The Fix**: Consume production, not other teams' lower environments. Create your own namespace on their production. Just like you use Azure Redis's production service but name your own instances "dev-cache", "qa-cache".

---

**Shared Fan-in**: Your services B and C both depend on D (MySQL, Redis, Kafka). Upgrading D requires upgrading both B and C simultaneously - impossible to coordinate. One team's upgrade blocks everyone else.

**The Fix**: One service "owns" its view of the shared dependency. Like B has MySQL-1, C has MySQL-2. Each team's dependency is isolated - no coordination required. Use strict SemVer so non-breaking upgrades don't block anyone.

---

**Dependency Cycles**: If Service A → B → C → A, you have a cycle. That's where environment fragmentation bites.

**The Fix**: Keep your dependency graph acyclic. Like npm or Maven, your service dependencies should form a tree, not a web. One service "owns" its consumers' view of it.

---

**Environment Drift**: Each team's "staging" diverges. Team A's notification service has different retry logic. Team B's auth service has different token expiry. "It works in Staging" becomes a reliable indicator it won't work in Production.

**The Fix**: Use contract testing (Pact) to verify compatibility without shared environments.

---

Jeff Bezos mandated that internal communication happen over email rather than meetings—so information could be shared asynchronously, without synchronization. The same principle applies here: if your lower environments require synchronous coordination to function, you've already lost.

Your production microservices are independently deployable. Your lower environments should be too.