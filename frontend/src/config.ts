export const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000';

export function apiBaseUrl(value?: string): string {
  const configured = value || process.env.EXPO_PUBLIC_ERP_API_URL || DEFAULT_API_BASE_URL;
  return configured.replace(/\/+$/, '');
}
