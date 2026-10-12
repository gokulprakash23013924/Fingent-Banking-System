# Intelligent Multi-Agent Banking Simulator with Observe–Think–Act Architecture

A production-grade, end-to-end intelligent banking assistant MVP demonstrating how multiple AI agents collaborate to solve complex banking scenarios through natural-language interaction, simulated banking APIs, dynamic task planning, native tool calling, and controlled self-correction.

---

## 1. System Architecture

The platform is designed around a decoupled, micro-orchestrated architecture:

```
[ User / Frontend Client ]
          │ (Natural Language + Bearer Token)
          ▼
[ FastAPI Backend / Auth Gate (`/auth/login`, Session Verification) ]
          │ Validated Customer / Supervisor Session Context
          ▼
[ Supervisor / Orchestrator Agent (Observe–Think–Act–Evaluate–Correct) ]
          │
    ┌─────┴──────────────────────────────────────────────────────┐
    │                                                            │
    ▼                                                            ▼
[ Unified NLU & LLM Tool Selection ]               [ State Machine & DAG Planner ]
(OpenAI / Anthropic Function Calling or Mock)             (Parallel Execution, Dependencies)
    │                                                            │
    └─────────────────────────────┬──────────────────────────────┘
                                  ▼
[ Specialized Agents & Real Tool Registry ]
 ├── Banking Agent   ──> `get_balance`, `get_transactions`, `get_accounts`, `transfer_funds`
 ├── Fraud Agent     ──> `find_transaction`, `score_transaction`, `block_card`, `create_dispute`
 ├── Credit Agent    ──> `get_bureau_score`, `check_eligibility`, `calculate_emi`, `create_loan_application`
 ├── Compliance Agent──> `get_kyc_status`, `run_aml_check`, `retrieve_policy`
 └── Notification Ag.──> `generate_alert`, `list_alerts`
                                  │
                                  ▼
[ Safety & Governance Layer ]
 ├── Customer Data Isolation (403 on Cross-Customer Access)
 ├── Human-in-the-Loop Approval Queue (Sensitive Write Operations)
 ├── Strict Idempotency & Bounded Self-Correction (Max 2 Safe Retries)
 └── Auditable Execution Trace & Telemetry Observatory
                                  │
                                  ▼
[ Deterministic Source of Truth: SQLite Database & Anomaly Models ]
```

---

## 2. Dynamic LLM-Driven Tool Calling vs. Rule-Based Fallback

### Native Structured Tool / Function Calling
When configured with a live provider (`LLM_PROVIDER=openai` or `LLM_PROVIDER=anthropic`), the system:
1. Passes OpenAI-compatible JSON schemas describing all registered tools, their parameters, data types, and required fields to the LLM.
2. The LLM understands user intent dynamically—accommodating slang, varied phrasing, follow-up context, and multi-intent requests without relying on keyword-based regex or hardcoded dictionary lookups.
3. The LLM emits structured tool calls (`tool_calls: [{"name": "...", "arguments": {...}}]`).
4. The backend validates arguments against Pydantic schemas, verifies caller permissions, and executes the actual backend tools against the database.
5. Tool execution results are returned directly into the LLM context for evaluation and final response generation.

### Demo / Mock Mode & Language Variety
In offline demo mode (`LLM_PROVIDER=mock`, which requires **no external API key**):
- **Conversational Dialogue & Greetings**: General greetings ("Hi", "Hey", "Hello", "Good morning", "How are you?") are handled naturally without making unnecessary banking tool calls.
- **Dynamic Semantic Parser**: Extracts amounts, tenures, transactions, and intents across varied paraphrases.
- **Multi-Intent Handling**: Composite requests such as *"What is my balance, and show me my last five transactions?"* dynamically trigger both `get_balance` and `get_transactions` in sequence.
- **Clarification & Ambiguity**: Vague requests (*"Help me with my money"*) prompt focused clarifying questions rather than hallucinating financial advice.
- **Transparent Disclosure**: All mock responses clearly identify that simulated reasoning was utilized, preventing confusion with live LLM inferences.

---

## 3. Observe–Think–Act–Evaluate–Correct (OTA) Lifecycle

Every request follows an auditable 5-stage lifecycle managed by the Supervisor Agent:

1. **Observe (State Inspection)**:
   - Captures the incoming natural-language message, conversation history, and authenticated session context.
   - Extracts semantic slots (e.g., amount, tenure, transaction ID) and identifies missing requirements.
   - For pure conversational greetings, completes immediately with a warm greeting and zero tool calls.

2. **Think (Structured Task Planning)**:
   - Formulates a Directed Acyclic Graph (DAG) of subtasks.
   - Assigns subtasks to specialized agents (Banking, Credit, Fraud, Compliance).
   - Identifies independent tasks to run concurrently (e.g., Credit, Fraud, and Compliance checks for loan underwriting).

3. **Act (Controlled Tool Execution)**:
   - Executes authorized tools against the live SQLite database.
   - Validates tool arguments against strict schemas.
   - Enforces role-based permissions: write operations (`block_card`, `create_loan_application`, `transfer_funds`) are halted and routed to the Human-in-the-Loop approval queue.

