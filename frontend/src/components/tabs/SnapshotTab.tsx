import React, { useState, useEffect } from 'react';
import { Camera, Database, CheckCircle2, AlertTriangle } from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { apiRequest } from '../../services/api';

export const SnapshotTab: React.FC = () => {
  const {
    settings,
    updateSettings,
    setActiveTab,
    refreshState,
    addToast,
    isWorkspaceDirty,
    workspaceStatus,
    suggestedCommitMessage,
    setSuggestedCommitMessage,
  } = useApp();

  const [author, setAuthor] = useState(settings.author || 'DataGit Engineer');
  const [message, setMessage] = useState(suggestedCommitMessage || '');
  const [parentCommitId, setParentCommitId] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (suggestedCommitMessage) {
      setMessage(suggestedCommitMessage);
    }
  }, [suggestedCommitMessage]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!author.trim() || !message.trim()) {
      addToast('Author and commit message are required', 'warning');
      return;
    }

    setIsSubmitting(true);
    try {
      const payload: { author: string; message: string; parent_commit_id?: number } = {
        author: author.trim(),
        message: message.trim(),
      };
      if (parentCommitId.trim()) {
        payload.parent_commit_id = parseInt(parentCommitId.trim(), 10);
      }

      const res = await apiRequest<{ commit_id: number }>('/commits', {
        method: 'POST',
        body: payload,
      }, settings);

      updateSettings({ author: author.trim() });
      addToast(`Snapshot commit #${res.commit_id} created successfully!`, 'success');
      setMessage('');
      setSuggestedCommitMessage('');
      setParentCommitId('');
      await refreshState();
      setActiveTab('history');
    } catch (err: unknown) {
      const msg = (err as Error).message || 'Failed to create snapshot commit';
      addToast(msg, 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="tab-content">
      <div className="view-header">
        <div>
          <h2>Create Snapshot Commit</h2>
          <p className="text-secondary">
            Capture a transactionally consistent, content-addressed snapshot of all PostgreSQL public objects.
          </p>
        </div>
      </div>

      <div className="card-grid two-column">
        <div className="card">
          <h3 className="card-title">New Snapshot</h3>
          <form className="form-layout" onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">
                Author <span className="required">*</span>
              </label>
              <input
                type="text"
                className="form-input"
                placeholder="Developer name or team"
                value={author}
                onChange={(e) => setAuthor(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">
                Commit Message <span className="required">*</span>
              </label>
              <textarea
                className="form-textarea"
                rows={4}
                placeholder="Describe schema or data changes..."
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">
                Parent Commit ID <span className="text-muted">(Optional, defaults to active HEAD)</span>
              </label>
              <input
                type="number"
                className="form-input"
                placeholder="Leave blank for active HEAD"
                value={parentCommitId}
                onChange={(e) => setParentCommitId(e.target.value)}
              />
            </div>

            <div className="form-actions">
              <button type="submit" className="btn btn-primary btn-lg" disabled={isSubmitting}>
                <Camera size={18} />
                <span>{isSubmitting ? 'Recording Snapshot...' : 'Record Snapshot & Commit'}</span>
              </button>
            </div>
          </form>
        </div>

        <div className="card card-accent">
          {/* Live Working Tree Status */}
          <div className={`demo-status-card mb-4 ${isWorkspaceDirty ? 'dirty' : 'clean'}`}>
            <div className="status-header-row">
              <div className="status-indicator-group">
                {isWorkspaceDirty ? (
                  <AlertTriangle size={16} className="text-amber-400" />
                ) : (
                  <CheckCircle2 size={16} className="text-emerald-400" />
                )}
                <span className="status-title">
                  {isWorkspaceDirty
                    ? 'Uncommitted Changes Ready to Snapshot'
                    : 'Working Database Matches Current HEAD'}
                </span>
              </div>
            </div>
            {isWorkspaceDirty && workspaceStatus?.summary && (
              <div className="summary-chips mt-2">
                {workspaceStatus.summary.rows_updated > 0 && (
                  <span className="diff-chip updated">~{workspaceStatus.summary.rows_updated} rows updated</span>
                )}
                {workspaceStatus.summary.rows_inserted > 0 && (
                  <span className="diff-chip inserted">+{workspaceStatus.summary.rows_inserted} rows inserted</span>
                )}
                {workspaceStatus.summary.rows_deleted > 0 && (
                  <span className="diff-chip deleted">-{workspaceStatus.summary.rows_deleted} rows deleted</span>
                )}
                {workspaceStatus.summary.tables_altered > 0 && (
                  <span className="diff-chip altered">~{workspaceStatus.summary.tables_altered} tables altered</span>
                )}
                {workspaceStatus.summary.tables_added > 0 && (
                  <span className="diff-chip inserted">+{workspaceStatus.summary.tables_added} tables added</span>
                )}
              </div>
            )}
          </div>

          <h3 className="card-title">Scope of DataGit Snapshots</h3>
          <ul className="feature-checklist">
            <li>
              <strong>Base Tables &amp; Columns:</strong> Structure, column types, default values, and nullability.
            </li>
            <li>
              <strong>Relational Constraints:</strong> Primary keys, foreign keys, unique, and check constraints.
            </li>
            <li>
              <strong>Row Data:</strong> Content-addressed SHA-256 row payload hashing across public schema tables.
            </li>
            <li>
              <strong>Indexes &amp; Triggers:</strong> Non-constraint indexes and user trigger attachments.
            </li>
            <li>
              <strong>Views &amp; Privileges:</strong> Full SQL view definitions and table grant privileges.
            </li>
            <li>
              <strong>Standalone Sequences:</strong> Exact sequence status, current values, and called state.
            </li>
          </ul>

          <div className="callout callout-info mt-4">
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <Database size={16} />
              <span>
                DataGit internal tables (<code>_dagit_*</code>) are strictly segregated and preserved across all restorations.
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
