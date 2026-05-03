# Agentic ERP Analytics Demo

A lightweight ERP analytics scaffold for a small distribution company. It uses synthetic, in-memory ERP data and deterministic rules, then layers read-only copilot-style summaries, risk explanations, and workflow recommendations on top of the same operational snapshot.

This is not a full ERP implementation yet. It does not include persistence, transaction posting, accounting periods, permissions, audit logs, or autonomous write actions.

## Scope

The MVP covers the ERP workflows that make the system feel integrated:

- Inventory, products, vendors, and reorder points
- Purchase orders and supplier delay risk
- Sales orders and fulfillment pressure
- Customer invoices and overdue receivables
- Simplified cash and inventory reporting
- Rules-based copilot summaries, risk flags, and question answering

Deferred areas include persistence, payroll, manufacturing, tax compliance, multi-currency accounting, full accounting correctness, and autonomous transaction execution.

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

The system uses three layers:

1. `erp_core.py`: seeded ERP data and deterministic business calculations.
2. `ai_copilot.py`: explainable recommendations and constrained natural-language intent handling.
3. `app.py`: a dependency-free local web dashboard.

Copilot behavior is intentionally read-only. It explains, prioritizes, and recommends actions, but business state changes should remain explicit ERP transactions.