4. **Evaluate (Result Verification)**:
   - Validates retrieved data against policy rules, KYC status, and bureau thresholds.
   - Verifies that state changes actually occurred and data consistency is maintained.

5. **Correct (Safe Bounded Self-Recovery)**:
   - Transient read errors or schema mismatches trigger up to 2 safe bounded retries.
   - Financial write operations are strictly non-retryable without re-authorization to prevent duplicate charges or applications.

---

## 4. Specialized Agents & Responsibilities

| Agent | Responsibilities | Callable Tools |
| :--- | :--- | :--- |
| **Supervisor / Orchestrator** | Task planning, agent coordination, evaluation, approval routing, clarification | `delegate_agent_task`, `collect_agent_result`, `verify_task_completion` |
| **Banking / Customer Agent** | Account balances, account details, transaction history, funds transfers | `get_customer_profile`, `get_accounts`, `get_balance`, `get_transactions`, `get_card_status`, `transfer_funds`* |
| **Fraud / Risk Agent** | Suspicious transaction scoring, device fingerprinting, card locking, disputes | `find_transaction`, `score_transaction`, `get_device_history`, `assess_recent_risk`, `get_card_status`, `block_card`*, `create_dispute`* |
| **Credit / Loan Agent** | Bureau score lookup, eligibility assessment, EMI calculation, loan origination | `get_bureau_score`, `check_eligibility`, `calculate_emi`, `get_loan_offers`, `list_loan_applications`, `create_loan_application`* |
| **Compliance Agent** | KYC status verification, AML sanction screening, policy retrieval | `get_kyc_status`, `run_aml_check`, `retrieve_policy` |
| **Notification Agent** | Security alerts, transaction confirmations, approval decision notices | `list_alerts`, `generate_alert` |

*\*Write operations require supervisor or customer confirmation via the Human Approval Queue.*

---

## 5. Authentication & Access Control

The platform implements session-based authentication with salted SHA-256 password hashing and Bearer token verification (`nxt_<hex>` tokens).

### Demo Accounts

| Username | Role | Password | Description / Customer Profile |
| :--- | :--- | :--- | :--- |
| `C001` | Customer | `password123` | **Aarav Sharma** - Tier 1, High bureau score (780), eligible for loans |
| `C002` | Customer | `password123` | **Diya Patel** - Tier 2, Suspicious ₹48,000 transaction subject to dispute |
| `C003` | Customer | `password123` | **Rohan Mehta** - Tier 1, Standard savings & credit profile |
| `C004` | Customer | `password123` | **Ananya Iyer** - Tier 3, Pending KYC (triggers Compliance Hold on loans) |
| `C005`–`C010`| Customer | `password123` | Additional verified customer demo accounts |
| `supervisor` | Supervisor | `admin123` | **Operations Lead** - Central approval queue & bank-wide investigation |
| `rm001` | Supervisor | `admin123` | **Senior Relationship Manager** - Full administrative access |

### Strict Customer Data Isolation
- Customer identities are enforced server-side via the authenticated session token.
- Any attempt by an authenticated customer (e.g., `C001`) to access another customer's records (`C002`) via API endpoints or tool parameters results in an immediate **`HTTP 403 Forbidden`** (`Access denied: cannot view another customer's data`).
- Supervisors and RMs have authorized view permissions across all accounts for investigation and approval management.

---

## 6. Human Approval Workflow

State-changing operations (such as blocking cards, submitting disputes, or finalizing loan applications) cannot be auto-executed by the LLM:

1. When a state-changing action is requested, the Supervisor records a pending approval request in SQLite with status `PENDING`.
2. The request enters the central **Supervisor Approval Queue** with full context: requesting customer, action type, amount/card details, and risk evaluation.
3. An authorized supervisor or relationship manager reviews the request and clicks **Approve** or **Reject**.
4. Upon approval, the backend re-validates permissions and executes the state-changing tool **exactly once** (protected by idempotency keys).
5. State verification ensures the database is updated (e.g., card status changed to `BLOCKED`, loan ID issued `LN-...`).
6. A notification alert is dispatched to the customer's feed, and the audit log records the approving supervisor, timestamp, and result.

---

## 7. The Six Core Banking Use Cases

### Use Case 1: Account Balance and Mini-Statement
- **Natural Language Input**: *"What is my balance, and show me my last five transactions?"*
- **Execution**: The Supervisor decomposes the composite intent, invokes `get_balance` and `get_transactions`, and presents a verified summary in INR with actual transaction records from the database.

### Use Case 2: Suspicious Transaction Investigation
- **Natural Language Input**: *"I don't recognise this ₹48,000 payment. Please investigate it."*
- **Execution**: The Fraud Agent retrieves the ₹48,000 transaction (`T1001`), computes deterministic risk rules and ML anomaly scores (flags late-night international POS activity, score 85/100), and initiates a Human-in-the-Loop approval gate to freeze the card and register a dispute (`DSP-...`).

### Use Case 3: Loan Eligibility and EMI Calculation
- **Natural Language Input**: *"Can I apply for a ₹5 lakh loan over three years? What would the EMI be?"*
- **Execution**: The Credit Agent checks the customer's credit score (780 for `C001`), evaluates eligibility according to lending policy guidelines, calculates exact monthly EMI using standard formulas (₹16,134/month @ 10.5%), and clearly distinguishes estimated eligibility from an approved loan.

### Use Case 4: Multi-Agent Loan Application (Concurrent Underwriting)
- **Natural Language Input**: *"Check my eligibility and prepare a loan application."*
- **Execution**: The Supervisor schedules concurrent checks across **Credit** (eligibility check), **Fraud** (risk evaluation), and **Compliance** (KYC/AML verification). If KYC is incomplete (`C004`), the application is placed on a compliance hold. If all checks pass (`C001`), a pending loan approval request (`LN-...`) is staged for supervisor sign-off.

### Use Case 5: Simulated Live Fraud Monitoring
- **Execution**: A background transaction generator produces synthetic debit card transactions. The risk engine assesses each transaction in real-time, instantly logging high-risk events to the alert feed without consuming LLM tokens.

### Use Case 6: Ambiguous or Unsupported Requests
- **Natural Language Input**: *"Help me with my money"* or *"Invest all my savings for me."*
- **Execution**: The NLU detects the ambiguity or out-of-scope investment advisory intent. Instead of hallucinating financial advice, it asks clarifying questions or clearly explains system boundaries, offering human RM assistance.

---

## 8. Setup & Installation

### Prerequisites
- Python 3.10+
- Node.js 18+ and npm

### Backend Setup (FastAPI)
```bash
# 1. Navigate to backend directory
cd banking-agents

