# Production Readiness Notes

## Release Candidate Scope

This release hardens the ERP demo around durable local persistence and safer workflow execution. SQLite is now the default storage backend, JSON remains available for compatibility, and workflow writes are covered by tests for persistence, readiness, concurrency, HTTP error handling, auditability, and backup.

## Completed Adaptive Cycles

| Cycle | PR | Outcome |
|---|---:|---|
| 1 | #10 | Added SQLite state/audit persistence as the default backend with JSON compatibility. |
| 2 | #11 | Added storage diagnostics and `/readyz` write probes. |
| 3 | #12 | Made SQLite workflow state and audit writes transactional. |
| 4 | #13 | Added concurrency regression tests for duplicate receipt and invoice payment races. |
| 5 | #14 | Returned 400/503 statuses for invalid workflow POSTs and unavailable engines. |
| 6 | #15 | Added structured audit fields and SQLite audit table migration. |
| 7 | #16 | Added SQLite backup API/CLI and moved smoke coverage to SQLite mode. |
| 8 | #17 | Release-candidate documentation, QA signoff, and PM next roadmap. |

## Verification Commands

Run these before release:

```bash
python3 -m pytest
python3 scripts/smoke_test.py
python3 scripts/backup_sqlite.py /tmp/erp-release-backup.sqlite3 --db data/erp.sqlite3
```

## Storage Contract

- Default backend: SQLite at `ERP_DB_PATH` or `data/erp.sqlite3`.
- Compatibility backend: JSON via `ERP_STORAGE_BACKEND=json` or `ERP_STATE_PATH`.
- Readiness: `/readyz` checks module availability, storage loadability, audit loadability, and a write probe.
- Atomicity: default SQLite workflow mutations and audit rows commit in one transaction.
- Backup: `erp_state.backup_sqlite()` and `scripts/backup_sqlite.py` use SQLite's backup API.

## QA Signoff Checklist

- Full unit suite passes.
- Smoke test runs in SQLite mode and verifies backup state/audit integrity.
- SQLite read/write round trips preserve Decimals, dates, workflow state, and audit rows.
- Concurrent create-PO, receive-PO, and invoice-payment tests pass without duplicate IDs, double receipts, or overpayments.
- Invalid workflow HTTP posts return non-2xx status codes and do not write audit rows.
- Legacy JSON and legacy SQLite audit table compatibility tests pass.

## Remaining Risks

- The SQLite state table stores the ERP aggregate as JSON payload instead of normalized relational ERP tables.
- There is no authentication, authorization, tenant isolation, or user attribution yet.
- Accounting depth is still simplified and does not implement ledger-grade posting, periods, tax, or multi-currency rules.
- Concurrency coverage is in-process; multi-process load and long-running lock contention should be tested before production deployment.

## PM Next Roadmap

1. Normalize SQL tables for products, vendors, customers, inventory, purchase orders, sales orders, invoices, lines, and audit metadata.
2. Add user identity, roles, and permission checks for mutating workflows.
3. Add ledger-grade inventory, cash, and AR transaction tables with immutable posting records.
4. Add migration versioning with forward-only migration files and downgrade/recovery guidance.
5. Add deployment packaging, scheduled backups, restore testing, and DB lock/contention observability.
6. Add multi-process and HTTP load tests for workflow race conditions.
7. Add product-facing workflow controls for reset confirmation, audit filtering, and backup/download operations.
8. Add CI enforcement for tests, smoke test, and storage compatibility checks on every PR.
