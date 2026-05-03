import assert from 'node:assert/strict';
import test from 'node:test';

import { ERPApiClient } from './client.ts';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

test('dashboard reads data from the versioned API', async () => {
  const calls: Array<{ url: string; init: RequestInit }> = [];
  const client = new ERPApiClient({
    baseUrl: 'http://erp.local/',
    fetcher: async (url, init) => {
      calls.push({ url: String(url), init: init || {} });
      return jsonResponse({
        ok: true,
        data: {
          kpis: [{ label: 'Projected cash', value: '$13,056', trend: 'Next 30 days' }],
          risk_flags: [],
          roles: [],
          inventory: [],
          sales_orders: [],
          purchase_orders: [],
          invoices: [],
          fulfillment_risks: [],
          ar_aging: [],
          audit_log: [],
        },
        error: null,
      });
    },
  });

  const dashboard = await client.dashboard();

  assert.equal(calls[0].url, 'http://erp.local/api/v1/dashboard');
  assert.equal(calls[0].init.method, 'GET');
  assert.equal(dashboard.kpis[0].label, 'Projected cash');
});

test('command preview posts JSON and returns non-mutating result', async () => {
  let parsedBody: unknown;
  const client = new ERPApiClient({
    baseUrl: 'http://erp.local',
    fetcher: async (_url, init) => {
      parsedBody = JSON.parse(String(init?.body));
      return jsonResponse({
        ok: true,
        data: { command: 'receive PO-1001', message: 'Preview: receive PO-1001', changed: false },
        error: null,
      });
    },
  });

  const result = await client.previewCommand('receive PO-1001');

  assert.deepEqual(parsedBody, { command: 'receive PO-1001' });
  assert.equal(result.changed, false);
});

test('ask posts a question to the ERP copilot API', async () => {
  let parsedBody: unknown;
  const client = new ERPApiClient({
    baseUrl: 'http://erp.local',
    fetcher: async (_url, init) => {
      parsedBody = JSON.parse(String(init?.body));
      return jsonResponse({
        ok: true,
        data: { question: 'What is at risk?', answer: 'PUMP-A needs review.' },
        error: null,
      });
    },
  });

  const result = await client.ask('What is at risk?');

  assert.deepEqual(parsedBody, { question: 'What is at risk?' });
  assert.equal(result.answer, 'PUMP-A needs review.');
});

test('runCommand posts a mutating command', async () => {
  let parsedBody: unknown;
  const client = new ERPApiClient({
    baseUrl: 'http://erp.local',
    fetcher: async (_url, init) => {
      parsedBody = JSON.parse(String(init?.body));
      return jsonResponse({
        ok: true,
        data: { command: 'receive PO-1001', message: 'Received PO-1001; inventory is updated.' },
        error: null,
      });
    },
  });

  const result = await client.runCommand('receive PO-1001');

  assert.deepEqual(parsedBody, { command: 'receive PO-1001' });
  assert.match(result.message, /Received PO-1001/);
});

test('API errors reject with the server message', async () => {
  const client = new ERPApiClient({
    baseUrl: 'http://erp.local',
    fetcher: async () =>
      jsonResponse(
        { ok: false, data: null, error: { code: 'validation_error', message: 'Unknown ERP action.' } },
        400,
      ),
  });

  await assert.rejects(client.action({ action: 'missing' }), /Unknown ERP action/);
});
