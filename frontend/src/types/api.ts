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

export interface DiffChangeItem {
  operation: string;
  table?: string;
  kind?: string;
  column?: string;
  before?: unknown;
  after?: unknown;
  key?: Record<string, unknown>;
  changed_columns?: string[];
  [key: string]: unknown;
}

export interface DiffSummary {
  tables_added: number;
  tables_dropped: number;
  tables_altered: number;
  rows_inserted: number;
  rows_deleted: number;
  rows_updated: number;
}

export interface DiffResult {
  from_commit_id?: number;
  to_commit_id?: number;
  schema_changes?: DiffChangeItem[];
  row_changes?: DiffChangeItem[];
  summary?: DiffSummary;
  schema_diff?: SchemaDiff;
  schema?: SchemaDiff;
  row_diff?: Record<string, TableRowDiff>;
  rows?: Record<string, TableRowDiff>;
  [key: string]: unknown;
}

export interface SchemaColumn {
  name: string;
  type: string;
  nullable: boolean;
  default: string | null;
  identity: string | null;
  sequence?: string | null;
  is_pk?: boolean;
}

export interface SchemaConstraint {
  name: string;
  type: string;
  definition: string;
  columns: string[];
  referenced_table?: string;
  referenced_schema?: string;
  referenced_columns?: string[];
}

export interface ForeignKeyLink {
  name?: string;
  columns: string[];
  referenced_table?: string;
  referenced_columns?: string[];
}

export interface SchemaIndex {
  name: string;
  definition: string;
}

export interface TableSchemaInfo {
  columns: SchemaColumn[];
  constraints: SchemaConstraint[];
  foreign_keys?: ForeignKeyLink[];
  indexes: SchemaIndex[];
  row_count: number;
}

export interface DatabaseSchemaResponse {
  target: string;
  commit_id?: number | null;
  branch?: string | null;
  tables: Record<string, TableSchemaInfo>;
  views: Record<string, { definition: string; owner?: string }>;
  sequences: Record<string, { last_value?: number; start_value?: number; increment_by?: number }>;
  total_tables: number;
  total_views: number;
  total_sequences: number;
}

export interface WorkspaceStatus {
  is_dirty: boolean;
  current_head: number | null;
  active_branch: string | null;
  head_hash?: string;
  current_hash?: string;
  summary?: DiffSummary;
  schema_changes?: DiffChangeItem[];
  row_changes?: DiffChangeItem[];
}

export interface DemoScenario {
  key: string;
  title: string;
  description: string;
  suggested_commit_message: string;
  sql: string;
}

export interface DemoSimulateResult {
  scenario: string;
  title: string;
  description: string;
  executed_sql: string;
  suggested_commit_message: string;
  workspace_status: WorkspaceStatus;
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

export type ReportMode = 'activity' | 'data_schema' | 'merge_conflict';
export type DateRangePreset = 'weekly' | 'monthly' | 'custom';

export interface ReportFilters {
  date_range: string;
  start_date: string;
  end_date: string;
  branch: string | null;
  branch_label: string;
  table: string | null;
  timezone: string;
  workspace_id: string;
}

export interface CommitActivityPoint {
  date: string;
  count: number;
  authors_count: number;
}

export interface AuthorDistributionItem {
  author: string;
  commits: number;
}

export interface TableRowChangeItem {
  table: string;
  inserts: number;
  updates: number;
  deletes: number;
  total: number;
}

export interface DailyChangeItem {
  date: string;
  inserts: number;
  updates: number;
  deletes: number;
  schema_changes: number;
}

export interface OutcomeBreakdownItem {
  status: string;
  count: number;
  color?: string;
}

export interface DailyMergeItem {
  date: string;
  success: number;
  conflict: number;
  rejected: number;
}

export interface ReportChartSeries {
  commit_activity?: CommitActivityPoint[];
  author_distribution?: AuthorDistributionItem[];
  table_row_changes?: TableRowChangeItem[];
  daily_changes?: DailyChangeItem[];
  outcome_breakdown?: OutcomeBreakdownItem[];
  daily_merges?: DailyMergeItem[];
}

export interface ReportDetailRow {
  commit_id?: number;
  id?: string | number;
  timestamp: string;
  author?: string;
  actor?: string;
  message?: string;
  parent_commits?: number[];
  is_merge?: boolean;
  tables_impacted_count?: number;
  tables_impacted?: string[];
  rows_changed?: number;
  change_category?: 'DATA' | 'SCHEMA';
  table?: string;
  operation?: string;
  details?: string;
  source?: string;
  target?: string;
  outcome?: string;
  merge_commit_id?: number | null;
  conflict_summary?: string;
  is_historical_reconstruction?: boolean;
  [key: string]: unknown;
}

export interface ReportResponse {
  mode: ReportMode;
  filters: ReportFilters;
  summary: Record<string, number | string | null>;
  chart_series: ReportChartSeries;
  details: ReportDetailRow[];
  coverage_notes: string[];
}

export interface ReportMetadata {
  modes: ReportMode[];
  date_ranges: DateRangePreset[];
  merge_outcome_tracking_started_at: string;
}

export interface AssistantEvidenceItem {
  commit_id: number;
  parent_id: number | null;
  timestamp: string;
  author: string;
  message: string;
  impacted_tables: string[];
  row_changes_summary: {
    inserts: number;
    updates: number;
    deletes: number;
    total: number;
  };
  schema_changes: Array<{
    operation: string;
    table: string;
    column: string | null;
    details: string;
  }>;
  diff_link: string;
  relevance_score: number;
}

export interface AssistantAppliedFilters {
  branch: string | null;
  table: string | null;
  date_range: string;
  start_date: string | null;
  end_date: string | null;
  metric: string;
}

export interface AssistantAskResponse {
  question: string;
  question_type: 'exact_statistics' | 'evidence_discovery' | 'explanation';
  answer: string;
  applied_filters: AssistantAppliedFilters;
  evidence: AssistantEvidenceItem[];
  clarification_needed: string | null;
  coverage_note: string | null;
  status: string;
}

export interface AssistantSuggestionItem {
  category: string;
  question: string;
  description: string;
}

export interface AssistantSuggestionsResponse {
  suggestions: AssistantSuggestionItem[];
}

