import assert from 'node:assert/strict';
import test from 'node:test';

import { dashboardSections, emptyDashboard, rowSummary } from './viewModel.ts';

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
