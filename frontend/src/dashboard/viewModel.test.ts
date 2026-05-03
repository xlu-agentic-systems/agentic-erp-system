import assert from 'node:assert/strict';
import test from 'node:test';

import { dashboardSections, emptyDashboard, quickActions, rowSummary } from './viewModel.ts';

test('dashboardSections returns populated operational tables in display order', () => {
  const snapshot = emptyDashboard();
  snapshot.inventory = [{ sku: 'PUMP-A', stock: 8, status: 'Low' }];
  snapshot.purchase_orders = [{ id: 'PO-1001', supplier: 'Metro', status: 'Delayed' }];

  const sections = dashboardSections(snapshot);

  assert.deepEqual(
    sections.map((section) => section.title),
    ['Inventory', 'Purchase Orders'],
  );
});

test('rowSummary creates a compact native table row label', () => {
  assert.equal(rowSummary({ sku: 'PUMP-A', item: 'Pump Assembly', stock: 8, status: 'Low' }), 'PUMP-A | Pump Assembly | 8 | Low');
});

test('quickActions derives mobile workflow actions from dashboard rows', () => {
  const snapshot = emptyDashboard();
  snapshot.inventory = [{ sku: 'PUMP-A', status: 'Low', stock: 8 }];
  snapshot.purchase_orders = [{ id: 'PO-1001', status: 'Delayed' }];
  snapshot.invoices = [{ id: 'INV-9001', status: 'Overdue', amount: '1500.00' }];

  const actions = quickActions(snapshot);

  assert.deepEqual(
    actions.map((action) => action.payload.action),
    ['create_po', 'receive_po', 'pay_invoice', 'reset'],
  );
  assert.deepEqual(actions[0].payload, { action: 'create_po', sku: 'PUMP-A' });
  assert.deepEqual(actions[2].payload, { action: 'pay_invoice', invoice_id: 'INV-9001', amount: '1500.00' });
});
