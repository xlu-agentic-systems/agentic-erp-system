# React Native Migration Plan

## Goal

Replace the raw server-rendered HTML/CSS product surface with a React Native frontend while preserving the Python ERP backend, SQLite persistence, workflow atomicity, audit behavior, and existing operational checks.

The migration should be incremental. The backend must expose stable JSON APIs before the React Native app depends on it, and the legacy HTML routes should remain functional until the React Native surface covers the dashboard and workflows.

## Product Scope

The React Native app must cover:

- Operating dashboard KPIs, risk flags, role summaries, and activity.
- Inventory, fulfillment risk, AR aging, sales order, purchase order, and invoice views.
- Ask ERP read-only question flow.
- Command ERP preview/run flow.
- Quick actions for create PO, receive PO, pay invoice, and reset, with safer confirmation for reset.
- Backend health/readiness awareness and clear error states.

## Backend API Contract Plan

Use versioned JSON endpoints under `/api/v1`:

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/dashboard` | `GET` | Dashboard snapshot, including KPIs, risks, tables, audit, and storage metadata safe for clients. |
| `/api/v1/ask` | `POST` | Ask ERP question; returns answer without mutating state. |
| `/api/v1/command/preview` | `POST` | Preview deterministic command; must not mutate state or audit. |
| `/api/v1/command/run` | `POST` | Execute deterministic command; successful mutations persist and audit atomically. |
| `/api/v1/actions` | `POST` | Execute quick action by action type and parameters. |
| `/api/v1/health` | `GET` | Client-friendly process health. |
| `/api/v1/ready` | `GET` | Client-friendly readiness and storage status. |
| `/api/v1/metrics` | `GET` | Existing request counters for operational checks. |

Response shape:

```json
{
  "ok": true,
  "data": {},
  "error": null
}
```

Error shape:

```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "validation_error",
    "message": "Unknown ERP action."
  }
}
```

## React Native Technical Direction

- Use Expo with TypeScript under `frontend/`.
- Keep the backend URL configurable through environment or app config.
- Build a small typed API client before UI screens.
- Prefer component tests and API-client tests that run in CI without a simulator.
- Use native controls and dense operational layouts rather than marketing-style pages.

## QA Checklist

- Python tests remain green after every cycle.
- SQLite workflow persistence remains covered by tests after API extraction.
- JSON APIs assert status codes, content types, success/error envelopes, and no HTML dependency.
- React Native tests cover loading, empty, error, and successful data states.
- Command preview does not mutate state or audit rows.
- Command run and quick actions persist state and write structured audit rows only on success.
- Smoke tests cover Python API and at least one frontend build/test path once the app exists.

## 10-Cycle Roadmap

| Cycle | Theme | Acceptance Criteria |
|---|---|---|
| 1 | Migration plan | This document lands; baseline Python tests and smoke test pass. |
| 2 | JSON API extraction | `/api/v1/*` endpoints cover dashboard, ask, command, actions, health, readiness, and metrics with contract tests. |
| 3 | Expo scaffold | `frontend/` Expo TypeScript app, API client, scripts, and first frontend tests land. |
| 4 | Read-only dashboard | React Native dashboard renders API snapshot with tests for loading, empty, and error states. |
| 5 | Quick actions | React Native quick actions call JSON API, refresh state, and surface failures. |
| 6 | Ask and command workflows | Ask ERP and command preview/run screens work and have tests. |
| 7 | UX hardening | Accessibility labels, disabled states, validation, timeouts, and responsive tablet layout improve operator usability. |
| 8 | Operability | CORS/dev config, request IDs, API version metadata, frontend health checks, and smoke coverage land. |
| 9 | Migration completion | React Native becomes the documented primary UI; raw HTML is removed or documented as temporary legacy fallback. |
| 10 | Release candidate | Full backend/frontend verification passes; QA signs off; PM publishes next roadmap. |

## Current Tradeoffs

React Native/Expo adds mobile reach, typed frontend structure, and a cleaner client/server boundary. It also adds Node tooling, build complexity, cross-platform QA, API versioning requirements, and environment configuration. The existing HTML remains useful as a migration fallback but should not be the product surface once the React Native app covers the workflows.
