import React, { useState, useEffect } from 'react';
import {
  ArrowLeftRight,
  Search,
  FileDiff,
  Database,
  Code,
  PlusCircle,
  MinusCircle,
  Layers,
  Sparkles
} from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { apiRequest } from '../../services/api';
import { DiffResult, DiffChangeItem } from '../../types/api';

export const DiffTab: React.FC = () => {
  const { history, currentHead, diffPair, setDiffPair, settings, addToast } = useApp();

  const [fromCommit, setFromCommit] = useState<string>(
    diffPair.from !== '' ? String(diffPair.from) : '6'
  );
  const [toCommit, setToCommit] = useState<string>(
    diffPair.to !== '' ? String(diffPair.to) : '7'
  );
  const [isLoading, setIsLoading] = useState(false);
  const [diffResult, setDiffResult] = useState<DiffResult | null>(null);
  const [activeSubtab, setActiveSubtab] = useState<'schema' | 'rows' | 'raw'>('schema');

  // Handle external diff pair requests
  useEffect(() => {
    if (diffPair.from !== '') setFromCommit(String(diffPair.from));
    if (diffPair.to !== '') setToCommit(String(diffPair.to));

    const f = diffPair.from !== '' ? Number(diffPair.from) : 6;
    const t = diffPair.to !== '' ? Number(diffPair.to) : (currentHead ?? 7);

    if (!isNaN(f) && !isNaN(t) && f !== t) {
      setFromCommit(String(f));
      setToCommit(String(t));
      handleRunDiff(f, t);
    } else if (history.length >= 2 && !diffResult && !isLoading) {
      // Smart default to comparing first two available commits or 6 vs 7
      const target = currentHead ?? history[0]?.commit_id ?? 7;
      const base = history.find(c => (c.commit_id ?? c.id) !== target)?.commit_id ?? 6;
      setFromCommit(String(base));
      setToCommit(String(target));
      handleRunDiff(base, target);
    }
  }, [diffPair, currentHead, history.length]);

  const handleRunDiff = async (fromId?: number, toId?: number) => {
    const f = fromId !== undefined ? fromId : parseInt(fromCommit, 10);
    const t = toId !== undefined ? toId : parseInt(toCommit, 10);

    if (isNaN(f) || isNaN(t)) {
      addToast('Please enter both From Commit ID and To Commit ID', 'warning');
      return;
    }

    if (f === t) {
      addToast('Selecting two identical commits produces no changes. Select two different commits to compare.', 'info');
    }

    setIsLoading(true);
    setDiffResult(null);

    try {
      const data = await apiRequest<DiffResult>(`/diff/${f}/${t}`, {}, settings);
      setDiffResult(data);
    } catch (err: unknown) {
      const msg = (err as Error).message || 'Failed to compute diff';
      addToast(msg, 'error');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSwap = () => {
    const tmp = fromCommit;
    setFromCommit(toCommit);
    setToCommit(tmp);
    setDiffPair({ from: toCommit ? Number(toCommit) : '', to: tmp ? Number(tmp) : '' });
    if (toCommit && tmp) {
      handleRunDiff(Number(toCommit), Number(tmp));
    }
  };

  const handlePresetSelect = (f: number, t: number) => {
    setFromCommit(String(f));
    setToCommit(String(t));
    setDiffPair({ from: f, to: t });
    handleRunDiff(f, t);
  };

  // Normalize schema and row changes from both new format and fallback format
  const schemaChanges: DiffChangeItem[] = diffResult?.schema_changes || [];
  const rowChanges: DiffChangeItem[] = diffResult?.row_changes || [];

  // Categorize schema changes
  const addedTables = schemaChanges.filter(c => c.operation === 'CREATE_TABLE');
  const droppedTables = schemaChanges.filter(c => c.operation === 'DROP_TABLE');
  const columnChanges = schemaChanges.filter(c => c.operation.includes('COLUMN'));
  const constraintChanges = schemaChanges.filter(c => c.operation.includes('CONSTRAINT'));
  const indexChanges = schemaChanges.filter(c => c.operation.includes('INDEX'));
  const viewChanges = schemaChanges.filter(c => c.operation.includes('VIEW'));
  const sequenceChanges = schemaChanges.filter(c => c.operation.includes('SEQUENCE'));

  // Altered table list
  const alteredTableNames = Array.from(new Set([
    ...columnChanges.map(c => c.table).filter(Boolean),
    ...constraintChanges.map(c => c.table).filter(Boolean),
    ...indexChanges.map(c => c.table).filter(Boolean),
  ])) as string[];

  // Categorize row changes
  const insertedRows = rowChanges.filter(c => c.operation === 'INSERT');
  const deletedRows = rowChanges.filter(c => c.operation === 'DELETE');
  const updatedRows = rowChanges.filter(c => c.operation === 'UPDATE');

  // Group row changes by table
  const rowsByTable: Record<string, { inserts: DiffChangeItem[]; deletes: DiffChangeItem[]; updates: DiffChangeItem[] }> = {};
  rowChanges.forEach(change => {
    const table = change.table || 'unspecified';
    if (!rowsByTable[table]) {
      rowsByTable[table] = { inserts: [], deletes: [], updates: [] };
    }
    if (change.operation === 'INSERT') rowsByTable[table].inserts.push(change);
    else if (change.operation === 'DELETE') rowsByTable[table].deletes.push(change);
    else if (change.operation === 'UPDATE') rowsByTable[table].updates.push(change);
  });

  return (
    <section className="tab-content">
      <div className="view-header">
        <div>
          <h2>Snapshot &amp; Schema Diff Inspector</h2>
          <p className="text-secondary">
            Inspect schema modifications, constraints, and row content deltas between any two database snapshots.
          </p>
        </div>
      </div>

      {/* Quick Comparison Presets */}
      <div className="diff-presets-bar mb-4">
        <span className="diff-preset-label">
          <Sparkles size={14} className="text-accent inline-block mr-1" />
          Quick Presets:
        </span>
        <button
          className="pill-preset-btn"
          onClick={() => handlePresetSelect(6, 7)}
          title="Compare pre-merge main state with 3-Way Merge #7"
        >
          🔀 Pre-Merge vs 3-Way Merge (#6 → #7)
        </button>
        <button
          className="pill-preset-btn"
          onClick={() => handlePresetSelect(1, 7)}
          title="Compare empty initial schema with full merged database"
        >
          🚀 Initial Schema vs Full DB (#1 → #7)
        </button>
        <button
          className="pill-preset-btn"
          onClick={() => handlePresetSelect(2, 3)}
          title="Compare initial seed data with orders and indexes"
        >
          📦 Catalog vs Orders &amp; Views (#2 → #3)
        </button>
        <button
          className="pill-preset-btn"
          onClick={() => handlePresetSelect(3, 4)}
          title="Compare main with feature/discounts branch"
        >
          🌿 Main vs Feature/Discounts (#3 → #4)
        </button>
        <button
          className="pill-preset-btn"
          onClick={() => handlePresetSelect(7, 8)}
          title="Compare main with hotfix/pricing-adjustments branch"
        >
          🔥 Main vs Hotfix Pricing (#7 → #8)
        </button>
      </div>

      <div className="card diff-selector-card">
        <div className="diff-selector-row">
          <div className="selector-col">
            <label className="form-label">From Commit (Base):</label>
            <div className="input-with-button">
              <input
                type="number"
                className="form-input"
                placeholder="e.g. 6"
                value={fromCommit}
                onChange={(e) => setFromCommit(e.target.value)}
              />
              <select
                className="form-select form-select-sm"
                value={fromCommit}
                onChange={(e) => setFromCommit(e.target.value)}
              >
                <option value="">Select from history...</option>
                {history.map((c) => {
                  const cid = c.commit_id ?? c.id;
                  return (
                    <option key={`from-${cid}`} value={cid}>
                      #{cid}: {c.message.substring(0, 32)} ({c.author})
                    </option>
                  );
                })}
              </select>
            </div>
          </div>

          <button className="btn btn-secondary btn-icon" onClick={handleSwap} title="Swap commits">
            <ArrowLeftRight size={16} />
          </button>

          <div className="selector-col">
            <label className="form-label">To Commit (Target):</label>
            <div className="input-with-button">
              <input
                type="number"
                className="form-input"
                placeholder="e.g. 7"
                value={toCommit}
                onChange={(e) => setToCommit(e.target.value)}
              />
              <select
                className="form-select form-select-sm"
                value={toCommit}
                onChange={(e) => setToCommit(e.target.value)}
              >
                <option value="">Select from history...</option>
                {history.map((c) => {
                  const cid = c.commit_id ?? c.id;
                  return (
                    <option key={`to-${cid}`} value={cid}>
                      #{cid}: {c.message.substring(0, 32)} ({c.author})
                    </option>
                  );
                })}
              </select>
            </div>
          </div>

          <div className="selector-action">
            <button
              className="btn btn-primary btn-md"
              disabled={isLoading}
              onClick={() => handleRunDiff()}
            >
              <Search size={16} />
              <span>{isLoading ? 'Comparing...' : 'Compare Commits'}</span>
            </button>
          </div>
        </div>
      </div>

      {isLoading && (
        <div className="loading-state">
          <div className="spinner" />
          <p>Computing deterministic schema and row diff...</p>
        </div>
      )}

      {diffResult && !isLoading && (
        <div className="mt-6">
          {/* Summary Pills Bar */}
          <div className="diff-summary-bar">
            <div className={`summary-pill ${addedTables.length > 0 ? 'added' : ''}`}>
              <PlusCircle size={14} className="inline mr-1" />
              {addedTables.length} tables added
            </div>
            <div className={`summary-pill ${droppedTables.length > 0 ? 'removed' : ''}`}>
              <MinusCircle size={14} className="inline mr-1" />
              {droppedTables.length} tables dropped
            </div>
            <div className={`summary-pill ${alteredTableNames.length > 0 ? 'modified' : ''}`}>
              <Layers size={14} className="inline mr-1" />
              {alteredTableNames.length} tables altered
            </div>
            <div className={`summary-pill ${insertedRows.length > 0 ? 'added' : ''}`}>
              +{insertedRows.length} rows inserted
            </div>
            <div className={`summary-pill ${deletedRows.length > 0 ? 'removed' : ''}`}>
              -{deletedRows.length} rows deleted
            </div>
            <div className={`summary-pill ${updatedRows.length > 0 ? 'modified' : ''}`}>
              ~{updatedRows.length} rows updated
            </div>
          </div>

          {/* Subtabs for Schema vs Rows vs Raw */}
          <div className="diff-subtabs">
            <button
              className={`diff-subtab ${activeSubtab === 'schema' ? 'active' : ''}`}
              onClick={() => setActiveSubtab('schema')}
            >
              <FileDiff size={15} style={{ display: 'inline', marginRight: '6px' }} />
              Schema &amp; Metadata Diff ({schemaChanges.length})
            </button>
            <button
              className={`diff-subtab ${activeSubtab === 'rows' ? 'active' : ''}`}
              onClick={() => setActiveSubtab('rows')}
            >
              <Database size={15} style={{ display: 'inline', marginRight: '6px' }} />
              Row-Level Content Diff ({rowChanges.length})
            </button>
            <button
              className={`diff-subtab ${activeSubtab === 'raw' ? 'active' : ''}`}
              onClick={() => setActiveSubtab('raw')}
            >
              <Code size={15} style={{ display: 'inline', marginRight: '6px' }} />
              Raw JSON
            </button>
          </div>

          {/* Schema Diff Content */}
          {activeSubtab === 'schema' && (
            <div>
              {schemaChanges.length === 0 ? (
                <div className="empty-state">
                  <p className="text-secondary">No schema or metadata structure changes between these snapshots.</p>
                </div>
              ) : (
                <div className="diff-cards-stack">
                  {/* Created Tables */}
                  {addedTables.length > 0 && (
                    <div className="diff-section">
                      <div className="diff-section-header">
                        <span>Added Tables ({addedTables.length})</span>
                        <span className="badge badge-delta">+CREATED</span>
                      </div>
                      <div className="diff-body">
                        {addedTables.map((c, idx) => (
                          <div key={idx} className="diff-item added">
                            + Table: <strong>{c.table}</strong>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Dropped Tables */}
                  {droppedTables.length > 0 && (
                    <div className="diff-section">
                      <div className="diff-section-header">
                        <span>Dropped Tables ({droppedTables.length})</span>
                        <span className="badge badge-snapshot">-DROPPED</span>
                      </div>
                      <div className="diff-body">
                        {droppedTables.map((c, idx) => (
                          <div key={idx} className="diff-item removed">
                            - Table: <strong>{c.table}</strong>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Column Changes */}
                  {columnChanges.length > 0 && (
                    <div className="diff-section">
                      <div className="diff-section-header">
                        <span>Column Modifications ({columnChanges.length})</span>
                        <span className="badge badge-shared">COLUMNS</span>
                      </div>
                      <div className="diff-body">
                        {columnChanges.map((c, idx) => {
                          const op = c.operation;
                          const className =
                            op === 'ADD_COLUMN'
                              ? 'diff-item added'
                              : op === 'DROP_COLUMN'
                              ? 'diff-item removed'
                              : 'diff-item modified';
                          return (
                            <div key={idx} className={className}>
                              <span className="font-mono text-xs font-bold mr-2">[{op}]</span>
                              Table: <strong>{c.table}</strong> &rarr; Column: <strong>{c.column}</strong>
                              {Boolean(c.after && typeof c.after === 'object') && (
                                <span className="text-muted ml-2">
                                  ({String((c.after as { type?: unknown })?.type || 'type')})
                                </span>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Constraints, Views, Sequences */}
                  {(constraintChanges.length > 0 || viewChanges.length > 0 || sequenceChanges.length > 0) && (
                    <div className="diff-section">
                      <div className="diff-section-header">
                        <span>Constraints, Views &amp; Sequences</span>
                        <span className="badge badge-shared">METADATA</span>
                      </div>
                      <div className="diff-body">
                        {constraintChanges.map((c, idx) => (
                          <div key={`con-${idx}`} className="diff-item modified">
                            <span className="font-mono text-xs font-bold mr-2">[{c.operation}]</span>
                            Table: <strong>{c.table}</strong> &rarr; Constraint: <strong>{String(c.kind || c.name || 'Constraint')}</strong>
                          </div>
                        ))}
                        {viewChanges.map((c, idx) => (
                          <div key={`view-${idx}`} className="diff-item added">
                            <span className="font-mono text-xs font-bold mr-2">[{c.operation}]</span>
                            View: <strong>{String(c.kind || c.table || 'View')}</strong>
                          </div>
                        ))}
                        {sequenceChanges.map((c, idx) => (
                          <div key={`seq-${idx}`} className="diff-item added">
                            <span className="font-mono text-xs font-bold mr-2">[{c.operation}]</span>
                            Sequence: <strong>{String(c.kind || c.table || 'Sequence')}</strong>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Row Diff Content */}
          {activeSubtab === 'rows' && (
            <div>
              {rowChanges.length === 0 ? (
                <div className="empty-state">
                  <p className="text-secondary">No row contents changed between these snapshots.</p>
                </div>
              ) : (
                <div className="diff-cards-stack">
                  {Object.entries(rowsByTable).map(([tableName, data]) => {
                    const totalChanges = data.inserts.length + data.deletes.length + data.updates.length;
                    return (
                      <div key={tableName} className="diff-section">
                        <div className="diff-section-header">
                          <span>
                            Table: <strong>{tableName}</strong> ({totalChanges} change{totalChanges > 1 ? 's' : ''})
                          </span>
                          <span className="text-xs text-muted">
                            +{data.inserts.length} / -{data.deletes.length} / ~{data.updates.length}
                          </span>
                        </div>
                        <div className="diff-body">
                          {/* Inserts */}
                          {data.inserts.length > 0 && (
                            <div className="mb-3">
                              <h5 className="text-emerald-400 font-semibold mb-2">
                                + Inserted Rows ({data.inserts.length})
                              </h5>
                              <div className="diff-table-container">
                                <table className="diff-table">
                                  <tbody>
                                    {data.inserts.map((r, i) => (
                                      <tr key={`ins-${i}`} className="row-insert">
                                        <td style={{ width: '36px' }}><strong>+</strong></td>
                                        <td>
                                          <pre className="font-mono text-xs m-0">
                                            {JSON.stringify(r.after || r.key || r, null, 2)}
                                          </pre>
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          )}

                          {/* Deletes */}
                          {data.deletes.length > 0 && (
                            <div className="mb-3">
                              <h5 className="text-rose-400 font-semibold mb-2">
                                - Deleted Rows ({data.deletes.length})
                              </h5>
                              <div className="diff-table-container">
                                <table className="diff-table">
                                  <tbody>
                                    {data.deletes.map((r, i) => (
                                      <tr key={`del-${i}`} className="row-delete">
                                        <td style={{ width: '36px' }}><strong>-</strong></td>
                                        <td>
                                          <pre className="font-mono text-xs m-0">
                                            {JSON.stringify(r.before || r.key || r, null, 2)}
                                          </pre>
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          )}

                          {/* Updates */}
                          {data.updates.length > 0 && (
                            <div>
                              <h5 className="text-amber-400 font-semibold mb-2">
                                ~ Updated Rows ({data.updates.length})
                              </h5>
                              <div className="diff-table-container">
                                <table className="diff-table">
                                  <thead>
                                    <tr>
                                      <th style={{ width: '180px' }}>Row Identity</th>
                                      <th>Modified Columns (Before &rarr; After)</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {data.updates.map((u, i) => (
                                      <tr key={`upd-${i}`} className="row-update">
                                        <td>
                                          <code>{JSON.stringify(u.key || 'Row')}</code>
                                        </td>
                                        <td>
                                          <div className="update-diff-details">
                                            {u.changed_columns && u.changed_columns.length > 0 ? (
                                              u.changed_columns.map(col => {
                                                const beforeVal = (u.before as Record<string, unknown>)?.[col];
                                                const afterVal = (u.after as Record<string, unknown>)?.[col];
                                                return (
                                                  <div key={col} className="col-change-row">
                                                    <strong className="text-secondary">{col}:</strong>{' '}
                                                    <span className="diff-del-val">{JSON.stringify(beforeVal)}</span>{' '}
                                                    &rarr;{' '}
                                                    <span className="diff-ins-val">{JSON.stringify(afterVal)}</span>
                                                  </div>
                                                );
                                              })
                                            ) : (
                                              <pre className="font-mono text-xs m-0">
                                                {JSON.stringify({ before: u.before, after: u.after }, null, 2)}
                                              </pre>
                                            )}
                                          </div>
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
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

          {/* Raw JSON */}
          {activeSubtab === 'raw' && (
            <div className="code-container">
              <pre>
                <code>{JSON.stringify(diffResult, null, 2)}</code>
              </pre>
            </div>
          )}
        </div>
      )}
    </section>
  );
};
