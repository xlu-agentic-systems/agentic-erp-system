# React Native Release Notes

## Release Scope

This release makes the Expo/React Native app the primary ERP product UI while preserving the Python backend, SQLite persistence, versioned JSON API, and legacy HTML fallback.

## Completed Cycles

| Cycle | PR | Outcome |
|---|---:|---|
| 1 | #18 | Documented React Native migration scope, API plan, QA checklist, and roadmap. |
| 2 | #19 | Added `/api/v1` JSON endpoints and backend API contract tests. |
| 3 | #20 | Added Expo/React Native TypeScript scaffold and tested API client. |
| 4 | #21 | Added read-only mobile dashboard screen and view-model tests. |
| 5 | #22 | Added mobile quick actions and backend default reorder action support. |
| 6 | #23 | Added mobile Ask ERP and Command ERP preview/run workflows. |
| 7 | #24 | Added request timeouts, reset confirmation, and accessibility/disabled states. |
| 8 | #25 | Added API metadata, request IDs, CORS, OPTIONS, and frontend metadata client. |
| 9 | #26 | Documented React Native as primary UI and marked HTML as legacy fallback. |
| 10 | #27 | Release notes, QA signoff, and PM next roadmap. |

## Verification Commands

```bash
python3 -m pytest
python3 scripts/smoke_test.py
cd frontend
npm test
npm run typecheck
```

Run `npm audit --omit=dev` during release review. It currently reports known moderate Expo transitive advisories tracked in the residual risks below.

## Current UI Contract

- Primary UI: `frontend/` Expo/React Native app.
- Backend API: Python server under `/api/v1`.
- Legacy fallback: Python server-rendered HTML at `/`, marked as fallback in-page.
- Persistence: SQLite remains default and workflow mutations still use transactional state/audit writes.

## QA Focus

- API envelope contract is stable for dashboard, ask, command preview/run, actions, health, readiness, metrics, and metadata.
- Command preview does not mutate state or audit.
- Command run and quick actions persist state and write structured audit rows on success.
- React Native API client covers success, validation errors, metadata, and timeout handling.
- React Native dashboard covers loading, retryable error, empty activity/risk states, workflow notices, quick actions, Ask ERP, and Command ERP.
- Python storage/readiness/concurrency regression suite remains green.

## Residual Risks

- No auth, roles, tenant isolation, CSRF protection, or user attribution.
- React Native UI has unit/API-client tests but no simulator/device E2E coverage yet.
- Expo transitive dependencies currently report moderate `npm audit --omit=dev` advisories that require upstream compatible fixes or a breaking package change.
- SQLite still stores the ERP aggregate as JSON rather than normalized ERP tables.
- Legacy HTML remains in the backend as a fallback and should be removed once native/web Expo deployment is fully validated.

## Dependency Audit Waiver

This release candidate carries a documented dependency-audit waiver for Expo transitive moderate advisories:

- `postcss`: XSS advisory through Expo/Metro dependency paths. `npm audit` reports no compatible fix in the current Expo tree.
- `uuid`: buffer bounds advisory through Expo config tooling. `npm audit fix` cannot resolve it without a breaking Expo package change.

This waiver applies only to the React Native migration release candidate. Production GA should not proceed until the Expo dependency tree has compatible patched packages, a safe package override is validated, or the team explicitly accepts the residual risk with deployment-specific compensating controls.

## PM Next Roadmap

1. Add CI gates for Python tests, frontend tests, typecheck, smoke test, and dependency audit reporting.
2. Add simulator or Expo web E2E coverage for dashboard, quick actions, Ask ERP, and Command ERP.
3. Add auth, roles, tenant isolation, and user attribution through API and audit rows.
4. Normalize SQLite ERP tables and introduce explicit schema migrations.
5. Add deployment packaging for backend and frontend, with environment-specific API URL configuration.
6. Add audit filtering/export and admin-safe reset/backup controls in the React Native UI.
7. Add offline/read retry strategy and richer API error taxonomy.
8. Retire the raw HTML fallback after Expo web/mobile deployment is validated.
