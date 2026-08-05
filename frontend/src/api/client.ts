import {useAuthStore} from '@/store/auth';
import type {
  AgentInfo,
  AgentTemplate,
  AgentTask,
  AuditLogEntry,
  BusStats,
  CatalogStats,
  CatalogTable,
  ColumnPolicy,
  ConnectorInfo,
  CurrentUser,
  DataSource,
  DocDetail,
  FeedbackStats,
  FilterRule,
  IngestResult,
  KnowledgeDoc,
  LifecycleData,
  LineageGraph,
  LoginResponse,
  MaskingPolicy,
  MetricDefinition,
  MetricQueryResult,
  MetricsSnapshot,
  RetrieveHit,
  TaskFeedback,
  ToolInfo,
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

  // 知识沉淀层: RAG 文档
  listKnowledgeDocs: () => request<KnowledgeDoc[]>('/knowledge/documents'),
  uploadKnowledgeDoc: (file: File, title?: string) => {
    const form = new FormData();
    form.append('file', file);
    if (title) form.append('title', title);
    return request<KnowledgeDoc>('/knowledge/documents', {
      method: 'POST',
      body: form,
      headers: {}, // Content-Type 交由 fetch 自动生成 multipart boundary
    });
  },
  knowledgeDocDetail: (id: number) => request<DocDetail>(`/knowledge/documents/${id}`),
  deleteKnowledgeDoc: (id: number) => request<void>(`/knowledge/documents/${id}`, {method: 'DELETE'}),
  retrieve: (query: string, top_k = 5) =>
    request<RetrieveHit[]>('/knowledge/retrieve', {
      method: 'POST',
      body: JSON.stringify({query, top_k}),
    }),

  // 多 Agent 协同层
  listAgents: () => request<AgentInfo[]>('/agents'),
  createAgent: (payload: {name: string; description?: string; capabilities?: string[]; tools?: string[]}) =>
    request<AgentInfo>('/agents', {method: 'POST', body: JSON.stringify(payload)}),
  deleteAgent: (id: number) => request<void>(`/agents/${id}`, {method: 'DELETE'}),
  listTools: () => request<ToolInfo[]>('/agents/tools'),
  listTemplates: () => request<AgentTemplate[]>('/agents/templates'),
  createFromTemplate: (templateKey: string, name?: string) =>
    request<AgentInfo>('/agents/from-template', {
      method: 'POST',
      body: JSON.stringify({template_key: templateKey, name: name || undefined}),
    }),
  busStats: () => request<BusStats>('/agents/bus/stats'),
  createTask: (agentId: number, objective: string, title?: string, collaborators?: number[]) =>
    request<AgentTask>(`/agents/${agentId}/tasks`, {
      method: 'POST',
      body: JSON.stringify({objective, title, collaborators: collaborators ?? []}),
    }),
  listTasks: () => request<AgentTask[]>('/agents/tasks'),
  runTask: (taskId: number) => request<AgentTask>(`/agents/tasks/${taskId}/run`, {method: 'POST'}),

  // M3: 安全治理
  auditLogs: (params: {limit?: number; action?: string} = {}) => {
    const qs = new URLSearchParams();
    if (params.limit) qs.set('limit', String(params.limit));
    if (params.action) qs.set('action', params.action);
    return request<AuditLogEntry[]>(`/security/audit-logs?${qs.toString()}`);
  },
  lineage: () => request<LineageGraph>('/security/lineage'),
  maskingPolicies: () => request<MaskingPolicy[]>('/security/masking-policies'),

  // M5: 列级权限 / 生命周期
  columnPolicies: () => request<ColumnPolicy[]>('/security/column-policies'),
  createColumnPolicy: (role: string, columnName: string, tableId?: number) =>
    request<ColumnPolicy>('/security/column-policies', {
      method: 'POST',
      body: JSON.stringify({role, column_name: columnName, table_id: tableId}),
    }),
  deleteColumnPolicy: (id: number) => request<void>(`/security/column-policies/${id}`, {method: 'DELETE'}),
  lifecycle: () => request<LifecycleData>('/security/lifecycle'),

  // M3: 反馈闭环
  submitFeedback: (taskId: number, rating: number, comment?: string) =>
    request<TaskFeedback>(`/feedback/tasks/${taskId}/feedback`, {
      method: 'POST',
      body: JSON.stringify({rating, comment: comment || null}),
    }),
  feedbackStats: () => request<FeedbackStats>('/feedback/stats'),

  // 观测
  metrics: () => request<MetricsSnapshot>('/feedback/metrics'),
};
