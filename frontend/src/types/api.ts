export interface Commit {
  commit_id?: number;
  id?: number;
  message: string;
  author: string;
  parent_commit?: number | null;
  parent_commit_id?: number | string | null;
  parents?: number[];
  state_id?: string;
  snapshot_hash?: string;
  timestamp?: string;
  created_at?: string;
}

export interface Branch {
  name: string;
  head_commit?: number | null;
  head_commit_id?: number | null;
  created_at?: string;
  is_current: boolean;
}

export interface SchemaColumnChange {
  name: string;
  type?: string;
  old_type?: string;
  new_type?: string;
}

export interface SchemaConstraintChange {
  name: string;
  [key: string]: unknown;
}

export interface AlteredTable {
  table_name?: string;
  name?: string;
  added_columns?: SchemaColumnChange[];
  dropped_columns?: SchemaColumnChange[];
  altered_columns?: SchemaColumnChange[];
  added_constraints?: SchemaConstraintChange[];
  dropped_constraints?: SchemaConstraintChange[];
  [key: string]: unknown;
}

export interface SchemaDiff {
  added_tables?: Array<string | { name?: string; table_name?: string }>;
  dropped_tables?: Array<string | { name?: string; table_name?: string }>;
  altered_tables?: AlteredTable[];
  extended_objects?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface RowUpdate {
  key?: unknown;
  primary_key?: unknown;
  identity?: unknown;
  changes?: unknown;
  diff?: unknown;
  [key: string]: unknown;
}

export interface TableRowDiff {
  inserted?: unknown[];
  inserts?: unknown[];
  deleted?: unknown[];
  deletes?: unknown[];
  updated?: RowUpdate[];
  updates?: RowUpdate[];
}

export interface DiffResult {
  schema_diff?: SchemaDiff;
  schema?: SchemaDiff;
  row_diff?: Record<string, TableRowDiff>;
  rows?: Record<string, TableRowDiff>;
  [key: string]: unknown;
}

export interface MergeResponse {
  merge_commit_id: number;
}

export interface StrategyMeasurement {
  payload_bytes?: number;
  size_bytes?: number;
  total_relation_bytes?: number;
  write_seconds?: number;
  write_ms?: number;
  write_time_ms?: number;
  read_seconds?: number;
  read_ms?: number;
  read_time_ms?: number;
  reconstruct_seconds?: number;
  reconstruction_ms?: number;
  reconstruct_time_ms?: number;
  verified_reconstruction?: boolean;
  records?: number;
}

export interface RecommendationInfo {
  recommended_strategy?: string;
  rationale?: string;
  compression_ratios?: Record<string, number>;
}

export interface StorageBenchmarkResult {
  iterations: number;
  snapshot_count?: number;
  shared_blob_count?: number;
  recommendation?: string | RecommendationInfo;
  integrity_verified?: boolean;
  measurements?: Record<string, StrategyMeasurement>;
  strategies?: Record<string, StrategyMeasurement>;
  measurement_notes?: string[];
  synthetic_workload?: {
    table_count: number;
    rows_per_table: number;
    snapshot_count: number;
    change_ratio: number;
  };
  [key: string]: unknown;
}

export interface AuthSettings {
  apiKey: string;
  authHeaderType: 'X-API-Key' | 'Bearer';
  apiBaseUrl: string;
  defaultAllowDirty: boolean;
  author: string;
}
