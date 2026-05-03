# Agentic ERP Analytics Demo

A lightweight ERP analytics scaffold for a small distribution company. It starts from synthetic ERP data, persists local demo state as JSON, and layers deterministic copilot-style summaries, risk explanations, and workflow recommendations on top of the same operational snapshot.

This is not a full ERP implementation yet. It does not include production database storage, transaction posting, accounting periods, permissions, or autonomous write actions.

## Scope

The MVP covers the ERP workflows that make the system feel integrated:

- Inventory, products, vendors, and reorder points
- Purchase orders and supplier delay risk
- Sales orders and fulfillment pressure
- Customer invoices and overdue receivables
- Simplified cash and inventory reporting
- Rules-based copilot summaries, risk flags, and question answering
- Natural-language workflow commands for reorder, receiving, and invoice payment
- Local JSON persistence for the demo state and audit activity log

Deferred areas include production database storage, payroll, manufacturing, tax compliance, multi-currency accounting, full accounting correctness, and autonomous transaction execution.

## Run

```bash
python3 app.py
```

Then open `http://127.0.0.1:8000`.

## Test

```bash
python3 -m unittest
```

## Design

The system uses four layers:

1. `erp_core.py`: seeded ERP data and deterministic business calculations.
2. `ai_copilot.py`: explainable recommendations, constrained natural-language intent handling, and an optional LLM answer path.
3. `llm_client.py`: dependency-free OpenAI Responses API client using `OPENAI_API_KEY`.
4. `app.py`: a dependency-free local web dashboard.

Copilot behavior is intentionally read-only. It explains, prioritizes, and recommends actions, but business state changes should remain explicit ERP transactions.

## Usable MVP Workflows

The dashboard includes a `Command ERP` panel and quick-action buttons. Supported deterministic commands include:

- `reorder PUMP-A`
- `create a purchase order for Sensor T`
- `receive PO-1001`
- `mark INV-9001 paid`

Workflow changes are saved to `data/erp_state.json`, and the activity log is saved to `data/audit.jsonl`. Both files are ignored by git.

Operational checks:

- `GET /healthz` returns process health and app metadata.
- `GET /readyz` verifies that ERP modules and local state can be loaded.

## Optional LLM Mode

The app uses deterministic rules by default. If `.env` or the shell environment provides `OPENAI_API_KEY`, the Ask ERP panel calls the OpenAI Responses API and gives the model only a read-only, JSON summary of the ERP snapshot and the deterministic rules answer.

Supported environment keys:

- `OPENAI_API_KEY`
- `OPENAI_MODEL`, optional, defaults to `gpt-5.4`
- `OPENAI_TIMEOUT_SECONDS`, optional, defaults to `20`
- `OPENAI_BASE_URL`, optional, defaults to `https://api.openai.com/v1`
- `OPENAI_CA_BUNDLE`, optional path to a CA bundle when local Python certificate discovery is broken

Run a live smoke test with:

```bash
python3 -m llm_client "Reply OK for the ERP LLM smoke test."
```
