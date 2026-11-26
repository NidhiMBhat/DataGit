import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  RefreshCw,
  Info,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  FileSpreadsheet,
  FileText,
  Activity,
  Database,
  GitMerge,
  Sparkles,
  Search,
  ArrowRight,
  ExternalLink,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { apiRequest } from '../../services/api';
import {
  ReportResponse,
  ReportMode,
  DateRangePreset,
  ReportDetailRow,
  AssistantAskResponse,
  AssistantSuggestionsResponse,
  AssistantSuggestionItem,
  AssistantAppliedFilters,
} from '../../types/api';

export const ReportsTab: React.FC = () => {
  const { branches, settings, addToast, setActiveTab, setDiffPair } = useApp();

  const [mode, setMode] = useState<ReportMode>('activity');
  const [dateRange, setDateRange] = useState<DateRangePreset>('monthly');
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  const [selectedBranch, setSelectedBranch] = useState<string>('');
  const [selectedTable, setSelectedTable] = useState<string>('');
  const [availableTables, setAvailableTables] = useState<string[]>([]);

  const [report, setReport] = useState<ReportResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isExportingCsv, setIsExportingCsv] = useState<boolean>(false);
  const [isExportingPdf, setIsExportingPdf] = useState<boolean>(false);
  const [searchDetail, setSearchDetail] = useState<string>('');

  // Ask DataGit assistant state
  const [askQuery, setAskQuery] = useState<string>('');
  const [isAsking, setIsAsking] = useState<boolean>(false);
  const [askResult, setAskResult] = useState<AssistantAskResponse | null>(null);
  const [askError, setAskError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<AssistantSuggestionItem[]>([]);
  const [isAssistantExpanded, setIsAssistantExpanded] = useState<boolean>(true);

  const systemTimezone = useMemo(() => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    } catch {
      return 'UTC';
    }
  }, []);

  // Fetch available tables from database schema for the table filter dropdown
  const loadTables = useCallback(async () => {
    try {
      const data = await apiRequest<{ tables?: Record<string, unknown> }>('/schema', {}, settings);
      if (data && data.tables) {
        setAvailableTables(Object.keys(data.tables).sort());
      }
    } catch {
      // Non-critical if schema load fails
    }
  }, [settings]);

  useEffect(() => {
    loadTables();
  }, [loadTables]);

  // Fetch dynamic report data
  const fetchReport = useCallback(async () => {
    setIsLoading(true);
    setErrorMsg(null);

    try {
      const params = new URLSearchParams({
        mode,
        date_range: dateRange,
        timezone: systemTimezone,
      });

      if (dateRange === 'custom') {
        if (startDate) params.set('start_date', startDate);
        if (endDate) params.set('end_date', endDate);
      }
      if (selectedBranch) {
        params.set('branch', selectedBranch);
      }
      if (selectedTable && mode === 'data_schema') {
        params.set('table', selectedTable);
      }

      const endpoint = `/reports?${params.toString()}`;
      const data = await apiRequest<ReportResponse>(endpoint, {}, settings);
      setReport(data);
    } catch (err: unknown) {
      const msg = (err as Error).message || 'Failed to load report analytics';
      setErrorMsg(msg);
      addToast(msg, 'error');
    } finally {
      setIsLoading(false);
    }
  }, [mode, dateRange, startDate, endDate, selectedBranch, selectedTable, systemTimezone, settings, addToast]);

  useEffect(() => {
    fetchReport();
  }, [fetchReport]);

  // Fetch suggestions for Ask DataGit on mount
  useEffect(() => {
    const fetchSuggestions = async () => {
      try {
        const res = await apiRequest<AssistantSuggestionsResponse>('/assistant/suggestions', {}, settings);
        if (res && res.suggestions) {
          setSuggestions(res.suggestions);
        }
      } catch {
        // Fallback default suggestions
        setSuggestions([
          {
            category: 'Exact statistics',
            question: 'How many order rows were updated on main last month?',
            description: 'Reconciles authoritative mutation counts against the reporting engine.',
          },
          {
            category: 'Evidence discovery',
            question: 'Which commits changed the orders schema last month?',
            description: 'Locates relevant commits, DDL operations, and schema alterations.',
          },
          {
            category: 'Explanation',
            question: 'Which commits contributed most to the spike in order updates?',
            description: 'Identifies mutation surges and isolates the driving commits.',
          },
        ]);
      }
    };
    fetchSuggestions();
  }, [settings]);

  // Execute query against Ask DataGit
  const handleAsk = useCallback(
    async (questionText?: string) => {
      const q = (questionText !== undefined ? questionText : askQuery).trim();
      if (!q) return;
      if (questionText !== undefined) {
        setAskQuery(q);
      }
      setIsAsking(true);
      setAskError(null);

      try {
        const payload = {
          question: q,
          context_filters: {
            branch: selectedBranch || null,
            table: selectedTable || null,
            date_range: dateRange,
            start_date: startDate || null,
            end_date: endDate || null,
            timezone: systemTimezone,
          },
        };

        const res = await apiRequest<AssistantAskResponse>(
          '/assistant/ask',
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          },
          settings
        );
        setAskResult(res);
      } catch (err: unknown) {
        const msg = (err as Error).message || 'Failed to query Ask DataGit assistant';
        setAskError(msg);
        addToast(msg, 'error');
      } finally {
        setIsAsking(false);
      }
    },
    [askQuery, selectedBranch, selectedTable, dateRange, startDate, endDate, systemTimezone, settings, addToast]
  );

  // Apply assistant scope to Reports tab filters
  const handleApplyScope = (filters: AssistantAppliedFilters) => {
    if (filters.branch) {
      setSelectedBranch(filters.branch);
    } else {
      setSelectedBranch('');
    }
    if (filters.table) {
      setSelectedTable(filters.table);
      setMode('data_schema');
    }
    if (filters.date_range && ['weekly', 'monthly', 'custom'].includes(filters.date_range)) {
      setDateRange(filters.date_range as DateRangePreset);
    }
    if (filters.start_date) setStartDate(filters.start_date);
    if (filters.end_date) setEndDate(filters.end_date);
    if (filters.metric === 'merges') {
      setMode('merge_conflict');
    } else if (filters.metric === 'commits') {
      setMode('activity');
    }
    addToast('Applied assistant scope to report filters', 'info');
  };

  // Click commit to open diff in Diff Inspector tab
  const handleOpenDiff = (commitId: number, parentId: number | null) => {
    setDiffPair({ from: parentId ?? commitId, to: commitId });
    setActiveTab('diff');
  };

  // Helper to render formatted Markdown-like text safely
  const renderFormattedAnswer = (text: string) => {
    const lines = text.split('\n');
    return (
      <div className="ask-answer-body">
        {lines.map((line, idx) => {
          if (!line.trim()) {
            return <div key={idx} style={{ height: '8px' }} />;
          }
          const parts = line.split(/(\*\*.*?\*\*|`.*?`)/g);
          return (
            <p key={idx} style={{ margin: '4px 0' }}>
              {parts.map((part, pIdx) => {
                if (part.startsWith('**') && part.endsWith('**')) {
                  return <strong key={pIdx}>{part.slice(2, -2)}</strong>;
                }
                if (part.startsWith('`') && part.endsWith('`')) {
                  return (
                    <code
                      key={pIdx}
                      className="font-mono"
                      style={{
                        backgroundColor: 'var(--bg-card)',
                        padding: '2px 5px',
                        borderRadius: '4px',
                        fontSize: '0.8125rem',
                      }}
                    >
                      {part.slice(1, -1)}
                    </code>
                  );
                }
                return part;
              })}
            </p>
          );
        })}
      </div>
    );
  };

  // Export handlers
  const handleExportCsv = async () => {
    setIsExportingCsv(true);
    try {
      const params = new URLSearchParams({
        mode,
        date_range: dateRange,
        timezone: systemTimezone,
      });
      if (dateRange === 'custom') {
        if (startDate) params.set('start_date', startDate);
        if (endDate) params.set('end_date', endDate);
      }
      if (selectedBranch) params.set('branch', selectedBranch);
      if (selectedTable && mode === 'data_schema') params.set('table', selectedTable);

      const headers: Record<string, string> = {};
      if (settings.apiKey) {
        if (settings.authHeaderType === 'Bearer') {
          headers['Authorization'] = `Bearer ${settings.apiKey.trim()}`;
        } else {
          headers['X-API-Key'] = settings.apiKey.trim();
        }
      }

      const res = await fetch(`${settings.apiBaseUrl}/reports/export/csv?${params.toString()}`, { headers });
      if (!res.ok) throw new Error(`Export CSV failed: HTTP ${res.status}`);
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `datagit_report_${mode}_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      window.URL.revokeObjectURL(url);
      addToast('CSV report downloaded successfully', 'success');
    } catch (err: unknown) {
      addToast((err as Error).message || 'CSV export failed', 'error');
    } finally {
      setIsExportingCsv(false);
    }
  };

  const handleExportPdf = async () => {
    setIsExportingPdf(true);
    try {
      const params = new URLSearchParams({
        mode,
        date_range: dateRange,
        timezone: systemTimezone,
      });
      if (dateRange === 'custom') {
        if (startDate) params.set('start_date', startDate);
        if (endDate) params.set('end_date', endDate);
      }
      if (selectedBranch) params.set('branch', selectedBranch);
      if (selectedTable && mode === 'data_schema') params.set('table', selectedTable);

      const headers: Record<string, string> = {};
      if (settings.apiKey) {
        if (settings.authHeaderType === 'Bearer') {
          headers['Authorization'] = `Bearer ${settings.apiKey.trim()}`;
        } else {
          headers['X-API-Key'] = settings.apiKey.trim();
        }
      }

      const res = await fetch(`${settings.apiBaseUrl}/reports/export/pdf?${params.toString()}`, { headers });
      if (!res.ok) throw new Error(`Export PDF failed: HTTP ${res.status}`);
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `datagit_report_${mode}_${new Date().toISOString().slice(0, 10)}.pdf`;
      a.click();
      window.URL.revokeObjectURL(url);
      addToast('PDF report generated and downloaded successfully', 'success');
    } catch (err: unknown) {
      addToast((err as Error).message || 'PDF export failed', 'error');
    } finally {
      setIsExportingPdf(false);
    }
  };

  // Filtered detail rows (only match when report matches the active mode)
  const filteredDetails = useMemo(() => {
    if (!report || !report.details || report.mode !== mode) return [];
    if (!searchDetail.trim()) return report.details;
    const term = searchDetail.toLowerCase();
    return report.details.filter((row: ReportDetailRow) => {
      const line = JSON.stringify(row).toLowerCase();
      return line.includes(term);
    });
  }, [report, mode, searchDetail]);

  // Chart rendering helpers with safe iterative aggregation (no call-stack-exceeding spread)
  const activitySeries = report?.chart_series?.commit_activity || [];
  const maxActivityCount = useMemo(() => {
    if (!activitySeries.length) return 1;
    return activitySeries.reduce((max, s) => (typeof s.count === 'number' && s.count > max ? s.count : max), 1);
  }, [activitySeries]);

  const tableChangesSeries = report?.chart_series?.table_row_changes || [];
  const maxTableChanges = useMemo(() => {
    if (!tableChangesSeries.length) return 1;
    return tableChangesSeries.reduce((max, t) => (typeof t.total === 'number' && t.total > max ? t.total : max), 1);
  }, [tableChangesSeries]);

  const outcomeBreakdown = report?.chart_series?.outcome_breakdown || [];
  const totalMergeAttempts = useMemo(() => {
    return outcomeBreakdown.reduce((acc, curr) => acc + (typeof curr.count === 'number' ? curr.count : 0), 0);
  }, [outcomeBreakdown]);

  return (
    <section className="tab-content reports-tab-container">
      {/* Header */}
      <div className="view-header">
        <div>
          <h2>Dynamic Statistics &amp; Analytics Reports</h2>
          <p className="text-secondary">
            Cross-branch activity audits, table-level mutation velocity, and 3-way merge conflict telemetry.
          </p>
        </div>

        <div className="view-controls">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={fetchReport}
            disabled={isLoading}
            title="Refresh Report Data"
          >
            <RefreshCw size={14} className={isLoading ? 'spin' : ''} />
            <span>Refresh</span>
          </button>

          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={handleExportCsv}
            disabled={isLoading || isExportingCsv}
          >
            <FileSpreadsheet size={14} />
            <span>{isExportingCsv ? 'Exporting...' : 'Export CSV'}</span>
          </button>

          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={handleExportPdf}
            disabled={isLoading || isExportingPdf}
          >
            <FileText size={14} />
            <span>{isExportingPdf ? 'Generating PDF...' : 'Export PDF'}</span>
          </button>
        </div>
      </div>

      {/* Ask DataGit RAG Assistant Panel */}
      <div className="card ask-datagit-card">
        <div className="ask-datagit-header">
          <div className="ask-datagit-title-group">
            <h3 className="ask-datagit-title">
              <Sparkles size={18} color="#6366f1" />
              <span>Ask DataGit</span>
            </h3>
            <span className="ask-datagit-badge">Read-Only RAG Assistant</span>
            <p className="ask-datagit-subtitle">
              Natural language repository intelligence: authoritative statistics, schema discovery, and grounded change explanations.
            </p>
          </div>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => setIsAssistantExpanded(!isAssistantExpanded)}
            title={isAssistantExpanded ? 'Collapse panel' : 'Expand panel'}
          >
            {isAssistantExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            <span>{isAssistantExpanded ? 'Collapse' : 'Expand'}</span>
          </button>
        </div>

        {isAssistantExpanded && (
          <div>
            {/* Search Input Form */}
            <form
              className="ask-datagit-form"
              onSubmit={(e) => {
                e.preventDefault();
                handleAsk();
              }}
            >
              <div className="ask-input-wrapper">
                <div className="ask-input-box">
                  <Search size={16} className="ask-input-icon" />
                  <input
                    type="text"
                    value={askQuery}
                    onChange={(e) => setAskQuery(e.target.value)}
                    placeholder="Ask a question (e.g., How many order rows were updated on main last month?)"
                    disabled={isAsking}
                  />
                </div>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={isAsking || !askQuery.trim()}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                >
                  <Sparkles size={15} className={isAsking ? 'spin' : ''} />
                  <span>{isAsking ? 'Analyzing...' : 'Ask DataGit'}</span>
                </button>
              </div>
            </form>

            {/* Suggested Questions */}
            <div className="ask-suggestions-container">
              <span className="ask-suggestions-label">Suggested Questions:</span>
              <div className="ask-suggestions-grid">
                {suggestions.map((item, idx) => (
                  <button
                    key={idx}
                    type="button"
                    className="ask-suggestion-btn"
                    onClick={() => handleAsk(item.question)}
                    disabled={isAsking}
                    title={item.description}
                  >
                    <span className="ask-suggestion-cat">{item.category}:</span>
                    <span>&ldquo;{item.question}&rdquo;</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Active inherited context preview */}
            <div className="text-secondary" style={{ fontSize: '0.75rem', marginBottom: '8px' }}>
              <span style={{ color: 'var(--text-muted)' }}>Inherited Report Defaults: </span>
              <span>Branch: <strong>{selectedBranch || 'All (reachable)'}</strong></span>
              <span className="mx-2">•</span>
              <span>Table: <strong>{selectedTable || 'All'}</strong></span>
              <span className="mx-2">•</span>
              <span>Time Window: <strong>{dateRange}</strong></span>
              <span className="mx-2">•</span>
              <span>Timezone: <strong>{systemTimezone}</strong></span>
            </div>

            {/* Error Message */}
            {askError && (
              <div className="alert alert-danger mt-2" style={{ fontSize: '0.8125rem' }}>
                <AlertTriangle size={15} className="mr-2 inline" />
                {askError}
              </div>
            )}

            {/* Assistant Results */}
            {askResult && (
              <div className="ask-result-panel">
                {/* Ambiguity clarification banner */}
                {askResult.clarification_needed && (
                  <div className="ask-clarification-box">
                    <AlertTriangle size={16} color="#f59e0b" />
                    <span><strong>Ambiguity Detected:</strong> {askResult.clarification_needed}</span>
                  </div>
                )}

                {/* Scope Bar */}
                <div className="ask-scope-row">
                  <div className="ask-scope-chips">
                    <span className="ask-scope-chip" style={{ borderColor: '#6366f1', color: '#6366f1' }}>
                      Type: <strong>{askResult.question_type.replace('_', ' ').toUpperCase()}</strong>
                    </span>
                    <span className="ask-scope-chip">
                      Branch: <strong>{askResult.applied_filters.branch || 'All Reachable'}</strong>
                    </span>
                    <span className="ask-scope-chip">
                      Table: <strong>{askResult.applied_filters.table || 'All'}</strong>
                    </span>
                    <span className="ask-scope-chip">
                      Window: <strong>{askResult.applied_filters.date_range}</strong>
                    </span>
                    {askResult.applied_filters.metric !== 'all' && (
                      <span className="ask-scope-chip">
                        Metric: <strong>{askResult.applied_filters.metric}</strong>
                      </span>
                    )}
                  </div>

                  <button
                    type="button"
                    className="ask-apply-scope-btn"
                    onClick={() => handleApplyScope(askResult.applied_filters)}
                    title="Update Reports dashboard filters to match this question scope"
                  >
                    <span>Apply Scope to Reports</span>
                    <ArrowRight size={13} />
                  </button>
                </div>

                {/* Formatted Answer */}
                {renderFormattedAnswer(askResult.answer)}

                {/* Evidence Citations */}
                {askResult.evidence && askResult.evidence.length > 0 && (
                  <div className="ask-evidence-section">
                    <div className="ask-evidence-header">
                      <CheckCircle2 size={15} color="#10b981" />
                      <span>Verified Evidence ({askResult.evidence.length} commit{askResult.evidence.length > 1 ? 's' : ''}):</span>
                    </div>

                    <div className="ask-evidence-cards">
                      {askResult.evidence.map((ev) => (
                        <div key={ev.commit_id} className="ask-evidence-card">
                          <div className="ask-evidence-left">
                            <button
                              type="button"
                              className="ask-commit-pill"
                              onClick={() => handleOpenDiff(ev.commit_id, ev.parent_id)}
                              title="Click to view diff in Diff Inspector"
                            >
                              <span>#{ev.commit_id}</span>
                              <ExternalLink size={11} />
                            </button>

                            <span className="ask-evidence-msg">&ldquo;{ev.message}&rdquo;</span>

                            <span className="ask-evidence-meta">
                              by <strong>{ev.author}</strong> on {ev.timestamp.slice(0, 10)}
                            </span>
                          </div>

                          <div className="ask-evidence-stats">
                            {ev.row_changes_summary.inserts > 0 && (
                              <span className="ask-stat-badge ins">+{ev.row_changes_summary.inserts}</span>
                            )}
                            {ev.row_changes_summary.updates > 0 && (
                              <span className="ask-stat-badge upd">~{ev.row_changes_summary.updates}</span>
                            )}
                            {ev.row_changes_summary.deletes > 0 && (
                              <span className="ask-stat-badge del">-{ev.row_changes_summary.deletes}</span>
                            )}
                            {ev.schema_changes.length > 0 && (
                              <span
                                className="ask-stat-badge ddl"
                                title={ev.schema_changes.map((s) => `${s.operation} ${s.table}`).join(', ')}
                              >
                                DDL ({ev.schema_changes.length})
                              </span>
                            )}

                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              style={{ padding: '3px 8px', fontSize: '0.6875rem' }}
                              onClick={() => handleOpenDiff(ev.commit_id, ev.parent_id)}
                            >
                              Inspect Diff
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Historical Coverage Note */}
                {askResult.coverage_note && (
                  <div className="ask-coverage-box">
                    <Info size={14} color="#3b82f6" />
                    <span>{askResult.coverage_note}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Filter Controls Card */}
      <div className="card report-filter-card mb-4">
        <div className="report-filter-row">
          {/* Mode Selector */}
          <div className="filter-group">
            <label className="filter-label">Report Mode:</label>
            <div className="segmented-control">
              <button
                type="button"
                className={`segment-btn ${mode === 'activity' ? 'active' : ''}`}
                onClick={() => setMode('activity')}
              >
                <Activity size={14} />
                <span>Activity</span>
              </button>
              <button
                type="button"
                className={`segment-btn ${mode === 'data_schema' ? 'active' : ''}`}
                onClick={() => setMode('data_schema')}
              >
                <Database size={14} />
                <span>Data &amp; Schema</span>
              </button>
              <button
                type="button"
                className={`segment-btn ${mode === 'merge_conflict' ? 'active' : ''}`}
                onClick={() => setMode('merge_conflict')}
              >
                <GitMerge size={14} />
                <span>Merge &amp; Conflicts</span>
              </button>
            </div>
          </div>

          {/* Date Range Presets */}
          <div className="filter-group">
            <label className="filter-label">Time Window:</label>
            <div className="segmented-control">
              <button
                type="button"
                className={`segment-btn ${dateRange === 'weekly' ? 'active' : ''}`}
                onClick={() => setDateRange('weekly')}
              >
                Last 7 Days
              </button>
              <button
                type="button"
                className={`segment-btn ${dateRange === 'monthly' ? 'active' : ''}`}
                onClick={() => setDateRange('monthly')}
              >
                Last 30 Days
              </button>
              <button
                type="button"
                className={`segment-btn ${dateRange === 'custom' ? 'active' : ''}`}
                onClick={() => setDateRange('custom')}
              >
                Custom
              </button>
            </div>
          </div>

          {/* Branch Filter */}
          <div className="filter-group">
            <label className="filter-label">Branch Scope (Ancestry):</label>
            <select
              className="form-select form-select-sm"
              value={selectedBranch}
              onChange={(e) => setSelectedBranch(e.target.value)}
            >
              <option value="">(All reachable commits)</option>
              {branches.map((b) => (
                <option key={b.name} value={b.name}>
                  Reachable from: {b.name} {b.is_current ? '(active)' : ''}
                </option>
              ))}
            </select>
          </div>

          {/* Table Filter (active for data_schema mode) */}
          {mode === 'data_schema' && (
            <div className="filter-group">
              <label className="filter-label">Table Filter:</label>
              <select
                className="form-select form-select-sm"
                value={selectedTable}
                onChange={(e) => setSelectedTable(e.target.value)}
              >
                <option value="">(All tables)</option>
                {availableTables.map((tbl) => (
                  <option key={tbl} value={tbl}>
                    {tbl}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* Custom Date Inputs if 'custom' is active */}
        {dateRange === 'custom' && (
          <div className="report-custom-date-row mt-3">
            <div className="form-group-inline">
              <label>Start Date:</label>
              <input
                type="date"
                className="form-input form-input-sm"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
            </div>
            <div className="form-group-inline">
              <label>End Date:</label>
              <input
                type="date"
                className="form-input form-input-sm"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </div>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={fetchReport}
            >
              Apply Dates
            </button>
          </div>
        )}
      </div>

      {/* Coverage Methodology & Notes Box */}
      {report?.coverage_notes && report.coverage_notes.length > 0 && (
        <div className="callout callout-info mb-4 report-coverage-callout">
          <div className="callout-icon">
            <Info size={16} />
          </div>
          <div className="callout-body">
            <strong>Data Integrity &amp; Coverage Methodology:</strong>
            <ul className="coverage-list mt-1">
              {report.coverage_notes.map((note, idx) => (
                <li key={idx}>{note}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Error State */}
      {errorMsg && !isLoading && (
        <div className="callout callout-danger mb-4">
          <div className="callout-icon">
            <XCircle size={18} />
          </div>
          <div className="callout-body">
            <strong>Error Loading Report:</strong>
            <p>{errorMsg}</p>
            <button type="button" className="btn btn-secondary btn-sm mt-2" onClick={fetchReport}>
              Retry
            </button>
          </div>
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="loading-state">
          <div className="spinner" />
          <p>Compiling cross-branch commit lineage, diff analytics, and merge records...</p>
        </div>
      )}

      {/* Report Body */}
      {!isLoading && report && (
        <div className="report-content-body">
          {/* Summary KPI Cards Grid */}
          <div className="report-kpi-grid mb-4">
            {mode === 'activity' && (
              <>
                <div className="kpi-card">
                  <span className="kpi-title">Total Commits</span>
                  <span className="kpi-value text-primary">{report.summary.total_commits ?? 0}</span>
                  <span className="kpi-subtext">Across selected time window</span>
                </div>
                <div className="kpi-card">
                  <span className="kpi-title">Unique Authors</span>
                  <span className="kpi-value text-accent">{report.summary.unique_authors ?? 0}</span>
                  <span className="kpi-subtext">Active contributors</span>
                </div>
                <div className="kpi-card">
                  <span className="kpi-title">Merge Commits</span>
                  <span className="kpi-value text-info">{report.summary.merge_commits ?? 0}</span>
                  <span className="kpi-subtext">Multi-parent reconciliations</span>
                </div>
                <div className="kpi-card">
                  <span className="kpi-title">Velocity</span>
                  <span className="kpi-value text-success">{report.summary.avg_commits_per_day ?? 0}</span>
                  <span className="kpi-subtext">Commits / day average</span>
                </div>
              </>
            )}

            {mode === 'data_schema' && (
              <>
                <div className="kpi-card">
                  <span className="kpi-title">Rows Inserted</span>
                  <span className="kpi-value text-success">+{report.summary.rows_inserted ?? 0}</span>
                  <span className="kpi-subtext">Net row additions</span>
                </div>
                <div className="kpi-card">
                  <span className="kpi-title">Rows Updated</span>
                  <span className="kpi-value text-warning">{report.summary.rows_updated ?? 0}</span>
                  <span className="kpi-subtext">Row modifications</span>
                </div>
                <div className="kpi-card">
                  <span className="kpi-title">Rows Deleted</span>
                  <span className="kpi-value text-danger">-{report.summary.rows_deleted ?? 0}</span>
                  <span className="kpi-subtext">Row removals</span>
                </div>
                <div className="kpi-card">
                  <span className="kpi-title">Schema Operations</span>
                  <span className="kpi-value text-info">{report.summary.schema_changes_count ?? 0}</span>
                  <span className="kpi-subtext">DDL structure evolutions</span>
                </div>
              </>
            )}

            {mode === 'merge_conflict' && (
              <>
                <div className="kpi-card">
                  <span className="kpi-title">Merge Attempts</span>
                  <span className="kpi-value text-primary">{report.summary.total_attempts ?? 0}</span>
                  <span className="kpi-subtext">Actual merge executions</span>
                </div>
                <div className="kpi-card">
                  <span className="kpi-title">Successful Merges</span>
                  <span className="kpi-value text-success">{report.summary.success_count ?? 0}</span>
                  <span className="kpi-subtext">{report.summary.success_rate_percent}% success rate</span>
                </div>
                <div className="kpi-card">
                  <span className="kpi-title">Conflict Rejections</span>
                  <span className="kpi-value text-danger">{report.summary.conflict_count ?? 0}</span>
                  <span className="kpi-subtext">{report.summary.conflict_rate_percent}% conflict rate</span>
                </div>
                <div className="kpi-card">
                  <span className="kpi-title">Other Rejections</span>
                  <span className="kpi-value text-warning">{report.summary.rejected_count ?? 0}</span>
                  <span className="kpi-subtext">Dirty working DB / checks</span>
                </div>
              </>
            )}
          </div>

          {/* Visual Charts */}
          <div className="report-charts-container mb-4">
            {/* Mode 1 Chart: Commit Activity Line Chart */}
            {mode === 'activity' && (
              <div className="card chart-card">
                <div className="chart-header">
                  <h3 className="card-title">Commit Activity Line Chart</h3>
                  <span className="badge badge-info">Timeline Trend</span>
                </div>

                {activitySeries.length === 0 ? (
                  <div className="empty-state py-4">No activity points in range</div>
                ) : (
                  <div className="line-chart-wrapper">
                    <svg viewBox="0 0 650 160" className="report-svg-chart">
                      {/* Grid Lines */}
                      <line x1="40" y1="20" x2="620" y2="20" stroke="var(--border-subtle)" strokeDasharray="3 3" />
                      <line x1="40" y1="75" x2="620" y2="75" stroke="var(--border-subtle)" strokeDasharray="3 3" />
                      <line x1="40" y1="130" x2="620" y2="130" stroke="var(--border-subtle)" />

                      {/* Y Axis Values */}
                      <text x="10" y="24" fontSize="10" fill="var(--text-muted)">{maxActivityCount}</text>
                      <text x="10" y="79" fontSize="10" fill="var(--text-muted)">{Math.round(maxActivityCount / 2)}</text>
                      <text x="10" y="134" fontSize="10" fill="var(--text-muted)">0</text>

                      {/* Area Fill & Trend Polyline */}
                      {activitySeries.length > 1 && (
                        <>
                          <polygon
                            points={`40,130 ${activitySeries
                              .map((p, idx) => {
                                const x = 40 + (idx / (activitySeries.length - 1)) * 580;
                                const y = 130 - (p.count / maxActivityCount) * 110;
                                return `${x},${y}`;
                              })
                              .join(' ')} 620,130`}
                            fill="rgba(37, 99, 235, 0.12)"
                          />
                          <polyline
                            points={activitySeries
                              .map((p, idx) => {
                                const x = 40 + (idx / (activitySeries.length - 1)) * 580;
                                const y = 130 - (p.count / maxActivityCount) * 110;
                                return `${x},${y}`;
                              })
                              .join(' ')}
                            fill="none"
                            stroke="var(--accent)"
                            strokeWidth="2.5"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </>
                      )}

                      {/* Data Dots & X Axis Labels */}
                      {activitySeries.map((p, idx) => {
                        const x =
                          activitySeries.length === 1
                            ? 330
                            : 40 + (idx / (activitySeries.length - 1)) * 580;
                        const y = 130 - (p.count / maxActivityCount) * 110;
                        const showLabel =
                          activitySeries.length <= 10 ||
                          idx === 0 ||
                          idx === activitySeries.length - 1 ||
                          idx % Math.ceil(activitySeries.length / 7) === 0;

                        return (
                          <g key={`pt-${p.date || idx}-${idx}`} className="chart-point-group">
                            <circle
                              cx={x}
                              cy={y}
                              r={p.count > 0 ? 4 : 2}
                              fill="var(--accent)"
                              stroke="var(--bg-card)"
                              strokeWidth="1.5"
                            >
                              <title>{`${p.date}: ${p.count} commit(s), ${p.authors_count} author(s)`}</title>
                            </circle>
                            {showLabel && (
                              <text
                                x={x}
                                y="148"
                                fontSize="9"
                                fill="var(--text-secondary)"
                                textAnchor="middle"
                              >
                                {p.date.slice(5)}
                              </text>
                            )}
                          </g>
                        );
                      })}
                    </svg>
                  </div>
                )}
              </div>
            )}

            {/* Mode 2 Chart: Stacked Bar Chart of Inserts, Updates, Deletes by Table */}
            {mode === 'data_schema' && (
              <div className="card chart-card">
                <div className="chart-header">
                  <h3 className="card-title">Row Changes by Table (Stacked Bar Chart)</h3>
                  <div className="chart-legend">
                    <span className="legend-item"><span className="legend-chip bg-success" /> Inserts</span>
                    <span className="legend-item"><span className="legend-chip bg-warning" /> Updates</span>
                    <span className="legend-item"><span className="legend-chip bg-danger" /> Deletes</span>
                  </div>
                </div>

                {tableChangesSeries.length === 0 ? (
                  <div className="empty-state py-4">No table mutations recorded for this filter scope</div>
                ) : (
                  <div className="stacked-bars-list">
                    {tableChangesSeries.map((item) => {
                      const insPct = (item.inserts / maxTableChanges) * 100;
                      const updPct = (item.updates / maxTableChanges) * 100;
                      const delPct = (item.deletes / maxTableChanges) * 100;

                      return (
                        <div key={item.table} className="table-bar-row">
                          <div className="table-bar-label font-mono">
                            <strong>{item.table}</strong>
                            <span className="text-secondary ml-2">({item.total} changes)</span>
                          </div>
                          <div className="stacked-track">
                            {insPct > 0 && (
                              <div
                                className="stacked-segment fill-success"
                                style={{ width: `${insPct}%` }}
                                title={`+${item.inserts} inserts`}
                              >
                                {item.inserts >= 2 && `+${item.inserts}`}
                              </div>
                            )}
                            {updPct > 0 && (
                              <div
                                className="stacked-segment fill-warning"
                                style={{ width: `${updPct}%` }}
                                title={`~${item.updates} updates`}
                              >
                                {item.updates >= 2 && `~${item.updates}`}
                              </div>
                            )}
                            {delPct > 0 && (
                              <div
                                className="stacked-segment fill-danger"
                                style={{ width: `${delPct}%` }}
                                title={`-${item.deletes} deletes`}
                              >
                                {item.deletes >= 2 && `-${item.deletes}`}
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {/* Mode 3 Chart: Merge Outcomes Bar Chart */}
            {mode === 'merge_conflict' && (
              <div className="card chart-card">
                <div className="chart-header">
                  <h3 className="card-title">Merge Outcomes Distribution</h3>
                  <span className="badge badge-primary">{totalMergeAttempts} Total Attempts</span>
                </div>

                {totalMergeAttempts === 0 ? (
                  <div className="empty-state py-4">No merge attempts recorded in this timeframe</div>
                ) : (
                  <div>
                    {/* Horizontal Outcome Bar */}
                    <div className="outcome-progress-bar mb-3">
                      {outcomeBreakdown.map((item) => {
                        const pct = (item.count / totalMergeAttempts) * 100;
                        if (pct <= 0) return null;
                        const fillClass =
                          item.status === 'Success'
                            ? 'bg-success'
                            : item.status === 'Conflict'
                            ? 'bg-danger'
                            : 'bg-warning';

                        return (
                          <div
                            key={item.status}
                            className={`outcome-segment ${fillClass}`}
                            style={{ width: `${pct}%` }}
                            title={`${item.status}: ${item.count} (${pct.toFixed(1)}%)`}
                          >
                            {pct >= 10 && `${item.status} (${pct.toFixed(0)}%)`}
                          </div>
                        );
                      })}
                    </div>

                    {/* Breakdown Cards */}
                    <div className="outcome-chips-row">
                      {outcomeBreakdown.map((item) => (
                        <div key={item.status} className="outcome-chip-card">
                          <div className="outcome-chip-header">
                            {item.status === 'Success' && <CheckCircle2 size={16} className="text-success" />}
                            {item.status === 'Conflict' && <AlertTriangle size={16} className="text-danger" />}
                            {item.status === 'Rejected' && <XCircle size={16} className="text-warning" />}
                            <strong>{item.status}</strong>
                          </div>
                          <div className="outcome-chip-count">{item.count}</div>
                          <div className="outcome-chip-subtext">
                            {totalMergeAttempts > 0
                              ? `${((item.count / totalMergeAttempts) * 100).toFixed(1)}% of total`
                              : '0%'}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Details Table */}
          <div className="card report-details-card">
            <div className="report-details-header">
              <h3 className="card-title">Detail Records ({filteredDetails.length})</h3>

              <div className="search-box">
                <input
                  type="text"
                  className="form-input form-input-sm"
                  placeholder="Filter detail rows..."
                  value={searchDetail}
                  onChange={(e) => setSearchDetail(e.target.value)}
                />
              </div>
            </div>

            {filteredDetails.length === 0 ? (
              <div className="empty-state py-4">No detail records found matching active filters</div>
            ) : (
              <div className="diff-table-container">
                <table className="diff-table">
                  <thead>
                    {mode === 'activity' && (
                      <tr>
                        <th>Commit #</th>
                        <th>Timestamp</th>
                        <th>Author</th>
                        <th>Merge?</th>
                        <th>Impacted Tables</th>
                        <th>Rows Changed</th>
                        <th>Commit Message</th>
                      </tr>
                    )}
                    {mode === 'data_schema' && (
                      <tr>
                        <th>Commit #</th>
                        <th>Timestamp</th>
                        <th>Author</th>
                        <th>Type</th>
                        <th>Table</th>
                        <th>Operation</th>
                        <th>Change Details</th>
                      </tr>
                    )}
                    {mode === 'merge_conflict' && (
                      <tr>
                        <th>ID</th>
                        <th>Attempted At</th>
                        <th>Actor</th>
                        <th>Source</th>
                        <th>Target</th>
                        <th>Outcome</th>
                        <th>Result / Conflict Summary</th>
                      </tr>
                    )}
                  </thead>
                  <tbody>
                    {mode === 'activity' &&
                      filteredDetails.map((row, idx) => (
                        <tr key={`act-${row.commit_id ?? idx}-${idx}`}>
                          <td className="font-mono">#{row.commit_id}</td>
                          <td className="text-secondary">{String(row.timestamp).slice(0, 19).replace('T', ' ')}</td>
                          <td><strong>{row.author}</strong></td>
                          <td>
                            {row.is_merge ? (
                              <span className="badge badge-info">Merge ({row.parent_commits?.length} parents)</span>
                            ) : (
                              <span className="text-secondary">Normal</span>
                            )}
                          </td>
                          <td>
                            {row.tables_impacted && row.tables_impacted.length > 0 ? (
                              <span className="font-mono" title={row.tables_impacted.join(', ')}>
                                {row.tables_impacted.slice(0, 3).join(', ')}
                                {row.tables_impacted.length > 3 && ` +${row.tables_impacted.length - 3}`}
                              </span>
                            ) : (
                              <span className="text-muted">—</span>
                            )}
                          </td>
                          <td className="font-mono">{row.rows_changed ?? 0}</td>
                          <td>{row.message}</td>
                        </tr>
                      ))}

                    {mode === 'data_schema' &&
                      filteredDetails.map((row, idx) => (
                        <tr key={`ds-${row.commit_id ?? ''}-${row.table ?? ''}-${row.operation ?? ''}-${idx}`}>
                          <td className="font-mono">#{row.commit_id}</td>
                          <td className="text-secondary">{String(row.timestamp).slice(0, 19).replace('T', ' ')}</td>
                          <td>{row.author}</td>
                          <td>
                            <span className={`badge ${row.change_category === 'SCHEMA' ? 'badge-info' : 'badge-snapshot'}`}>
                              {row.change_category}
                            </span>
                          </td>
                          <td className="font-mono"><strong>{row.table}</strong></td>
                          <td>
                            <span
                              className={`badge ${
                                row.operation === 'INSERT' || row.operation === 'CREATE_TABLE'
                                  ? 'badge-success'
                                  : row.operation === 'DELETE' || row.operation === 'DROP_TABLE'
                                  ? 'badge-danger'
                                  : 'badge-warning'
                              }`}
                            >
                              {row.operation}
                            </span>
                          </td>
                          <td className="font-mono text-secondary" style={{ maxWidth: 300, wordBreak: 'break-all' }}>
                            {String(row.details || '—')}
                          </td>
                        </tr>
                      ))}

                    {mode === 'merge_conflict' &&
                      filteredDetails.map((row, idx) => (
                        <tr key={`mc-${row.id ?? idx}-${idx}`}>
                          <td className="font-mono">{String(row.id)}</td>
                          <td className="text-secondary">{String(row.timestamp).slice(0, 19).replace('T', ' ')}</td>
                          <td><strong>{row.actor}</strong></td>
                          <td className="font-mono">{row.source}</td>
                          <td className="font-mono">{row.target}</td>
                          <td>
                            <span
                              className={`badge ${
                                row.outcome === 'success'
                                  ? 'badge-success'
                                  : row.outcome === 'conflict'
                                  ? 'badge-danger'
                                  : 'badge-warning'
                              }`}
                            >
                              {String(row.outcome).toUpperCase()}
                            </span>
                          </td>
                          <td>
                            {row.merge_commit_id ? (
                              <span className="text-success">
                                Commit #{row.merge_commit_id} created
                              </span>
                            ) : (
                              <span className={row.outcome === 'conflict' ? 'text-danger' : 'text-warning'}>
                                {row.conflict_summary}
                              </span>
                            )}
                            {row.is_historical_reconstruction && (
                              <span className="text-muted ml-2">(historical)</span>
                            )}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
};
