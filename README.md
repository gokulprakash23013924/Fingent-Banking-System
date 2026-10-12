
# Fingent: Multi-Agent Banking Platform

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![FastAPI](https://img.shields.io/badge/backend-FastAPI-009688)
![React](https://img.shields.io/badge/frontend-React%20%2B%20Vite-61dafb)
![Database](https://img.shields.io/badge/database-SQLite-003b57)

Fingent is a simulated banking assistant where a **Supervisor agent** coordinates specialised agents (Banking, Fraud, Credit, Compliance, Notification) to answer natural-language requests such as *"I don't recognise this ₹48,000 payment"* or *"Can I get a ₹5 lakh loan over three years?"*.

Every request runs through an auditable **Observe → Think → Act → Evaluate → Correct** loop, and anything that changes state (blocking a card, filing a dispute, creating a loan application, large transfers) waits in a **human approval queue** instead of auto-executing.

> All banking rails (UPI, credit bureau, KYC registry) are simulated in SQLite. No real financial systems are contacted.

## Why it's useful

- **LLM-last routing.** A four-tier ladder tries exact rules (Tier 0) and a small local classifier (Tier 1) before ever calling an LLM (Tiers 2 and 3), which keeps common requests fast and token-free.
- **Runs without an API key.** The default `mock` provider works fully offline, so you can explore the whole system immediately.
- **Safe by design.** Server-side customer data isolation (HTTP 403 on cross-customer access), PII masking, idempotent approvals, bounded retries (max 2, never on financial writes), and an audit trail.
- **Transparent.** An in-app Observatory shows each request's plan, tool calls and routing tier.
- **Configurable policy.** Loan limits, credit-score cut-offs, FOIR, and fraud thresholds live in [`banking-agents/config/policies.yaml`](banking-agents/config/policies.yaml), not in code.

## Architecture
<img width="1377" height="918" alt="WhatsApp Image 2026-10-12 at 9 50 44 PM" src="https://github.com/user-attachments/assets/0a2140e9-1195-401c-abcb-77e0e395043f" />




## Screenshots

### Sign in

One-click demo credentials for customers and supervisors.
<img width="1870" height="992" alt="Screenshot 2026-10-12 203438" src="https://github.com/user-attachments/assets/66eaab1a-81a5-478c-9663-a31e17cb7082" />


### Customer portal

The AI banking assistant answers in natural language. The side panel shows the customer context and a live Observe–Think–Act inspector (workflow state, observed intent, agents used, self-evaluation, latency).
<img width="1870" height="992" alt="Screenshot 2026-10-12 203534" src="https://github.com/user-attachments/assets/aa0794a6-efb1-4309-862a-aba0eb2a26a8" />



Accounts, cards, credit score, KYC status, loan facilities, and recent transactions with real-time Isolation Forest fraud scoring.
<img width="1870" height="992" alt="Screenshot 2026-10-12 203600" src="https://github.com/user-attachments/assets/6eb0e844-3c33-4d87-8705-658301d9ef00" />


### Supervisor / RM portal

Bank-wide Customer 360 view with the same account, card, and transaction detail for any customer.
<img width="1871" height="991" alt="Screenshot 2026-10-12 203657" src="https://github.com/user-attachments/assets/f6515c0f-82eb-42a7-a243-47e6ab344f80" />



The Supervisor AI Assistant allows cross-customer queries, which customer accounts do not.
<img width="1866" height="992" alt="Screenshot 2026-10-12 204011" src="https://github.com/user-attachments/assets/527eb9b7-9e61-49c8-89cc-8e9ccb86c2f0" />


## Project layout

| Path | What it is |
| :--- | :--- |
| [`banking-agents/`](banking-agents) | FastAPI backend: agents, supervisor, tools, ML models, tests, benchmark |
| [`frontend/`](frontend) | React + Vite dashboard (chat, customer view, approvals, observatory, alerts) |
| [`architecture_report/`](architecture_report) | In-depth architecture docs (lifecycle, agents, safety, ML, frontend) |

## Getting started

**Prerequisites:** Python 3.10+ and Node.js 18+.

### 1. Start the backend

```bash
cd banking-agents
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # defaults to LLM_PROVIDER=mock (no key needed)
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

On first start the app creates and seeds `data/bank.db` and warms its small ML models automatically. To do this ahead of time, run `python -m data.seed` and `python -m app.ml.train`.

Interactive API docs: <http://127.0.0.1:8000/docs>

### 2. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://127.0.0.1:5173>. The dev server proxies API calls to port 8000; to point at another backend, set `VITE_API_URL`.

### 3. Log in with a demo account

| Username | Password | Role | Notes |
| :--- | :--- | :--- | :--- |
| `C001` | `password123` | Customer | Aarav Mehta: credit score 780, verified KYC, clean loan path |
| `C002` | `password123` | Customer | Diya Nair: flagged ₹48,000 foreign payment (`T900001`) |
| `C003` | `password123` | Customer | Rohan Das: score below policy minimum, loan declined |
| `C004` | `password123` | Customer | Meera Iyer: KYC pending, loan referred to Compliance |
| `C005`–`C010` | `password123` | Customer | More scenarios: high obligations, risky history, expired KYC, AML flag |
| `supervisor` | `admin123` | Supervisor | Approval queue and bank-wide view |
| `rm001` | `admin123` | Relationship Manager | Full administrative access |

These are demo credentials for local use only.

### 4. Try it

Log in as `C001` and ask:

- *"What's my balance and my last five transactions?"*
- *"Can I apply for a ₹5 lakh loan over three years? What would the EMI be?"*
- *"Check my eligibility and prepare a loan application."* (runs Credit, Fraud and Compliance in parallel, then waits for supervisor approval)

Log in as `C002` and ask *"I don't recognise this ₹48,000 payment."* to see the Fraud agent investigate and stage a card block and dispute for approval. Then log in as `supervisor` to approve or reject it.

Or call the API directly:

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"C001","password":"password123"}' | python -c "import sys,json; print(json.load(sys.stdin)['token'])")

curl -s -X POST http://127.0.0.1:8000/chat \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"message":"What is my balance?","customer_id":"C001","role":"customer"}'
```

## Configuration

Settings are read from `banking-agents/.env` (see [`.env.example`](banking-agents/.env.example) for every option).

| Variable | Purpose |
| :--- | :--- |
| `LLM_PROVIDER` | `mock` (offline, default), `none`, `anthropic`, or `openai` (any OpenAI-compatible endpoint) |
| `LLM_API_KEY`, `LLM_BASE_URL` | Credentials and endpoint for a live provider |
| `LLM_TIER2_MODEL`, `LLM_TIER3_MODEL` | Models used for the LLM tiers |
| `MAX_TOKENS_PER_REQUEST`, `MAX_LLM_CALLS_PER_REQUEST` | Per-request budget limits |
| `STREAM_ENABLED` | Generate a live synthetic transaction stream scored by the fraud engine |
| `BANK_DB_PATH` | SQLite database location |
| `CORS_ORIGINS` | Allowed browser origins (default `*`; restrict this outside local use) |

Never commit `.env` or API keys; `.env` is already git-ignored.

## Running tests and the benchmark

```bash
cd banking-agents
pytest -q                    # or: python -m tests.run_all  (no pytest needed)
python -m eval.run           # routing benchmark; see --mode ladder|llm_only|offline
```

Frontend lint: `cd frontend && npm run lint`.

The optional Streamlit UI (`banking-agents/ui/streamlit_app.py`) needs `pip install streamlit`, which is not in `requirements.txt`.

## Documentation

- [Backend guide](banking-agents/README.md): agents, tools, approval workflow, the six core use cases
- [Architecture report](architecture_report/README.md): system design, orchestration lifecycle, NLU ladder, safety and guardrails, ML and rule engines, frontend
- Interactive API reference at `/docs` when the backend is running

## Getting help

- Browse the documentation above first.
- Open a [GitHub issue](https://github.com/gokulprakash23013924/Fingent-Banking-System/issues) for bugs, questions, or feature requests. Include your Python/Node versions, your `LLM_PROVIDER`, and the steps to reproduce.

## Maintainers and contributing

Maintained by [@gokulprakash23013924](https://github.com/gokulprakash23013924).

Contributions are welcome:

1. Fork the repo and create a feature branch.
2. Make your change and run `pytest -q` in `banking-agents/` (and `npm run lint` in `frontend/` for UI changes).
3. Open a pull request describing what changed and why.

There is no `CONTRIBUTING.md` or `LICENSE` file in the repository yet; add one before reusing or redistributing the code.
