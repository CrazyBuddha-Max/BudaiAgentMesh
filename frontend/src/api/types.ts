/** 后端 API 类型定义 (与 backend/app/access/schemas.py 对应) */

export interface DataSource {
  id: number;
  name: string;
  source_type: string;
  description: string | null;
  host: string | null;
  port: number | null;
  database: string | null;
  schema_name: string | null;
  username: string | null;
  file_path: string | null;
  status: 'pending' | 'active' | 'error';
  quality_score: number;
  last_ingested_at: string | null;
  created_at: string;
}

export interface CatalogColumn {
  id: number;
  column_name: string;
  data_type: string;
  is_nullable: boolean;
  is_primary_key: boolean;
  null_rate: number;
  distinct_ratio: number;
  sample_values: unknown[] | null;
  description: string | null;
}

export interface CatalogTable {
  id: number;
  source_id: number;
  schema_name: string;
  table_name: string;
  row_count: number;
  quality_score: number;
  description: string | null;
  columns: CatalogColumn[];
}

export interface ConnectorInfo {
  type: string;
  display_name: string;
  description: string;
  available: boolean;
  params: string[];
}

export interface IngestResult {
  source_id: number;
  run_id: number;
  status: 'running' | 'success' | 'failed';
  tables_found: number;
  message: string;
}

export interface CatalogStats {
  sources: number;
  tables: number;
  columns: number;
  ingestion_runs: number;
}

export interface MetricsSnapshot {
  window_seconds: number;
  requests: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  error_rate: number;
  status_distribution: Record<string, number>;
}

export interface FilterRule {
  column: string;
  op: 'eq' | 'neq' | 'gt' | 'ge' | 'lt' | 'le' | 'in' | 'contains';
  value: unknown;
}

export interface MetricDefinition {
  id: number;
  name: string;
  display_name: string;
  description: string;
  table_id: number;
  measure: string;
  aggregation: 'sum' | 'avg' | 'count' | 'min' | 'max' | 'count_distinct';
  dimensions: string[];
  default_filters: FilterRule[];
  unit: string | null;
  owner: string | null;
  status: 'active' | 'archived';
  created_at: string;
  updated_at: string;
  expression: string;
  table: {
    id: number;
    schema_name: string;
    table_name: string;
    row_count: number;
    quality_score: number;
  } | null;
  source: {id: number; name: string; source_type: string} | null;
}

export interface MetricQueryResult {
  metric: MetricDefinition;
  source: {id: number; name: string; source_type: string; schema: string; table: string};
  expression: string;
  group_by: string[];
  rows: Array<Record<string, unknown> & {value: number | string | null}>;
  duration_ms: number;
  executed_at: string;
}

export interface CurrentUser {
  username: string;
  role: 'admin' | 'analyst' | 'viewer';
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: CurrentUser;
}

// ---------- 知识层 ----------

export interface KnowledgeDoc {
  id: number;
  title: string;
  source_type: string;
  file_name: string;
  file_size: number;
  chunk_count: number;
  status: 'processing' | 'ready' | 'failed';
  error: string | null;
  created_at: string;
}

export interface KnowledgeChunk {
  id: number;
  chunk_index: number;
  content: string;
  token_count: number;
  meta: {source?: string; chunk?: number} | null;
}

export interface DocDetail extends KnowledgeDoc {
  chunks: KnowledgeChunk[];
}

export interface RetrieveHit {
  chunk_id: number;
  doc_id: number;
  content: string;
  score: number;
  metadata: {source?: string; chunk?: number} | null;
}

// ---------- 协同层 ----------

export interface AgentInfo {
  id: number;
  name: string;
  description: string | null;
  capabilities: string[];
  tools: string[];
  status: 'active' | 'paused' | 'offline';
  created_at: string;
}

export interface AgentTemplate {
  key: string;
  name: string;
  description: string;
  capabilities: string[];
}

export interface BusStats {
  type: string;
  published: number;
  queue_size: number;
}

export interface ToolInfo {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
}

export interface AgentEvent {
  id: number;
  agent_id: number;
  event_type: string;
  payload: Record<string, unknown> | null;
  created_at: string;
}

export interface AgentTask {
  id: number;
  agent_id: number;
  title: string | null;
  objective: string;
  collaborators: number[];
  status: 'pending' | 'running' | 'succeeded' | 'failed';
  result: string | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
  events: AgentEvent[];
}

// ---------- M3: 安全治理 ----------

export interface AuditLogEntry {
  id: number;
  actor: string;
  action: string;
  target_type: string;
  target_id: string | null;
  detail: Record<string, unknown> | null;
  created_at: string;
}

export interface LineageNode {
  id: string;
  type: string;
  kind: 'source' | 'consumer';
  label: string;
}

export interface LineageEdge {
  from: string;
  to: string;
  action: string;
}

export interface LineageGraph {
  nodes: LineageNode[];
  edges: LineageEdge[];
}

export interface MaskingPolicy {
  sensitive_type: string;
  label: string;
  patterns: string[];
  example: string;
  mask_roles: string[];
}

// ---------- M5: 列级权限 / 生命周期 ----------

export interface ColumnPolicy {
  id: number;
  role: string;
  table_id: number | null;
  column_name: string;
  created_by: string | null;
  created_at: string;
}

export interface LifecycleItem {
  source_id: number;
  source_name: string;
  source_type: string;
  retention_days: number | null;
  status: 'no-policy' | 'active' | 'expiring' | 'expired';
  status_label: string;
  last_ingested_at: string | null;
  expires_at: string | null;
}

export interface LifecycleData {
  summary: {total: number; by_status: Record<string, number>};
  items: LifecycleItem[];
}

// ---------- M3: 反馈闭环 ----------

export interface TaskFeedback {
  id: number;
  task_id: number;
  agent_id: number;
  rating: number;
  comment: string | null;
  created_by: string | null;
  created_at: string;
}

export interface FeedbackStats {
  total: number;
  avg_rating: number;
  by_rating: Record<string, number>;
}
