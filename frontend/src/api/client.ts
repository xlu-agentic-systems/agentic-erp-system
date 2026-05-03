import { apiBaseUrl } from '../config.ts';

export type ApiError = {
  code: string;
  message: string;
};

export type ApiEnvelope<T> =
  | { ok: true; data: T; error: null }
  | { ok: false; data: null; error: ApiError };

export type DashboardSnapshot = {
  kpis: Array<{ label: string; value: string; trend: string }>;
  risk_flags: Array<{ level: string; title: string; detail: string }>;
  roles: Array<{ role: string; summary: string }>;
  inventory: Array<Record<string, string | number>>;
  sales_orders: Array<Record<string, string | number>>;
  purchase_orders: Array<Record<string, string | number>>;
  invoices: Array<Record<string, string | number>>;
  fulfillment_risks: Array<Record<string, string | number>>;
  ar_aging: Array<Record<string, string | number>>;
  audit_log: Array<Record<string, string>>;
};

export type ApiMetadata = {
  service: string;
  app_version: string;
  api_version: string;
};

export class ERPApiClient {
  private readonly baseUrl: string;
  private readonly fetcher: typeof fetch;
  private readonly timeoutMs: number;

  constructor(options: { baseUrl?: string; fetcher?: typeof fetch; timeoutMs?: number } = {}) {
    this.baseUrl = apiBaseUrl(options.baseUrl);
    this.fetcher = options.fetcher || fetch;
    this.timeoutMs = options.timeoutMs ?? 10000;
  }

  dashboard(): Promise<DashboardSnapshot> {
    return this.get<DashboardSnapshot>('/api/v1/dashboard');
  }

  metadata(): Promise<ApiMetadata> {
    return this.get<ApiMetadata>('/api/v1/meta');
  }

  ask(question: string): Promise<{ question: string; answer: string }> {
    return this.post('/api/v1/ask', { question });
  }

  previewCommand(command: string): Promise<{ command: string; message: string; changed: boolean }> {
    return this.post('/api/v1/command/preview', { command });
  }

  runCommand(command: string): Promise<{ command: string; message: string }> {
    return this.post('/api/v1/command/run', { command });
  }

  action(payload: Record<string, string | number | null>): Promise<{ message: string; dashboard: DashboardSnapshot }> {
    return this.post('/api/v1/actions', payload);
  }

  private async get<T>(path: string): Promise<T> {
    return this.request<T>(path, { method: 'GET' });
  }

  private async post<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  }

  private async request<T>(path: string, init: RequestInit): Promise<T> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const response = await this.fetcher(`${this.baseUrl}${path}`, { ...init, signal: controller.signal });
      const envelope = (await response.json()) as ApiEnvelope<T>;
      if (!response.ok || !envelope.ok) {
        const message = envelope.ok ? `HTTP ${response.status}` : envelope.error.message;
        throw new Error(message);
      }
      return envelope.data;
    } catch (exc) {
      if (exc instanceof Error && exc.name === 'AbortError') {
        throw new Error('ERP API request timed out.');
      }
      throw exc;
    } finally {
      clearTimeout(timeout);
    }
  }
}
