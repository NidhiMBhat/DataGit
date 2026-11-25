import React, { useState } from 'react';
import { GitCommit, GitBranch, ArrowRight, Copy, Check, Clock, User, Hash } from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { apiRequest } from '../../services/api';

export const HistoryTab: React.FC = () => {
  const {
    history,
    branches,
    currentHead,
    settings,
    setActiveTab,
    setDiffPair,
    refreshState,
    addToast,
  } = useApp();

  const [copiedHash, setCopiedHash] = useState<string | null>(null);
  const [selectedBranch, setSelectedBranch] = useState<string>('');
  const [loadingCheckout, setLoadingCheckout] = useState<number | null>(null);

  const handleCopyHash = (hash?: string) => {
    if (!hash) return;
    navigator.clipboard.writeText(hash);
    setCopiedHash(hash);
    addToast('SHA-256 snapshot hash copied', 'info');
    setTimeout(() => setCopiedHash(null), 2500);
  };

  const handleCheckout = async (commitId: number) => {
    setLoadingCheckout(commitId);
    try {
      const endpoint = `/checkout/commits/${commitId}${
        settings.defaultAllowDirty ? '?allow_dirty=true' : ''
      }`;
      await apiRequest(endpoint, { method: 'POST' }, settings);
      addToast(`Checked out commit #${commitId} (Detached HEAD mode)`, 'success');
      await refreshState();
    } catch (err: unknown) {
      const msg = (err as Error).message || 'Failed to checkout commit';
      addToast(msg, 'error');
    } finally {
      setLoadingCheckout(null);
    }
  };

  const handleDiffWithHead = (commitId: number) => {
    if (currentHead === null) {
      addToast('No current HEAD commit available to compare against', 'warning');
      return;
    }
    setDiffPair({ from: commitId, to: currentHead });
    setActiveTab('diff');
  };

  const handleDiffWithParent = (commitId: number, parentId: string | number) => {
    const p = String(parentId).split(',')[0].trim();
    setDiffPair({ from: parseInt(p, 10), to: commitId });
    setActiveTab('diff');
  };

  const filteredHistory = selectedBranch
    ? history.filter((c) => {
        const b = branches.find((branch) => branch.name === selectedBranch);
        const commitId = c.commit_id ?? c.id;
        return b && (b.head_commit ?? b.head_commit_id) === commitId;
      })
    : history;

  return (
    <section className="tab-content">
      <div className="view-header">
        <div>
          <h2>Commit History &amp; Lineage</h2>
          <p className="text-secondary">
            Content-addressed snapshot commits with deterministic SHA-256 integrity and branching lineage.
          </p>
        </div>
        <div className="view-controls">
          <div className="control-group">
            <label>Branch:</label>
            <select
              className="form-select form-select-sm"
              value={selectedBranch}
              onChange={(e) => setSelectedBranch(e.target.value)}
            >
              <option value="">(All reachable commits)</option>
              {branches.map((b) => (
                <option key={b.name} value={b.name}>
                  {b.name} {b.is_current ? '(active)' : ''}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {filteredHistory.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">🌱</div>
          <h3>No Commits Found</h3>
          <p className="text-secondary">Record your first PostgreSQL snapshot to start tracking versions.</p>
          <button className="btn btn-primary mt-4" onClick={() => setActiveTab('snapshot')}>
            Create Snapshot
          </button>
        </div>
      ) : (
        <div className="timeline-wrapper">
          <div className="timeline-line" />
          <div className="commit-list">
            {filteredHistory.map((commit) => {
              const commitId = (commit.commit_id ?? commit.id)!;
              const isHead = currentHead !== null && commitId === currentHead;
              const matchingBranches = branches.filter(
                (b) => (b.head_commit ?? b.head_commit_id) === commitId
              );

              const parents = commit.parents && commit.parents.length > 0
                ? commit.parents
                : commit.parent_commit
                ? [commit.parent_commit]
                : commit.parent_commit_id
                ? String(commit.parent_commit_id).split(',').map((p) => parseInt(p.trim(), 10))
                : [];

              const isMerge = parents.length > 1;
              const snapshotHash = commit.state_id ?? commit.snapshot_hash;
              const timestampStr = commit.timestamp ?? commit.created_at;

              return (
                <div key={commitId} className={`commit-card ${isHead ? 'is-head' : ''}`}>
                  <div className="commit-header">
                    <div className="commit-title-row">
                      <span className="commit-id-badge">#{commitId}</span>
                      <span className="commit-message">{commit.message}</span>
                    </div>
                    <div className="commit-tags">
                      {isHead && <span className="tag-badge head">HEAD</span>}
                      {matchingBranches.map((b) => (
                        <span key={b.name} className="tag-badge branch">
                          🌿 {b.name}
                        </span>
                      ))}
                      {isMerge && <span className="tag-badge merge">3-Way Merge</span>}
                    </div>
                  </div>

                  <div className="commit-meta">
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                      <User size={14} />
                      <strong>{commit.author}</strong>
                    </span>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                      <Clock size={14} />
                      {timestampStr ? new Date(timestampStr).toLocaleString() : 'Recorded'}
                    </span>
                    {parents.length > 0 ? (
                      <span>
                        🔗 {parents.length > 1 ? 'Parents' : 'Parent'}:{' '}
                        {parents.map((p) => `#${p}`).join(', ')}
                      </span>
                    ) : (
                      <span>🌱 Initial Root</span>
                    )}

                    {snapshotHash && (
                      <button
                        className="commit-hash-btn"
                        onClick={() => handleCopyHash(snapshotHash)}
                        title="Click to copy SHA-256 hash"
                      >
                        <Hash size={12} style={{ display: 'inline' }} />
                        <span>{snapshotHash.substring(0, 8)}...</span>
                        {copiedHash === snapshotHash ? (
                          <Check size={12} className="text-emerald-400" />
                        ) : (
                          <Copy size={12} />
                        )}
                      </button>
                    )}
                  </div>

                  <div className="commit-actions">
                    {currentHead !== null && commitId !== currentHead && (
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => handleDiffWithHead(commitId)}
                      >
                        <span>Compare with HEAD</span>
                        <ArrowRight size={13} />
                      </button>
                    )}

                    {parents.length > 0 && (
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => handleDiffWithParent(commitId, parents[0])}
                      >
                        <span>Diff vs Parent (#{parents[0]})</span>
                      </button>
                    )}

                    <button
                      className="btn btn-secondary btn-sm"
                      disabled={loadingCheckout === commitId}
                      onClick={() => handleCheckout(commitId)}
                    >
                      <GitCommit size={14} />
                      <span>
                        {loadingCheckout === commitId ? 'Checking out...' : 'Checkout (Detached)'}
                      </span>
                    </button>

                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => {
                        setActiveTab('branches');
                      }}
                    >
                      <GitBranch size={14} />
                      <span>Branch from Here</span>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
};
