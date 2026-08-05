import {useAuthStore} from '@/store/auth';
import type {
  CatalogStats,
  CatalogTable,
  ConnectorInfo,
  CurrentUser,
  DataSource,
  FilterRule,
  IngestResult,
  LoginResponse,
  MetricDefinition,
  MetricQueryResult,
  MetricsSnapshot,
} from './types';

const BASE = '/api';

export class ApiError extends Error {
  code: string;
  status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = useAuthStore.getState().token;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const resp = await fetch(`${BASE}${path}`, {...options, headers});
  if (resp.status === 401) {
    useAuthStore.getState().logout();
  }
  if (!resp.ok) {
    let code = 'REQUEST_FAILED';
    let message = `请求失败 (${resp.status})`;
    try {
      const body = await resp.json();
      code = body.code ?? code;
      message = body.message ?? message;
    } catch {
      /* 忽略解析失败 */
    }
    throw new ApiError(resp.status, code, message);
  }
  if (resp.status === 204) {
    return undefined as T;
  }
  return resp.json() as Promise<T>;
}

export const api = {
  // 系统
  health: () => request<{status: string; version: string}>('/health'),

  // 认证
  login: (username: string, password: string) =>
    request<LoginResponse>('/security/login', {method: 'POST', body: JSON.stringify({username, password})}),
  me: () => request<CurrentUser>('/security/me'),

  // 数据源
  listSources: () => request<DataSource[]>('/access/sources'),
  createSource: (payload: Record<string, unknown>) =>
    request<DataSource>('/access/sources', {method: 'POST', body: JSON.stringify(payload)}),
  deleteSource: (id: number) => request<void>(`/access/sources/${id}`, {method: 'DELETE'}),
  testSource: (id: number) =>
    request<{source_id: number; status: string; message: string}>(`/access/sources/${id}/test`, {method: 'POST'}),
  ingestSource: (id: number) =>
    request<IngestResult>(`/access/sources/${id}/ingest`, {method: 'POST'}),

  // 连接器市场
  connectors: () => request<ConnectorInfo[]>('/access/connectors'),

  // 元数据目录
  catalogStats: () => request<CatalogStats>('/access/catalog/stats'),
  catalogTables: (params: {source_id?: number; keyword?: string} = {}) => {
    const qs = new URLSearchParams();
    if (params.source_id !== undefined) qs.set('source_id', String(params.source_id));
    if (params.keyword) qs.set('keyword', params.keyword);
    return request<CatalogTable[]>(`/access/catalog/tables?${qs.toString()}`);
  },
  tableDetail: (id: number) => request<CatalogTable>(`/access/catalog/tables/${id}`),

  // 知识沉淀层: 指标语义
  listMetrics: (params: {keyword?: string; status?: string} = {}) => {
    const qs = new URLSearchParams();
    if (params.keyword) qs.set('keyword', params.keyword);
    if (params.status) qs.set('status', params.status);
    return request<MetricDefinition[]>(`/knowledge/metrics?${qs.toString()}`);
  },
  createMetric: (payload: Record<string, unknown>) =>
    request<MetricDefinition>('/knowledge/metrics', {method: 'POST', body: JSON.stringify(payload)}),
  deleteMetric: (id: number) => request<void>(`/knowledge/metrics/${id}`, {method: 'DELETE'}),
  runMetricQuery: (id: number, payload: {group_by?: string[]; filters?: FilterRule[]; limit?: number}) =>
    request<MetricQueryResult>(`/knowledge/metrics/${id}/query`, {method: 'POST', body: JSON.stringify(payload)}),

  // 观测
  metrics: () => request<MetricsSnapshot>('/feedback/metrics'),
};
