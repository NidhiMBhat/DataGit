import React, { useState } from 'react';
import {
  Zap,
  X,
  Play,
  RotateCcw,
  ShoppingBag,
  Tag,
  Rocket,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  Camera,
  Terminal,
  Database
} from 'lucide-react';
import { useApp } from '../context/AppContext';

export const DemoPlaygroundModal: React.FC = () => {
  const {
    isDemoModalOpen,
    setIsDemoModalOpen,
    workspaceStatus,
    isWorkspaceDirty,
    executeScenario,
    setActiveTab,
    addToast,
    currentHead,
  } = useApp();

  const [customSql, setCustomSql] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [lastExecutedSql, setLastExecutedSql] = useState<string | null>(null);

  if (!isDemoModalOpen) return null;

  const handleRunScenario = async (scenarioKey: string, custom?: string) => {
    setIsRunning(true);
    try {
      const res = await executeScenario(scenarioKey, custom);
      setLastExecutedSql(res.executed_sql);
      addToast(
        scenarioKey === 'reset_clean'
          ? 'Database restored cleanly to HEAD snapshot'
          : `Live demo change applied: ${res.title}`,
        'success'
      );
    } catch (err: unknown) {
      const msg = (err as Error).message || 'Failed to execute scenario';
      addToast(msg, 'error');
    } finally {
      setIsRunning(false);
    }
  };

  const handleReviewInDiff = () => {
    setIsDemoModalOpen(false);
    setActiveTab('diff');
  };

  const handleCommitLiveChanges = () => {
    setIsDemoModalOpen(false);
    setActiveTab('snapshot');
  };

  const summary = workspaceStatus?.summary || {
    tables_added: 0,
    tables_dropped: 0,
    tables_altered: 0,
    rows_inserted: 0,
    rows_deleted: 0,
    rows_updated: 0,
  };

  return (
    <div className="modal-backdrop">
      <div className="modal-window demo-modal-window">
        {/* Modal Header */}
        <div className="modal-header">
          <div className="modal-title-group">
            <div className="demo-icon-badge">
              <Zap size={20} className="text-amber-400" />
            </div>
            <div>
              <h3>Live Database Playground</h3>
              <p className="text-secondary text-xs">
                Manipulate the actual PostgreSQL database in real-time to demonstrate DataGit version tracking.
              </p>
            </div>
          </div>
          <button
            className="modal-close-btn"
            onClick={() => setIsDemoModalOpen(false)}
            title="Close playground"
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="modal-body">
          {/* Live Workspace Status Card */}
          <div className={`demo-status-card ${isWorkspaceDirty ? 'dirty' : 'clean'}`}>
            <div className="status-header-row">
              <div className="status-indicator-group">
                {isWorkspaceDirty ? (
                  <AlertTriangle size={18} className="text-amber-400" />
                ) : (
                  <CheckCircle2 size={18} className="text-emerald-400" />
                )}
                <span className="status-title">
                  {isWorkspaceDirty
                    ? 'Uncommitted Changes Detected in PostgreSQL'
                    : `Workspace in Sync with HEAD #${currentHead ?? 'Detached'}`}
                </span>
              </div>
              <span className={`status-badge-pill ${isWorkspaceDirty ? 'dirty' : 'clean'}`}>
                {isWorkspaceDirty ? 'Working Tree Dirty' : 'Clean'}
              </span>
            </div>

            {isWorkspaceDirty ? (
              <div className="uncommitted-summary-row mt-3">
                <div className="summary-chips">
                  {summary.rows_updated > 0 && (
                    <span className="diff-chip updated">~{summary.rows_updated} rows updated</span>
                  )}
                  {summary.rows_inserted > 0 && (
                    <span className="diff-chip inserted">+{summary.rows_inserted} rows inserted</span>
                  )}
                  {summary.rows_deleted > 0 && (
                    <span className="diff-chip deleted">-{summary.rows_deleted} rows deleted</span>
                  )}
                  {summary.tables_altered > 0 && (
                    <span className="diff-chip altered">~{summary.tables_altered} tables altered</span>
                  )}
                  {summary.tables_added > 0 && (
                    <span className="diff-chip inserted">+{summary.tables_added} tables added</span>
                  )}
                </div>

                <div className="uncommitted-actions">
                  <button className="btn btn-secondary btn-sm" onClick={handleReviewInDiff}>
                    <span>View Diff</span>
                    <ArrowRight size={13} />
                  </button>
                  <button className="btn btn-primary btn-sm" onClick={handleCommitLiveChanges}>
                    <Camera size={13} />
                    <span>Commit Changes</span>
                  </button>
                </div>
              </div>
            ) : (
              <p className="text-secondary text-xs mt-2">
                The PostgreSQL database matches the HEAD commit. Trigger a scenario below to see DataGit detect modifications live!
              </p>
            )}
          </div>

          {/* Preset Demo Scenarios */}
          <div className="demo-scenarios-section mt-4">
            <h4 className="section-subtitle">1-Click Live Scenarios (E-commerce):</h4>

            <div className="scenarios-grid">
              {/* Scenario 1: Flash Sale */}
              <div className="scenario-card">
                <div className="scenario-card-top">
                  <div className="scenario-icon sale">
                    <Tag size={16} />
                  </div>
                  <div className="scenario-text">
                    <div className="scenario-title">Flash Sale (25% Off Electronics)</div>
                    <div className="scenario-desc">
                      Slashes prices by 25% on electronics products and appends 'flash-sale-25' tag.
                    </div>
                  </div>
                </div>
                <button
                  className="btn btn-secondary btn-sm scenario-run-btn"
                  disabled={isRunning}
                  onClick={() => handleRunScenario('flash_sale')}
                >
                  <Play size={13} />
                  <span>Execute on DB</span>
                </button>
              </div>

              {/* Scenario 2: High Value Order */}
              <div className="scenario-card">
                <div className="scenario-card-top">
                  <div className="scenario-icon order">
                    <ShoppingBag size={16} />
                  </div>
                  <div className="scenario-text">
                    <div className="scenario-title">Customer Order ($948.99) &amp; VIP Upgrade</div>
                    <div className="scenario-desc">
                      Inserts order ORD-99001, deducts inventory, and promotes Alice Chen to Platinum.
                    </div>
                  </div>
                </div>
                <button
                  className="btn btn-secondary btn-sm scenario-run-btn"
                  disabled={isRunning}
                  onClick={() => handleRunScenario('new_order')}
                >
                  <Play size={13} />
                  <span>Execute on DB</span>
                </button>
              </div>

              {/* Scenario 3: Product Launch & Schema Evolution */}
              <div className="scenario-card">
                <div className="scenario-card-top">
                  <div className="scenario-icon launch">
                    <Rocket size={16} />
                  </div>
                  <div className="scenario-text">
                    <div className="scenario-title">Launch AR Glasses &amp; Alter Schema</div>
                    <div className="scenario-desc">
                      Adds 'warranty_months' column to products, creates 'Smart Wearables' category, and adds new product.
                    </div>
                  </div>
                </div>
                <button
                  className="btn btn-secondary btn-sm scenario-run-btn"
                  disabled={isRunning}
                  onClick={() => handleRunScenario('product_launch')}
                >
                  <Play size={13} />
                  <span>Execute on DB</span>
                </button>
              </div>

              {/* Scenario 4: Clean Reset */}
              <div className="scenario-card">
                <div className="scenario-card-top">
                  <div className="scenario-icon reset">
                    <RotateCcw size={16} />
                  </div>
                  <div className="scenario-text">
                    <div className="scenario-title">Reset to Clean HEAD</div>
                    <div className="scenario-desc">
                      Reverts all uncommitted changes back to current HEAD snapshot so you can re-run demos cleanly.
                    </div>
                  </div>
                </div>
                <button
                  className="btn btn-secondary btn-sm scenario-run-btn"
                  disabled={isRunning}
                  onClick={() => handleRunScenario('reset_clean')}
                >
                  <RotateCcw size={13} />
                  <span>Reset Database</span>
                </button>
              </div>
            </div>
          </div>

          {/* Custom SQL Playground */}
          <div className="custom-sql-section mt-4">
            <h4 className="section-subtitle">
              <Terminal size={14} className="inline mr-1 text-accent" />
              Custom SQL Manipulation (Optional):
            </h4>
            <div className="custom-sql-box">
              <textarea
                className="form-input form-textarea font-mono text-xs"
                rows={3}
                placeholder="UPDATE products SET price = 149.99 WHERE sku = 'TECH-001'; -- or any SQL"
                value={customSql}
                onChange={(e) => setCustomSql(e.target.value)}
              />
              <div className="custom-sql-actions mt-2">
                <span className="text-muted text-xs">
                  Runs directly on connected PostgreSQL database (<code>public</code> schema).
                </span>
                <button
                  className="btn btn-secondary btn-sm"
                  disabled={isRunning || !customSql.trim()}
                  onClick={() => handleRunScenario('custom_sql', customSql)}
                >
                  <Database size={13} />
                  <span>Run Custom SQL</span>
                </button>
              </div>
            </div>
          </div>

          {/* Last Executed SQL preview */}
          {lastExecutedSql && (
            <div className="executed-sql-preview mt-3">
              <div className="preview-label">Last Executed SQL:</div>
              <pre className="font-mono text-xs m-0">{lastExecutedSql}</pre>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="modal-footer">
          <div className="text-secondary text-xs">
            Tip: You can also run <code>npm run demo:live</code> in your terminal while the audience watches this UI!
          </div>
          <button className="btn btn-secondary btn-md" onClick={() => setIsDemoModalOpen(false)}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
