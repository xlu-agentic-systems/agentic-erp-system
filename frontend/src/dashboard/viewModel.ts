import type { DashboardSnapshot } from '../api/client.ts';

export type DashboardSection = {
  title: string;
  rows: Array<Record<string, string | number>>;
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
