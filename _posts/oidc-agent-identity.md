---
id: oidc-agent-identity
title: "OIDC-A: The Emerging Standard for AI Agent Identity and Credentials"
summary: "How OpenID Connect is being extended to authenticate, authorize, and delegate credentials for autonomous AI agents—and what a real credential exchange looks like."
date: 2026-04-07
image: /images/oidc-agent-identity-header.png
---

# OIDC-A: The Emerging Standard for AI Agent Identity and Credentials

As AI agents transition from simple chatbots to autonomous actors capable of calling APIs, executing transactions, and orchestrating complex workflows, a fundamental question emerges: **how do we know who an agent is, what it's authorized to do, and whether we trust it?**

Traditional authentication was built for humans. OAuth 2.0 and OpenID Connect (OIDC) handle user login, but they weren't designed for software entities that act with varying degrees of autonomy, delegate authority to other agents, and require cryptographic proof of their integrity. The security community is now responding with a new generation of standards—and the most promising candidate is **OIDC-A (OpenID Connect for Agents)**.

## The Problem: Why Existing Standards Fall Short

Modern AI agents present challenges that existing identity frameworks weren't built to handle:

1. **Delegation chains**: An agent may act on behalf of a user, which in turn delegates to another specialized agent. Who is responsible, and what permissions flow through the chain?

2. **Dynamic capabilities**: An agent's abilities depend on its underlying model, which can change with updates. How do we represent and verify what an agent can actually do?

3. **Attestation**: How do we cryptographically prove that an agent is running in a trusted environment, hasn't been tampered with, and originates from a known provider?

4. **Autonomous vs. supervised**: Some agents make decisions independently; others require human approval for sensitive actions. How do we distinguish and enforce these modes?

Existing OAuth 2.0 tokens carry minimal information about the software performing the request. There's no standard way to represent "this is an AI agent" or "this agent was delegated authority by user X to perform Y."

## State of the Art: Emerging Standards Landscape

Several initiatives are tackling agent identity from different angles:

### 1. OIDC-A 1.0 (OpenID Connect for Agents)

The most comprehensive proposal to date, OIDC-A extends OpenID Connect Core 1.0 with agent-specific claims and protocols. Created by Subramanya N (with an arXiv paper published in September 2025) and discussed on agentictrust.com, it provides:

- **Agent identity claims**: `agent_type`, `agent_model`, `agent_provider`, `agent_instance_id`
- **Delegation framework**: `delegator_sub`, `delegation_chain`, `delegation_constraints`
- **Attestation**: Integration with IETF RATS (Remote Attestation Procedures)
- **Capability discovery**: Endpoints to enumerate what an agent can do

### 2. IETF AIMS (AI Agent Identity Management System)

In March 2026, four engineers from Defakto Security, AWS, Zscaler, and Ping Identity submitted `draft-klrc-aiagent-auth-00`—a 26-page IETF draft providing a comprehensive identity framework for AI agents. Key innovations:

- **WIMSE (Workload Identity in Multi-System Environments)**: A conceptual framework for workload identity
- **SPIFFE integration**: Leverages the existing SPIFFE standard for cryptographic workload identity
- **OAuth 2.0 extension**: Extends token formats with agent-specific metadata

This draft represents a more conservative, standards-body approach compared to OIDC-A's detailed proposal.

### 3. Agent Credential Attestation Protocol (ACAP)

An IETF draft from March 2026 (`draft-yakung-oauth-agent-attestation-00`) focusing specifically on **attestation**—the cryptographic proof of agent integrity. It defines how agents can present verifiable evidence of their origin, configuration, and运行环境.

### 4. Agent Identity Protocol (AIP)

Another IETF draft (`draft-prakash-aip-00`) focusing on **verifiable delegation** for AI agent systems—the ability for chains of agents to pass authority while maintaining cryptographic proof of the chain.

## The Community: Who's Building This?

### OpenID Foundation

The OpenID Foundation has taken a leadership role. In October 2025, they published "Identity Management for Agentic AI"—a whitepaper tackling the foundational challenges. The lead editor was **Tobin South** (MIT, Stanford HAI research fellow, and WorkOS). The foundation has also responded to NIST calls for input on AI agent security.

### Key Individuals and Organizations

