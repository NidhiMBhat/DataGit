import { AuthSettings } from '../types/api';

export class ApiError extends Error {
  status?: number;
  data?: unknown;

  constructor(message: string, status?: number, data?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

export const defaultSettings: AuthSettings = {
  apiKey: localStorage.getItem('datagit_api_key') || '',
  authHeaderType: (localStorage.getItem('datagit_auth_header') as 'X-API-Key' | 'Bearer') || 'X-API-Key',
  apiBaseUrl: localStorage.getItem('datagit_api_base') || '/api',
  defaultAllowDirty: localStorage.getItem('datagit_default_allow_dirty') === 'true',
  author: localStorage.getItem('datagit_author') || 'DataGit Engineer',
};

export interface ApiRequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
}

export async function apiRequest<T = unknown>(
  endpoint: string,
  options: ApiRequestOptions = {},
  settings: AuthSettings = defaultSettings
): Promise<T> {
  const baseUrl = settings.apiBaseUrl.replace(/\/+$/, '');
  const url = `${baseUrl}${endpoint.startsWith('/') ? '' : '/'}${endpoint}`;

  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...((options.headers as Record<string, string>) || {}),
  };

  const { body, ...restOptions } = options;
  let finalBody: BodyInit | null | undefined = undefined;

  if (body !== undefined && body !== null) {
    if (typeof body === 'object' && !(body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
      finalBody = JSON.stringify(body);
    } else {
      finalBody = body as BodyInit;
    }
  }

  // Attach API key if configured
  if (settings.apiKey) {
    if (settings.authHeaderType === 'Bearer') {
      headers['Authorization'] = `Bearer ${settings.apiKey.trim()}`;
    } else {
      headers['X-API-Key'] = settings.apiKey.trim();
    }
  }

  try {
    const response = await fetch(url, { ...restOptions, headers, body: finalBody });

    let data: unknown = null;
    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      data = await response.json();
    } else {
      data = await response.text();
    }

    if (!response.ok) {
      let errorMsg = `HTTP ${response.status}: ${response.statusText}`;
      if (typeof data === 'object' && data !== null && 'detail' in data) {
        const detail = (data as { detail: unknown }).detail;
        errorMsg = typeof detail === 'string' ? detail : JSON.stringify(detail);
      }
      throw new ApiError(errorMsg, response.status, data);
    }

    return data as T;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError((error as Error).message || 'Network error');
  }
}
