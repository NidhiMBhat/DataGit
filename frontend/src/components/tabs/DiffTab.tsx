import React, { useState, useEffect } from 'react';
import { ArrowLeftRight, Search, FileDiff, Database, Code } from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { apiRequest } from '../../services/api';
import { DiffResult, SchemaDiff, TableRowDiff } from '../../types/api';

export const DiffTab: React.FC = () => {
  const { history, diffPair, setDiffPair, settings, addToast } = useApp();

  const [fromCommit, setFromCommit] = useState<string>(diffPair.from ? String(diffPair.from) : '');
  const [toCommit, setToCommit] = useState<string>(diffPair.to ? String(diffPair.to) : '');
  const [isLoading, setIsLoading] = useState(false);
  const [diffResult, setDiffResult] = useState<DiffResult | null>(null);
  const [activeSubtab, setActiveSubtab] = useState<'schema' | 'rows' | 'raw'>('schema');

  useEffect(() => {
    if (diffPair.from !== '') setFromCommit(String(diffPair.from));
    if (diffPair.to !== '') setToCommit(String(diffPair.to));
    if (diffPair.from !== '' && diffPair.to !== '') {
      handleRunDiff(Number(diffPair.from), Number(diffPair.to));
    }
  }, [diffPair]);

  const handleRunDiff = async (fromId?: number, toId?: number) => {
    const f = fromId !== undefined ? fromId : parseInt(fromCommit, 10);
    const t = toId !== undefined ? toId : parseInt(toCommit, 10);

    if (isNaN(f) || isNaN(t)) {
      addToast('Please enter both From Commit ID and To Commit ID', 'warning');
      return;
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
  };

  // Compute summary metrics
  const schema: SchemaDiff = diffResult?.schema_diff || diffResult?.schema || {};
  const rows: Record<string, TableRowDiff> = diffResult?.row_diff || diffResult?.rows || {};

  const tablesAdded = schema.added_tables?.length || 0;
  const tablesDropped = schema.dropped_tables?.length || 0;
  const tablesAltered = schema.altered_tables?.length || 0;

  let rowsInserted = 0;
  let rowsDeleted = 0;
  let rowsUpdated = 0;

  Object.values(rows).forEach((tbl) => {
    rowsInserted += (tbl.inserted || tbl.inserts || []).length;
    rowsDeleted += (tbl.deleted || tbl.deletes || []).length;
    rowsUpdated += (tbl.updated || tbl.updates || []).length;
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

      <div className="card diff-selector-card">
        <div className="diff-selector-row">
          <div className="selector-col">
            <label className="form-label">From Commit (Base):</label>
            <div className="input-with-button">
              <input
                type="number"
                className="form-input"
                placeholder="e.g. 1"
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
                      #{cid}: {c.message.substring(0, 25)} ({c.author})
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
                placeholder="e.g. 2"
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
                      #{cid}: {c.message.substring(0, 25)} ({c.author})
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
          <p>Computing schema and row diff...</p>
        </div>
      )}

      {diffResult && !isLoading && (
        <div className="mt-6">
          <div className="diff-summary-bar">
            <div className="summary-pill added">{tablesAdded} tables added</div>
            <div className="summary-pill removed">{tablesDropped} tables dropped</div>
            <div className="summary-pill modified">{tablesAltered} tables altered</div>
            <div className="summary-pill added">{rowsInserted} rows inserted</div>
            <div className="summary-pill removed">{rowsDeleted} rows deleted</div>
            <div className="summary-pill modified">{rowsUpdated} rows updated</div>
          </div>

          <div className="diff-subtabs">
            <button
              className={`diff-subtab ${activeSubtab === 'schema' ? 'active' : ''}`}
              onClick={() => setActiveSubtab('schema')}
            >
              <FileDiff size={15} style={{ display: 'inline', marginRight: '6px' }} />
              Schema &amp; Metadata Diff
            </button>
            <button
              className={`diff-subtab ${activeSubtab === 'rows' ? 'active' : ''}`}
              onClick={() => setActiveSubtab('rows')}
            >
              <Database size={15} style={{ display: 'inline', marginRight: '6px' }} />
              Row-Level Content Diff
            </button>
            <button
              className={`diff-subtab ${activeSubtab === 'raw' ? 'active' : ''}`}
              onClick={() => setActiveSubtab('raw')}
            >
              <Code size={15} style={{ display: 'inline', marginRight: '6px' }} />
              Raw JSON
            </button>
          </div>

          {activeSubtab === 'schema' && (
            <div>
              {tablesAdded === 0 && tablesDropped === 0 && tablesAltered === 0 && (
                <div className="empty-state">
                  <p className="text-secondary">No schema or metadata structure changes between these snapshots.</p>
                </div>
              )}

              {tablesAdded > 0 && (
                <div className="diff-section">
                  <div className="diff-section-header">
                    <span>Added Tables ({tablesAdded})</span>
                    <span className="badge badge-delta">+NEW</span>
                  </div>
                  <div className="diff-body">
                    {schema.added_tables?.map((tbl, idx) => {
                      const name = typeof tbl === 'string' ? tbl : tbl.table_name || tbl.name;
                      return (
                        <div key={idx} className="diff-item added">
                          + Table: <strong>{name}</strong>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {tablesDropped > 0 && (
                <div className="diff-section">
                  <div className="diff-section-header">
                    <span>Dropped Tables ({tablesDropped})</span>
                    <span className="badge badge-snapshot">-DROPPED</span>
                  </div>
                  <div className="diff-body">
                    {schema.dropped_tables?.map((tbl, idx) => {
                      const name = typeof tbl === 'string' ? tbl : tbl.table_name || tbl.name;
                      return (
                        <div key={idx} className="diff-item removed">
                          - Table: <strong>{name}</strong>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {tablesAltered > 0 && (
                <div className="diff-section">
                  <div className="diff-section-header">
                    <span>Altered Tables ({tablesAltered})</span>
                    <span className="badge badge-shared">~MODIFIED</span>
                  </div>
                  <div className="diff-body">
                    {schema.altered_tables?.map((tbl, idx) => {
                      const name = tbl.table_name || tbl.name || 'Table';
                      return (
                        <div key={idx} style={{ marginBottom: '14px' }}>
                          <div style={{ fontWeight: 600, marginBottom: '6px' }}>Table: {name}</div>
                          {tbl.added_columns?.map((c, i) => (
                            <div key={`col-add-${i}`} className="diff-item added">
                              + Col: {c.name} ({c.type || 'any'})
                            </div>
                          ))}
                          {tbl.dropped_columns?.map((c, i) => (
                            <div key={`col-drop-${i}`} className="diff-item removed">
                              - Col: {c.name}
                            </div>
                          ))}
                          {tbl.altered_columns?.map((c, i) => (
                            <div key={`col-alt-${i}`} className="diff-item modified">
                              ~ Col: {c.name} ({c.old_type} → {c.new_type})
                            </div>
                          ))}
                          {tbl.added_constraints?.map((c, i) => (
                            <div key={`con-add-${i}`} className="diff-item added">
                              + Constraint: {c.name}
                            </div>
                          ))}
                          {tbl.dropped_constraints?.map((c, i) => (
                            <div key={`con-drop-${i}`} className="diff-item removed">
                              - Constraint: {c.name}
                            </div>
                          ))}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

          {activeSubtab === 'rows' && (
            <div>
              {Object.keys(rows).length === 0 ? (
                <div className="empty-state">
                  <p className="text-secondary">No row changes recorded between these snapshots.</p>
                </div>
              ) : (
                Object.entries(rows).map(([tableName, tblDiff]) => {
                  const ins = tblDiff.inserted || tblDiff.inserts || [];
                  const del = tblDiff.deleted || tblDiff.deletes || [];
                  const upd = tblDiff.updated || tblDiff.updates || [];

                  return (
                    <div key={tableName} className="diff-section">
                      <div className="diff-section-header">
                        <span>
                          Table: <strong>{tableName}</strong>
                        </span>
                        <span className="text-xs text-muted">
                          +{ins.length} / -{del.length} / ~{upd.length}
                        </span>
                      </div>
                      <div className="diff-body">
                        {ins.length > 0 && (
                          <div style={{ marginBottom: '12px' }}>
                            <h5 style={{ color: '#34d399', marginBottom: '6px' }}>
                              + Inserted Rows ({ins.length})
                            </h5>
                            <div className="diff-table-container">
                              <table className="diff-table">
                                <tbody>
                                  {ins.map((r, i) => (
                                    <tr key={`ins-${i}`} className="row-insert">
                                      <td style={{ width: '40px' }}>
                                        <strong>+</strong>
                                      </td>
                                      <td>{JSON.stringify(r)}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        )}

                        {del.length > 0 && (
                          <div style={{ marginBottom: '12px' }}>
                            <h5 style={{ color: '#f87171', marginBottom: '6px' }}>
                              - Deleted Rows ({del.length})
                            </h5>
                            <div className="diff-table-container">
                              <table className="diff-table">
                                <tbody>
                                  {del.map((r, i) => (
                                    <tr key={`del-${i}`} className="row-delete">
                                      <td style={{ width: '40px' }}>
                                        <strong>-</strong>
                                      </td>
                                      <td>{JSON.stringify(r)}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        )}

                        {upd.length > 0 && (
                          <div>
                            <h5 style={{ color: '#fbbf24', marginBottom: '6px' }}>
                              ~ Updated Rows ({upd.length})
                            </h5>
                            <div className="diff-table-container">
                              <table className="diff-table">
                                <thead>
                                  <tr>
                                    <th style={{ width: '180px' }}>Row Key / Identity</th>
                                    <th>Changes (Old → New)</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {upd.map((u, i) => (
                                    <tr key={`upd-${i}`} className="row-update">
                                      <td>
                                        <code>{JSON.stringify(u.key || u.primary_key || u.identity || 'Row')}</code>
                                      </td>
                                      <td>
                                        <pre className="font-mono text-xs" style={{ margin: 0 }}>
                                          {JSON.stringify(u.changes || u.diff || u, null, 2)}
                                        </pre>
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
                })
              )}
            </div>
          )}

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
