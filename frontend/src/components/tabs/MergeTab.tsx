import React, { useState } from 'react';
import { GitMerge, AlertOctagon, CheckCircle2 } from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { apiRequest } from '../../services/api';
import { MergeResponse } from '../../types/api';

export const MergeTab: React.FC = () => {
  const { branches, activeBranch, currentHead, settings, refreshState, addToast } = useApp();

  const [sourceMode, setSourceMode] = useState<'branch' | 'commit'>('branch');
  const [sourceBranch, setSourceBranch] = useState('');
  const [sourceCommitId, setSourceCommitId] = useState('');
  const [author, setAuthor] = useState(settings.author || 'DataGit Engineer');
  const [message, setMessage] = useState('');
  const [isMerging, setIsMerging] = useState(false);
  const [mergeResult, setMergeResult] = useState<{ success?: boolean; commitId?: number; conflict?: unknown } | null>(null);

  const availableBranches = branches.filter((b) => !b.is_current);

  const handleMerge = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeBranch) {
      addToast('Cannot merge in detached HEAD mode. Please checkout a target branch first.', 'warning');
      return;
    }

    const payload: {
      source_branch?: string;
      source_commit_id?: number;
      author: string;
      message?: string;
    } = { author: author.trim() };

    if (sourceMode === 'branch') {
      if (!sourceBranch) {
        addToast('Please select a source branch to merge', 'warning');
        return;
      }
      payload.source_branch = sourceBranch;
    } else {
      const commitNum = parseInt(sourceCommitId.trim(), 10);
      if (isNaN(commitNum)) {
        addToast('Please enter a valid source commit ID', 'warning');
        return;
      }
      payload.source_commit_id = commitNum;
    }

    if (message.trim()) {
      payload.message = message.trim();
    }

    setIsMerging(true);
    setMergeResult(null);

    try {
      const res = await apiRequest<MergeResponse>('/merge', {
        method: 'POST',
        body: payload,
      }, settings);

      setMergeResult({ success: true, commitId: res.merge_commit_id });
      addToast(`3-Way merge completed! Created commit #${res.merge_commit_id}`, 'success');
      await refreshState();
    } catch (err: unknown) {
      const apiErr = err as { status?: number; data?: { detail?: unknown }; message?: string };
      if (apiErr.status === 409) {
        setMergeResult({ success: false, conflict: apiErr.data?.detail || apiErr.message });
        addToast('Merge conflict detected! Transaction safely rolled back.', 'warning', 6000);
      } else {
        const msg = apiErr.message || 'Merge failed';
        addToast(msg, 'error');
      }
    } finally {
      setIsMerging(false);
    }
  };

  return (
    <section className="tab-content">
      <div className="view-header">
        <div>
          <h2>3-Way Database Merge &amp; Conflict Resolution</h2>
          <p className="text-secondary">
            Combine schema and data evolutions using 3-way common ancestor resolution with transactional rollback guarantees.
          </p>
        </div>
      </div>

      <div className="card-grid two-column">
        <div className="card">
          <h3 className="card-title">Execute Merge</h3>
          <form className="form-layout" onSubmit={handleMerge}>
            <div className="form-group">
              <label className="form-label">Target Branch (Current Workspace):</label>
              <div className="active-merge-target font-mono">
                {activeBranch ? `${activeBranch} (HEAD: #${currentHead ?? 'none'})` : 'Detached HEAD (Select a branch)'}
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Merge Source Mode:</label>
              <div className="segmented-control">
                <label className="segment-label">
                  <input
                    type="radio"
                    name="mode"
                    value="branch"
                    checked={sourceMode === 'branch'}
                    onChange={() => setSourceMode('branch')}
                  />
                  <span>From Branch</span>
                </label>
                <label className="segment-label">
                  <input
                    type="radio"
                    name="mode"
                    value="commit"
                    checked={sourceMode === 'commit'}
                    onChange={() => setSourceMode('commit')}
                  />
                  <span>From Specific Commit</span>
                </label>
              </div>
            </div>

            {sourceMode === 'branch' ? (
              <div className="form-group">
                <label className="form-label">
                  Source Branch <span className="required">*</span>
                </label>
                <select
                  className="form-select"
                  value={sourceBranch}
                  onChange={(e) => setSourceBranch(e.target.value)}
                  required
                >
                  <option value="">Select branch to merge into {activeBranch}...</option>
                  {availableBranches.map((b) => (
                    <option key={b.name} value={b.name}>
                      {b.name} (HEAD: #{b.head_commit_id ?? b.head_commit ?? 'none'})
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <div className="form-group">
                <label className="form-label">
                  Source Commit ID <span className="required">*</span>
                </label>
                <input
                  type="number"
                  className="form-input"
                  placeholder="e.g. 4"
                  value={sourceCommitId}
                  onChange={(e) => setSourceCommitId(e.target.value)}
                  required
                />
              </div>
            )}

            <div className="form-group">
              <label className="form-label">Author:</label>
              <input
                type="text"
                className="form-input"
                value={author}
                onChange={(e) => setAuthor(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">
                Custom Commit Message <span className="text-muted">(Optional)</span>:
              </label>
              <input
                type="text"
                className="form-input"
                placeholder="Defaults to: Merge branch '...' into ..."
                value={message}
                onChange={(e) => setMessage(e.target.value)}
              />
            </div>

            <div className="form-actions">
              <button
                type="submit"
                className="btn btn-primary btn-lg"
                disabled={isMerging || !activeBranch}
              >
                <GitMerge size={18} />
                <span>{isMerging ? 'Merging Transactions...' : 'Execute 3-Way Merge'}</span>
              </button>
            </div>
          </form>
        </div>

        <div className="card">
          <h3 className="card-title">How DataGit Merging Works</h3>
          <div className="merge-info-list">
            <div className="info-item">
              <div className="info-icon">🌿</div>
              <div>
                <strong>Common Ancestor:</strong> DataGit identifies the closest common ancestor snapshot and computes 3-way diffs between base, active, and source.
              </div>
            </div>
            <div className="info-item">
              <div className="info-icon">⚡</div>
              <div>
                <strong>Atomic Transaction:</strong> Disjoint row and schema changes are combined and committed to PostgreSQL in a single transactional write.
              </div>
            </div>
            <div className="info-item">
              <div className="info-icon">🛡️</div>
              <div>
                <strong>Safe Conflict Detection:</strong> Concurrent edits to the exact same column/row or foreign-key violations abort with HTTP 409 without mutating your database.
              </div>
            </div>
          </div>
        </div>
      </div>

      {mergeResult && (
        <div className="mt-6">
          {mergeResult.success ? (
            <div className="callout callout-info" style={{ background: 'rgba(16, 185, 129, 0.15)', borderColor: '#10b981', color: '#34d399' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '1.1rem', fontWeight: 600 }}>
                <CheckCircle2 size={20} />
                <span>Merge Succeeded! Two-parent commit #{mergeResult.commitId} created.</span>
              </div>
              <p className="mt-2 text-sm">
                Active PostgreSQL branch {activeBranch} is now updated with all combined changes.
              </p>
            </div>
          ) : (
            <div className="conflict-card">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <AlertOctagon size={20} color="#f87171" />
                <h4>Merge Conflict Refusal (HTTP 409)</h4>
              </div>
              <p style={{ color: '#cbd5e1', margin: '8px 0 16px 0', fontSize: '0.9rem' }}>
                Automated 3-way merge was aborted to prevent data corruption. The PostgreSQL transaction was completely rolled back.
              </p>
              <div className="code-container">
                <pre>{JSON.stringify(mergeResult.conflict, null, 2)}</pre>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
};
