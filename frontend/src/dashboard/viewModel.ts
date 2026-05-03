import type { DashboardSnapshot } from '../api/client.ts';

export type DashboardSection = {
  title: string;
  rows: Array<Record<string, string | number>>;
};

export type QuickAction = {
  key: string;
  label: string;
  payload: Record<string, string | number>;
  tone: 'primary' | 'danger';
};

export function dashboardSections(snapshot: DashboardSnapshot): DashboardSection[] {
  return [
    { title: 'Fulfillment Risk', rows: snapshot.fulfillment_risks },
    { title: 'AR Aging', rows: snapshot.ar_aging },
    { title: 'Inventory', rows: snapshot.inventory },
    { title: 'Purchase Orders', rows: snapshot.purchase_orders },
    { title: 'Invoices', rows: snapshot.invoices },
  ].filter((section) => section.rows.length > 0);
}

export function rowSummary(row: Record<string, string | number>): string {
  const values = Object.values(row).filter((value) => value !== '' && value !== null && value !== undefined);
  return values.slice(0, 4).join(' | ');
}

export function quickActions(snapshot: DashboardSnapshot): QuickAction[] {
  const actions: QuickAction[] = [];
  for (const row of snapshot.inventory) {
    if (String(row.status).toLowerCase() === 'low' && row.sku) {
      actions.push({
        key: `create-po-${row.sku}`,
        label: `Create PO for ${row.sku}`,
        payload: { action: 'create_po', sku: String(row.sku) },
        tone: 'primary',
      });
    }
  }
  for (const row of snapshot.purchase_orders) {
    const status = String(row.status).toLowerCase();
    if ((status === 'delayed' || status === 'open') && row.id) {
      actions.push({
        key: `receive-${row.id}`,
        label: `Receive ${row.id}`,
        payload: { action: 'receive_po', po_id: String(row.id) },
        tone: 'primary',
      });
    }
  }
  for (const row of snapshot.invoices) {
    if (String(row.status).toLowerCase() === 'overdue' && row.id) {
      actions.push({
        key: `pay-${row.id}`,
        label: `Pay ${row.id}`,
        payload: { action: 'pay_invoice', invoice_id: String(row.id), amount: String(row.amount || '') },
        tone: 'primary',
      });
    }
  }
  actions.push({
    key: 'reset',
    label: 'Reset Demo Data',
    payload: { action: 'reset' },
    tone: 'danger',
  });
  return actions;
}

export function emptyDashboard(): DashboardSnapshot {
  return {
    kpis: [],
    risk_flags: [],
    roles: [],
    inventory: [],
    sales_orders: [],
    purchase_orders: [],
    invoices: [],
    fulfillment_risks: [],
    ar_aging: [],
    audit_log: [],
  };
}