- **Subramanya N**: Creator of OIDC-A proposal, maintainer of the [oidc-a GitHub repository](https://github.com/subramanya1997/oidc-a)
- **Brian Campbell** (Ping Identity): Co-author of IETF AIMS draft
- **Tobin South**: Lead editor of OpenID Foundation whitepaper, MCP security research at Anthropic
- **Atul Tulshibagwale** (SGNL): Co-chair of OpenID Foundation working group on AI identity

### Protocol Projects

- **A2A (Agent2Agent)**: An open protocol for agent-to-agent communication. Issue #1463 discusses integrating OID4VP (OpenID for Verifiable Presentations) for in-task authorization.
- **MCP (Model Context Protocol)**: Anthropic's protocol for agent-tool interaction. Work is underway to secure MCP with OIDC and OIDC-A.

## A Concrete Example: Credential Exchange for a Secured Action

Let's walk through what a real credential exchange looks like when an AI agent needs to perform a secured action—specifically, an email agent that needs to read a user's inbox after delegated authority.

### The Scenario

1. **User Alice** wants her email assistant agent to summarize her unread emails.
2. **Agent Alpha** is Alice's primary assistant, which will coordinate the task.
3. **Agent Beta** is a specialized summarization agent that Agent Alpha delegates to.
4. **Resource Server** is the email API that requires authentication.

### Step 1: Initial Authentication (Alice → Authorization Server)

Alice logs in using standard OIDC. The Authorization Server issues an ID token and access token.

```json
// Alice's initial ID Token
{
  "iss": "https://auth.example.com",
  "sub": "user_alice_123",
  "aud": "client_app_alpha",
  "exp": 1714348800,
  "iat": 1714345200,
  "auth_time": 1714345200
}
```

### Step 2: Agent Registration

Agent Alpha registers with the authorization server, declaring its identity:

```json
// Agent metadata registration
{
  "client_id": "agent_alpha_789",
  "agent_provider": "acme.ai",
  "agent_models_supported": ["gpt-4o", "claude-3-5-sonnet"],
  "agent_capabilities": ["email:read", "email:draft", "calendar:view"],
  "attestation_formats_supported": ["urn:ietf:params:oauth:token-type:eat"],
  "delegation_methods_supported": ["scope_delegation"]
}
```

### Step 3: Delegation Grant

Alice delegates authority to Agent Alpha. The authorization server issues a token with delegation claims:

```json
// Agent Alpha's ID Token (with delegation)
{
  "iss": "https://auth.example.com",
  "sub": "agent_alpha_789",
  "aud": "email_api",
  "exp": 1714352400,
  "iat": 1714348800,
  "auth_time": 1714345200,
  
  // OIDC-A: Agent identity
  "agent_type": "assistant",
  "agent_model": "gpt-4o",
  "agent_version": "2026-03",
  "agent_provider": "acme.ai",
  "agent_instance_id": "alpha_instance_001",
  "agent_trust_level": "verified",
  
  // OIDC-A: Delegation from Alice
  "delegator_sub": "user_alice_123",
  "delegation_purpose": "Email management assistant",
  "delegation_constraints": {
    "max_duration": 3600,
    "allowed_resources": ["mailto:alice@example.com"]
  },
  
  // OIDC-A: Capabilities
  "agent_capabilities": ["email:read", "email:draft"],
  
  // OIDC-A: Attestation (EAT token)
  "agent_attestation": {
    "format": "urn:ietf:params:oauth:token-type:eat",
    "token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
    "timestamp": 1714348800
  }
}
```

### Step 4: Sub-delegation to Specialized Agent

Agent Alpha decides to delegate to Agent Beta for summarization. The delegation chain grows:

```json
// Agent Alpha's token, now including delegation chain
{
  // ... previous claims ...
  "delegation_chain": [
    {
      "iss": "https://auth.example.com",
      "sub": "user_alice_123",
      "aud": "agent_alpha_789",
      "delegated_at": 1714348700,
      "scope": "email:read email:draft",
      "purpose": "Manage my emails"
    }
  ]
}
```

When Agent Alpha delegates to Agent Beta, the chain extends:

```json
// Agent Beta's token - multi-step delegation
{
  "iss": "https://auth.example.com",
  "sub": "agent_beta_456",
  "aud": "email_api",
  "delegation_chain": [
    {
      "iss": "https://auth.example.com",
      "sub": "user_alice_123",
      "aud": "agent_alpha_789",
      "delegated_at": 1714348700,
      "scope": "email:read email:draft",
      "purpose": "Manage my emails"
    },
    {
      "iss": "https://auth.example.com",
      "sub": "agent_alpha_789",
      "aud": "agent_beta_456",
      "delegated_at": 1714348800,
      "scope": "email:read",
      "purpose": "Summarize unread emails"
    }
  ]
}
```

### Step 5: Resource Access with Full Credentials

When Agent Beta calls the email API, it presents its token. The API validates:

1. **Signature**: Verify JWT signature using Authorization Server's public keys
2. **Agent claims**: Confirm `agent_type`, `agent_model`, `agent_provider`
3. **Attestation**: Verify the EAT token proves the agent runs in a trusted environment
4. **Delegation chain**: Validate each step in the chain—the final scope (`email:read`) is a subset of Alice's original grant
5. **Constraints**: Ensure the request is within `allowed_resources` and time limits

```http
GET /api/emails/unread
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...

# The API decodes and validates:
# - Agent identity: gpt-4o from acme.ai
# - Delegation chain: user_alice -> alpha -> beta
# - Purpose: email summarization
# - Attestation: verified via EAT
```

## Security Considerations

The OIDC-A specification emphasizes several critical security aspects:

1. **Strong authentication**: Agents must use asymmetric methods (JWT Client Auth with private keys, mTLS), not shared secrets
2. **Chain validation**: Every step in the delegation chain must be validated—scope reduction, trusted issuers, chronological order
3. **Attestation verification**: Use nonces to prevent replay attacks, verify cryptographic signatures against trusted keys
4. **Token encryption**: ID tokens containing agent claims should be encrypted to protect sensitive metadata
5. **Time-bounding**: Delegations should expire; policies may limit chain length to prevent "delegation creep"

## Privacy Considerations

Agent identity introduces new privacy concerns:

- **Correlation risk**: Agent IDs can track user behavior across services
- **Delegation visibility**: Full delegation chains reveal user workflow patterns
- **Data minimization**: Services should request only the claims they need

## What's Next: The Road to Standardization

We're in the early days. The OIDC-A proposal is version 1.0; the IETF drafts are in "Network Working Group" status—meaning they're being discussed but not yet ratified. Here's what needs to happen:

1. **Convergence**: The various proposals (OIDC-A, AIMS, ACAP, AIP) need to align on core concepts while allowing flexibility
2. **Implementation**: Real-world deployments will surface edge cases and drive refinement
3. **Industry adoption**: Major cloud providers and AI labs need to implement and operationalize these standards
4. **Interoperability testing**: Ensure tokens issued by one provider work with resources from another

The OpenID Foundation's whitepaper and working groups provide the venue for this convergence. Given the pace of AI agent adoption, standardization will likely accelerate throughout 2026.

## References

**Primary Sources:**
- OIDC-A 1.0 Proposal (Subramanya N): [subramanya.ai/2025/04/28/oidc-a-proposal/](https://subramanya.ai/2025/04/28/oidc-a-proposal/)
- OIDC-A 1.0 Paper (arXiv): [arxiv.org/html/2509.25974v1](https://arxiv.org/html/2509.25974v1)
- IETF AIMS Draft: [ietf.org/archive/id/draft-klrc-aiagent-auth-00.html](https://www.ietf.org/archive/id/draft-klrc-aiagent-auth-00.html)
- ACAP Draft: [ietf.org/archive/id/draft-yakung-oauth-agent-attestation-00.html](https://www.ietf.org/archive/id/draft-yakung-oauth-agent-attestation-00.html)

**Community Resources:**
- OpenID Foundation Whitepaper: "Identity Management for Agentic AI" (October 2025)
- Agentic Trust Blog: [agentictrust.com/blog/openid-connect-for-agents-securing-llm-identity-with-oidc-a-10](https://agentictrust.com/blog/openid-connect-for-agents-securing-llm-identity-with-oidc-a-10)
- OIDC-A GitHub: [github.com/subramanya1997/oidc-a](https://github.com/subramanya1997/oidc-a)
- A2A Protocol: [a2aproject/A2A](https://github.com/a2aproject/A2A)

**Ecosystem:**
- Tobin South (Stanford/WorkOS/Anthropic): [tobin.page](http://tobin.page/)
- OpenID Foundation: [openid.net](https://openid.net)