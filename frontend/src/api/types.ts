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
