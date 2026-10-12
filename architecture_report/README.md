# Fingent: Complete Architecture & Orchestration Report Suite

Welcome to the comprehensive architecture and orchestration documentation suite for **Fingent: Autonomous Multi-Agent Banking Platform**.

This dedicated report collection provides an exhaustive, production-grade technical breakdown of the entire platform—from system topology and multi-agent orchestration lifecycles to security guardrails, data structures, machine learning anomaly engines, and frontend telemetry.

---

## 📑 Report Navigation Index

| Document | Focus Area | Key Architectural Topics Covered |
| :--- | :--- | :--- |
| **[01. High-Level System Architecture](01_SYSTEM_ARCHITECTURE.md)** | **Topologies & Perimeters** | • Full system topology & tier interactions<br/>• Directory layout & module organization<br/>• SQLite database relational schema (ERD)<br/>• Authentication, Bearer sessions (`nxt_<hex>`), & RBAC matrix |
| **[02. Orchestration & Workflow Lifecycle](02_ORCHESTRATION_AND_LIFECYCLE.md)** | **OTAEC State Machine** | • Observe–Think–Act–Evaluate–Correct lifecycle<br/>• Workflow finite state machine (11 states)<br/>• DAG task decomposition & parallel groups<br/>• Concurrent multi-agent underwriting (Credit + Fraud + Compliance)<br/>• Self-evaluation invariants & bounded safe recovery |
| **[03. Specialized Domain Agents](03_MULTI_AGENT_SPECIFICATION.md)** | **Agent Capabilities & Tools** | • BaseAgent abstraction & budget counters<br/>• Supervisor, Banking, Fraud, Credit, Compliance, Notification agents<br/>• Complete tool registry permission matrix (24 tools)<br/>• Input/output contracts and error boundaries |
| **[04. NLU, Ladder & Tool Calling](04_NLU_LADDER_AND_TOOL_CALLING.md)** | **Language & Model Routing** | • Dual NLU architecture<br/>• 4-tier cost-avoidance ladder (Tier 0 to Tier 3)<br/>• Native structured function calling (OpenAI & Anthropic schemas)<br/>• Offline Mock intelligence engine (zero API keys required)<br/>• Typo normalizer & colloquial language handling |
| **[05. Safety, Guardrails & HITL](05_SAFETY_GUARDRAILS_AND_HITL.md)** | **Governance & Defenses** | • Customer data isolation (HTTP 403 on cross-access)<br/>• Human-in-the-Loop (HITL) approval queue for write operations<br/>• Idempotency key locks preventing duplicate execution<br/>• PII masking (PAN, Aadhaar, Cards, Phone, Email)<br/>• Indirect prompt injection neutralization<br/>• Mathematical output grounding (hallucination defense) |
| **[06. Data, ML & Rule Engines](06_DATA_ML_AND_RULE_ENGINES.md)** | **Models & Financial Math** | • 10 realistic customer personas (`C001`–`C010`)<br/>• Isolation Forest fraud anomaly engine & feature vectors<br/>• Deterministic EMI equation & FOIR borrowing capacity<br/>• Rate cards tied to CIBIL bureau scores<br/>• TF-IDF + LogisticRegression intent classification |
| **[07. Frontend & Observatory](07_FRONTEND_AND_OBSERVATORY.md)** | **Presentation & Telemetry** | • React 18 + Vite SPA architecture<br/>• Obsidian Glassmorphism design system<br/>• Component hierarchy (`ChatView`, `CustomerView`, `Navbar`, etc.)<br/>• Inline OTA telemetry cards & interactive approval buttons<br/>• Session-isolated chat persistence & real-time alerts |

---

## 🏛️ Executive Architectural Summary

### 1. The Observe–Think–Act–Evaluate–Correct (OTAEC) Paradigm
Fingent transitions away from brittle, single-prompt LLM wrappers. Instead, every customer interaction is managed by an auditable state machine:
1. **Observe**: Sanitizes colloquialisms and typos, scrubs PII, detects ambiguities, and extracts semantic entities.
2. **Think**: Formulates a Directed Acyclic Graph (DAG) of subtasks, assigning domain duties across specialized agents.
3. **Act**: Dispatches authorized tools against the live database; runs parallel tasks concurrently via a thread pool.
4. **Evaluate**: Deterministically validates results against policy invariants, KYC compliance, and customer identity boundaries.
5. **Correct**: Handles transient read errors with bounded retries (max 2), while strictly prohibiting blind retries on state-changing financial writes.

### 2. Defense-in-Depth Security & Governance
- **Human-in-the-Loop Gatekeeping**: High-risk financial operations (`block_card`, `create_dispute`, `create_loan_application`, and transfers $\ge ₹50,000$) **never auto-execute**. They are staged into a persistent SQLite approval queue, requiring explicit customer or supervisor confirmation.
- **Strict Customer Isolation**: Validated session tokens enforce identity server-side. Cross-customer data inquiries from customer roles return an immediate **HTTP 403 Forbidden**.
- **Indirect Prompt Injection Defense**: External transaction descriptions and merchant text are screened for instruction hijacking phrases before being surfaced to model reasoning.
- **Mathematical Grounding**: Every number quoted in an agent's answer must exist in verified database records, preventing invented balances or loan rates.

### 3. Cost-Optimization & Dual NLU
- High-frequency, deterministic tasks (e.g. balance lookups) are resolved by exact regex (Tier 0) or local statistical machine learning (Tier 1) in under 5 milliseconds with **zero token cost**.
- Dynamic, composite, or varied queries escalate through the Gateway to live LLM function calling or the offline mock engine.

---

## 🧪 Verification & Automated Test Suite

The entire architectural implementation is validated by an automated test suite verifying every component, safety perimeter, and banking algorithm:

```bash
cd banking-agents
pytest tests/ -q
```

**Results**: All **127 automated tests pass (100% pass rate)** in 77 seconds:
- ✅ Unit & smoke API endpoints
- ✅ 50+ general language queries, edge cases, and typo resilience
- ✅ Multi-agent loan underwriting & parallel aggregation
- ✅ Customer identity isolation & 403 authorization gates
- ✅ Human-in-the-loop approval staging and single-execution idempotency
- ✅ Isolation Forest fraud scoring & Isolation Forest vectorization
- ✅ EMI formulas, FOIR math, and lending rate cards
- ✅ Cost-avoidance ladder escalation and fallback clarification
