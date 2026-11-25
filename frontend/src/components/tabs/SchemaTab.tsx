import React, { useState, useEffect } from 'react';
import {
  Layers,
  Database,
  Key,
  Link,
  Search,
  Hash,
  Eye,
  GitBranch,
  RefreshCw,
  Table as TableIcon,
  FileCode,
  Sparkles
} from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { apiRequest } from '../../services/api';
import { DatabaseSchemaResponse, TableSchemaInfo } from '../../types/api';

export const SchemaTab: React.FC = () => {
  const { branches, history, currentHead, activeBranch, settings, addToast } = useApp();

  const [selectedTarget, setSelectedTarget] = useState<string>('live');
  const [selectedCommitId, setSelectedCommitId] = useState<string>('');
  const [selectedBranch, setSelectedBranch] = useState<string>('');
  const [schemaData, setSchemaData] = useState<DatabaseSchemaResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [searchFilter, setSearchFilter] = useState('');
  const [activeViewMode, setActiveViewMode] = useState<'tables' | 'relationships' | 'views_seq'>('tables');

  const fetchSchema = async (type: 'live' | 'branch' | 'commit', value?: string | number) => {
    setIsLoading(true);
    try {
      let url = '/schema';
      if (type === 'commit' && value !== undefined && value !== '') {
        url = `/schema?commit_id=${value}`;
      } else if (type === 'branch' && value) {
        url = `/schema?branch=${encodeURIComponent(String(value))}`;
      }

      const data = await apiRequest<DatabaseSchemaResponse>(url, {}, settings);
      setSchemaData(data);
    } catch (err: unknown) {
      const msg = (err as Error).message || 'Failed to fetch database schema';
      addToast(msg, 'error');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchSchema('live');
  }, []);

  const handleTargetChange = (type: 'live' | 'branch' | 'commit', value?: string | number) => {
    setSelectedTarget(type);
    if (type === 'live') {
      setSelectedBranch('');
      setSelectedCommitId('');
      fetchSchema('live');
    } else if (type === 'branch') {
      const branchName = value ? String(value) : (activeBranch || 'main');
      setSelectedBranch(branchName);
      setSelectedCommitId('');
      fetchSchema('branch', branchName);
    } else if (type === 'commit') {
      const cid = value !== undefined ? String(value) : String(currentHead ?? 7);
      setSelectedCommitId(cid);
      setSelectedBranch('');
      fetchSchema('commit', cid);
    }
  };

  // Filter tables by search query
  const tables = schemaData?.tables || {};
  const filteredTables = Object.entries(tables).filter(([tableName, info]) => {
    if (!searchFilter.trim()) return true;
    const q = searchFilter.toLowerCase();
    if (tableName.toLowerCase().includes(q)) return true;
    return info.columns.some((col) => col.name.toLowerCase().includes(q) || col.type.toLowerCase().includes(q));
  });

  // Calculate total rows across all tables
  const totalRows = Object.values(tables).reduce((acc, t) => acc + (t.row_count || 0), 0);
  const totalColumns = Object.values(tables).reduce((acc, t) => acc + (t.columns?.length || 0), 0);

  // Extract all foreign key relationships
  const allForeignKeys: {
    fromTable: string;
    fromCols: string[];
    toTable: string;
    toCols: string[];
    constraintName?: string;
  }[] = [];

  Object.entries(tables).forEach(([tblName, tblInfo]) => {
    (tblInfo.foreign_keys || []).forEach((fk) => {
      if (fk.referenced_table) {
        allForeignKeys.push({
          fromTable: tblName,
          fromCols: fk.columns || [],
          toTable: fk.referenced_table,
          toCols: fk.referenced_columns || [],
          constraintName: fk.name,
        });
      }
    });
  });

  return (
    <section className="tab-content">
      <div className="view-header">
        <div>
          <h2>Visual Database Schema &amp; Lineage</h2>
          <p className="text-secondary">
            Inspect relational database schemas, tables, constraints, types, foreign keys, and views across branches and commits.
          </p>
        </div>
        <div className="view-controls">
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => {
              if (selectedTarget === 'commit') fetchSchema('commit', selectedCommitId);
              else if (selectedTarget === 'branch') fetchSchema('branch', selectedBranch);
              else fetchSchema('live');
            }}
            title="Reload schema metadata"
          >
            <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
            <span>Reload</span>
          </button>
        </div>
      </div>

      {/* Selector & Switcher Bar */}
      <div className="card mb-6">
        <div className="schema-target-selector-row">
          <div className="schema-selector-group">
            <span className="schema-selector-label">Inspect Context:</span>
            <div className="segmented-pill-selector">
              <button
                className={`segmented-pill-item ${selectedTarget === 'live' ? 'active' : ''}`}
                onClick={() => handleTargetChange('live')}
              >
                <Database size={14} className="inline mr-1" />
                Live Database
              </button>
              <button
                className={`segmented-pill-item ${selectedTarget === 'branch' ? 'active' : ''}`}
                onClick={() => handleTargetChange('branch', activeBranch || 'main')}
              >
                <GitBranch size={14} className="inline mr-1" />
                Branch HEAD
              </button>
              <button
                className={`segmented-pill-item ${selectedTarget === 'commit' ? 'active' : ''}`}
                onClick={() => handleTargetChange('commit', currentHead ?? 7)}
              >
                <Hash size={14} className="inline mr-1" />
                Historic Commit
              </button>
            </div>
          </div>

          {selectedTarget === 'branch' && (
            <div className="schema-dropdown-group">
              <label className="form-label mb-0 mr-2">Branch:</label>
              <select
                className="form-select form-select-sm"
                value={selectedBranch}
                onChange={(e) => handleTargetChange('branch', e.target.value)}
              >
                {branches.map((b) => (
                  <option key={b.name} value={b.name}>
                    🌿 {b.name} {b.is_current ? '(active)' : ''}
                  </option>
                ))}
              </select>
            </div>
          )}

          {selectedTarget === 'commit' && (
            <div className="schema-dropdown-group">
              <label className="form-label mb-0 mr-2">Commit Snapshot:</label>
              <select
                className="form-select form-select-sm"
                value={selectedCommitId}
                onChange={(e) => handleTargetChange('commit', e.target.value)}
              >
                {history.map((c) => {
                  const cid = c.commit_id ?? c.id;
                  return (
                    <option key={cid} value={cid}>
                      #{cid}: {c.message.substring(0, 36)} ({c.author})
                    </option>
                  );
                })}
              </select>
            </div>
          )}
        </div>

        {schemaData && (
          <div className="schema-target-badge-row mt-4">
            <span className="schema-target-pill">
              <Sparkles size={13} className="text-accent mr-1 inline" />
              Showing: <strong>{schemaData.target}</strong>
            </span>
          </div>
        )}
      </div>

      {isLoading && (
        <div className="loading-state">
          <div className="spinner" />
          <p>Loading PostgreSQL schema metadata and constraint definitions...</p>
        </div>
      )}

      {schemaData && !isLoading && (
        <div>
          {/* Schema High-Level Metrics Grid */}
          <div className="schema-metrics-grid mb-6">
            <div className="schema-metric-card">
              <div className="metric-icon-circle">
                <TableIcon size={18} />
              </div>
              <div className="metric-details">
                <div className="metric-title">Tables</div>
                <div className="metric-number">{schemaData.total_tables}</div>
              </div>
            </div>

            <div className="schema-metric-card">
              <div className="metric-icon-circle">
                <Layers size={18} />
              </div>
              <div className="metric-details">
                <div className="metric-title">Columns</div>
                <div className="metric-number">{totalColumns}</div>
              </div>
            </div>

            <div className="schema-metric-card">
              <div className="metric-icon-circle">
                <Link size={18} />
              </div>
              <div className="metric-details">
                <div className="metric-title">Foreign Keys</div>
                <div className="metric-number">{allForeignKeys.length}</div>
              </div>
            </div>

            <div className="schema-metric-card">
              <div className="metric-icon-circle">
                <Database size={18} />
              </div>
              <div className="metric-details">
                <div className="metric-title">Total Rows</div>
                <div className="metric-number">{totalRows.toLocaleString()}</div>
              </div>
            </div>

            <div className="schema-metric-card">
              <div className="metric-icon-circle">
                <Eye size={18} />
              </div>
              <div className="metric-details">
                <div className="metric-title">Views &amp; Sequences</div>
                <div className="metric-number">
                  {schemaData.total_views} View{schemaData.total_views !== 1 ? 's' : ''} / {schemaData.total_sequences} Seq
                </div>
              </div>
            </div>
          </div>

          {/* Subtabs & Search */}
          <div className="schema-subbar mb-6">
            <div className="diff-subtabs mb-0">
              <button
                className={`diff-subtab ${activeViewMode === 'tables' ? 'active' : ''}`}
                onClick={() => setActiveViewMode('tables')}
              >
                <TableIcon size={15} className="inline mr-1" />
                Tables &amp; Schemas ({filteredTables.length})
              </button>
              <button
                className={`diff-subtab ${activeViewMode === 'relationships' ? 'active' : ''}`}
                onClick={() => setActiveViewMode('relationships')}
              >
                <Link size={15} className="inline mr-1" />
                Entity Relationships ({allForeignKeys.length})
              </button>
              <button
                className={`diff-subtab ${activeViewMode === 'views_seq' ? 'active' : ''}`}
                onClick={() => setActiveViewMode('views_seq')}
              >
                <FileCode size={15} className="inline mr-1" />
                Views &amp; Sequences
              </button>
            </div>

            <div className="schema-search-container">
              <Search size={15} className="search-icon-inside" />
              <input
                type="text"
                className="form-input schema-search-input"
                placeholder="Search tables or columns..."
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
              />
            </div>
          </div>

          {/* VIEW MODE 1: Tables Grid */}
          {activeViewMode === 'tables' && (
            <div className="schema-tables-grid">
              {filteredTables.length === 0 ? (
                <div className="empty-state">
                  <p className="text-secondary">No tables match &quot;{searchFilter}&quot;.</p>
                </div>
              ) : (
                filteredTables.map(([tableName, tableInfo]: [string, TableSchemaInfo]) => {
                  return (
                    <div key={tableName} className="schema-table-card">
                      <div className="table-card-header">
                        <div className="table-card-title-group">
                          <TableIcon size={16} className="text-accent" />
                          <span className="table-card-name">{tableName}</span>
                        </div>
                        <span className="table-row-badge">
                          {tableInfo.row_count || 0} row{tableInfo.row_count !== 1 ? 's' : ''}
                        </span>
                      </div>

                      {/* Columns List */}
                      <div className="table-columns-container">
                        <table className="schema-columns-table">
                          <thead>
                            <tr>
                              <th>Column</th>
                              <th>Type</th>
                              <th>Attributes</th>
                            </tr>
                          </thead>
                          <tbody>
                            {tableInfo.columns.map((col) => (
                              <tr key={col.name} className={col.is_pk ? 'pk-row' : ''}>
                                <td className="col-name-cell">
                                  {col.is_pk && (
                                    <span title="Primary Key">
                                      <Key size={12} className="inline mr-1 text-amber-400" />
                                    </span>
                                  )}
                                  <span className="font-semibold">{col.name}</span>
                                </td>
                                <td className="col-type-cell font-mono">
                                  {col.type}
                                </td>
                                <td className="col-attr-cell">
                                  {col.is_pk && <span className="attr-pill pk">PK</span>}
                                  {!col.nullable && !col.is_pk && (
                                    <span className="attr-pill req">NOT NULL</span>
                                  )}
                                  {col.nullable && <span className="attr-pill opt">NULL</span>}
                                  {col.default && (
                                    <span
                                      className="attr-pill def font-mono text-xs"
                                      title={`Default: ${col.default}`}
                                    >
                                      default
                                    </span>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>

                      {/* Foreign Keys on this table */}
                      {tableInfo.foreign_keys && tableInfo.foreign_keys.length > 0 && (
                        <div className="table-card-fks">
                          <div className="fk-title">Foreign Key Relations:</div>
                          {tableInfo.foreign_keys.map((fk, i) => (
                            <div key={i} className="fk-item-pill">
                              <Link size={11} className="inline mr-1 text-accent" />
                              <span>
                                {fk.columns.join(', ')} &rarr; <strong>{fk.referenced_table}</strong>
                                ({fk.referenced_columns?.join(', ') || 'id'})
                              </span>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Indexes on this table */}
                      {tableInfo.indexes && tableInfo.indexes.length > 0 && (
                        <div className="table-card-indexes">
                          <span className="text-muted text-xs font-semibold mr-1">Indexes:</span>
                          {tableInfo.indexes.map((idx, i) => (
                            <span key={i} className="index-pill" title={idx.definition}>
                              {idx.name}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          )}

          {/* VIEW MODE 2: Relationships View */}
          {activeViewMode === 'relationships' && (
            <div className="schema-relationships-container">
              <div className="card">
                <h3 className="card-title">Entity Relationships &amp; Foreign Keys</h3>
                <p className="text-secondary text-sm mb-4">
                  Foreign key integrity constraints connecting relational tables in this database state.
                </p>

                {allForeignKeys.length === 0 ? (
                  <div className="empty-state">
                    <p className="text-secondary">No foreign key constraints defined in this snapshot.</p>
                  </div>
                ) : (
                  <div className="er-links-list">
                    {allForeignKeys.map((fk, idx) => (
                      <div key={idx} className="er-link-card">
                        <div className="er-link-from">
                          <TableIcon size={14} className="inline mr-1 text-accent" />
                          <span className="font-bold">{fk.fromTable}</span>
                          <span className="er-cols font-mono">({fk.fromCols.join(', ')})</span>
                        </div>

                        <div className="er-link-arrow">
                          <span className="er-arrow-line" />
                          <span className="er-badge">REFERENCES</span>
                          <span className="er-arrow-line" />
                        </div>

                        <div className="er-link-to">
                          <TableIcon size={14} className="inline mr-1 text-emerald-400" />
                          <span className="font-bold">{fk.toTable}</span>
                          <span className="er-cols font-mono">({fk.toCols.join(', ') || 'id'})</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* VIEW MODE 3: Views & Sequences */}
          {activeViewMode === 'views_seq' && (
            <div className="schema-views-container">
              <div className="card mb-4">
                <h3 className="card-title">Database Views</h3>
                {Object.keys(schemaData.views || {}).length === 0 ? (
                  <p className="text-secondary">No views defined in this snapshot.</p>
                ) : (
                  Object.entries(schemaData.views).map(([viewName, viewInfo]) => (
                    <div key={viewName} className="view-card-item">
                      <div className="view-card-header">
                        <Eye size={15} className="text-accent inline mr-1" />
                        <strong>{viewName}</strong>
                      </div>
                      <div className="code-container mt-2">
                        <pre>
                          <code>{viewInfo.definition}</code>
                        </pre>
                      </div>
                    </div>
                  ))
                )}
              </div>

              <div className="card">
                <h3 className="card-title">Database Sequences</h3>
                {Object.keys(schemaData.sequences || {}).length === 0 ? (
                  <p className="text-secondary">No sequence objects defined in this snapshot.</p>
                ) : (
                  <div className="diff-table-container">
                    <table className="diff-table">
                      <thead>
                        <tr>
                          <th>Sequence Name</th>
                          <th>Last Value</th>
                          <th>Start Value</th>
                          <th>Increment</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(schemaData.sequences).map(([seqName, seqInfo]) => (
                          <tr key={seqName}>
                            <td className="font-bold font-mono">{seqName}</td>
                            <td>{seqInfo.last_value ?? 'N/A'}</td>
                            <td>{seqInfo.start_value ?? 1}</td>
                            <td>{seqInfo.increment_by ?? 1}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
};