# 2. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env

# 5. Seed SQLite database and train ML anomaly models
python -m data.seed
python -m app.ml.train

# 6. Start the FastAPI server
uvicorn app.main:app --host 127.0.0.1 --port 8000
```
API Documentation will be available at `http://127.0.0.1:8000/docs`.

### Frontend Setup (React + Vite)
```bash
# 1. Navigate to frontend directory
cd frontend

# 2. Install dependencies
npm install

# 3. Start Vite development server
npm run dev
```
Open your browser at `http://127.0.0.1:5173`.

---

## 9. Environment Variables & LLM Provider Configuration

Configure `banking-agents/.env` according to your deployment target:

```ini
# LLM Provider Configuration ("mock", "openai", or "anthropic")
LLM_PROVIDER=mock

# Live Provider Credentials (not required in mock mode)
LLM_API_KEY=
LLM_MODEL=gpt-4o-mini

# Database & Runtime
DATABASE_PATH=data/banking.db
APP_ENV=development
PORT=8000
```

> **Security Note:** Never commit API keys or production secrets to source control. The system securely reads secrets from environment variables or `.env`.

---

## 10. Automated Testing

The repository contains an end-to-end automated test suite verifying natural language understanding, multi-agent orchestration, approval gates, role-based isolation, and banking algorithms.

Run the complete test suite:
```bash
cd banking-agents
pytest tests/ -v
```

### Verified Test Results (73 / 73 Tests Passing)
```
tests/test_api_smoke.py (8 passed)
  - /health and database connectivity
  - Customer endpoints & role validation
  - Balance & transaction queries
  - Approval queue inspection

tests/test_dynamic_llm_and_auth.py (17 passed)
  - Greetings receive natural conversation without banking tools
  - Paraphrased and follow-up query resolution
  - Composite multi-intent tool orchestration
  - Ambiguous query clarification & out-of-scope boundaries
  - Salted SHA-256 authentication and Bearer token issuance
  - Strict customer data isolation (HTTP 403 enforcement)
  - Approval queue security and supervisor execution
  - Multi-agent loan underwriting pipeline

tests/test_engines.py (10 passed)
  - Deterministic EMI calculation formulas
  - Credit score policy thresholds
  - Rule-based & Isolation Forest anomaly scoring

tests/test_observe_think_act.py (10 passed)
  - Full end-to-end verification of Use Cases 1 through 6
  - Self-evaluation and bounded recovery safety
  - Customer ownership boundaries

tests/test_supervisor.py (20 passed)
  - DAG task planner execution
  - Orchestrator state transitions
  - Retry counter bounds & error handling

tests/test_tools.py (8 passed)
  - Tool registry schema validation
  - Permission allowlist enforcement
  - Tamper-evident audit logging

============================= 73 passed in 42.02s =============================
```

---

## 11. Known Limitations & Mock vs. Real Mode Differences

1. **Mock Mode Language Variety**: The mock engine provides semantic slot extraction and comprehensive intent mapping for banking scenarios, but does not generalize to arbitrary open-domain conversational topics outside banking and greetings.
2. **Real LLM Mode Dependency**: Using `LLM_PROVIDER=openai` or `LLM_PROVIDER=anthropic` requires an active internet connection and valid API credits. If the API is unreachable, the system returns a clear error instead of silently falsifying outputs.
3. **Simulated External Rails**: Financial rails (UPI, NEFT, Credit Bureaus, and KYC registries) are simulated against SQLite. No actual external banking networks or government databases are contacted.
