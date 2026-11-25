import React, { useState } from 'react';
import { GitBranch, Plus, Check, ArrowRightLeft, X } from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { apiRequest } from '../../services/api';

export const BranchesTab: React.FC = () => {
  const {
    branches,
    currentHead,
    settings,
    setActiveTab,
    setDiffPair,
    refreshState,
    addToast,
  } = useApp();

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newBranchName, setNewBranchName] = useState('');
  const [fromCommitId, setFromCommitId] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [switchingBranch, setSwitchingBranch] = useState<string | null>(null);

  const handleCreateBranch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newBranchName.trim()) {
      addToast('Branch name is required', 'warning');
      return;
    }

    setIsCreating(true);
    try {
      const payload: { name: string; from_commit_id?: number } = {
        name: newBranchName.trim(),
      };
      if (fromCommitId.trim()) {
        payload.from_commit_id = parseInt(fromCommitId.trim(), 10);
      }

      await apiRequest('/branches', {
        method: 'POST',
        body: payload,
      }, settings);

      addToast(`Branch "${newBranchName.trim()}" created successfully`, 'success');
      setNewBranchName('');
      setFromCommitId('');
      setIsModalOpen(false);
      await refreshState();
    } catch (err: unknown) {
      const msg = (err as Error).message || 'Failed to create branch';
      addToast(msg, 'error');
    } finally {
      setIsCreating(false);
    }
  };

  const handleCheckoutBranch = async (branchName: string) => {
    setSwitchingBranch(branchName);
    try {
      const allowDirty = settings.defaultAllowDirty;
      const endpoint = `/checkout/branches/${encodeURIComponent(branchName)}${
        allowDirty ? '?allow_dirty=true' : ''
      }`;

      await apiRequest(endpoint, { method: 'POST' }, settings);
      addToast(`Switched to branch "${branchName}"! Database state restored.`, 'success');
      await refreshState();
    } catch (err: unknown) {
      const msg = (err as Error).message || 'Failed to checkout branch';
      addToast(msg, 'error');
    } finally {
      setSwitchingBranch(null);
    }
  };

  const handleCompareBranch = (headId: number | null) => {
    if (headId === null || currentHead === null) {
      addToast('Cannot compare: active or target branch has no head commit', 'warning');
      return;
    }
    setDiffPair({ from: currentHead, to: headId });
    setActiveTab('diff');
  };

  return (
    <section className="tab-content">
      <div className="view-header">
        <div>
          <h2>Branch Management</h2>
          <p className="text-secondary">
            Create isolated branches, track branch heads, and switch working database versions.
          </p>
        </div>
        <div>
          <button className="btn btn-primary" onClick={() => setIsModalOpen(true)}>
            <Plus size={16} />
            <span>Create New Branch</span>
          </button>
        </div>
      </div>

      <div className="branches-grid">
        {branches.map((b) => {
          const headId = b.head_commit ?? b.head_commit_id ?? null;
          return (
            <div key={b.name} className={`branch-card ${b.is_current ? 'active' : ''}`}>
              <div className="branch-top">
                <div className="branch-name">
                  <GitBranch size={18} className="text-blue-400" />
                  <span>{b.name}</span>
                </div>
                {b.is_current && <span className="tag-badge head">ACTIVE BRANCH</span>}
              </div>

              <div>
                <div className="text-muted text-xs">HEAD COMMIT:</div>
                <div className="font-mono" style={{ fontSize: '1.1rem', color: '#38bdf8', fontWeight: 600 }}>
                  {headId !== null ? `#${headId}` : 'None'}
                </div>
              </div>

              <div className="branch-actions">
                {b.is_current ? (
                  <button className="btn btn-secondary btn-sm" disabled>
                    <Check size={14} />
                    <span>Current Branch</span>
                  </button>
                ) : (
                  <button
                    className="btn btn-primary btn-sm"
                    disabled={switchingBranch === b.name}
                    onClick={() => handleCheckoutBranch(b.name)}
                  >
                    <ArrowRightLeft size={14} />
                    <span>{switchingBranch === b.name ? 'Restoring DB...' : 'Switch Branch'}</span>
                  </button>
                )}

                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => handleCompareBranch(headId)}
                  disabled={headId === null || headId === currentHead}
                  title="Compare with current HEAD"
                >
                  <span>Compare</span>
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {isModalOpen && (
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="modal-header">
              <h3>Create New Branch</h3>
              <button className="modal-close" onClick={() => setIsModalOpen(false)}>
                <X size={20} />
              </button>
            </div>
            <form className="modal-body form-layout" onSubmit={handleCreateBranch}>
              <div className="form-group">
                <label className="form-label">
                  Branch Name <span className="required">*</span>
                </label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. feature/users, migration/v2"
                  value={newBranchName}
                  onChange={(e) => setNewBranchName(e.target.value)}
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">
                  From Commit ID <span className="text-muted">(Optional, defaults to active HEAD)</span>
                </label>
                <input
                  type="number"
                  className="form-input"
                  placeholder="Leave empty for current HEAD"
                  value={fromCommitId}
                  onChange={(e) => setFromCommitId(e.target.value)}
                />
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setIsModalOpen(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={isCreating}>
                  {isCreating ? 'Creating...' : 'Create Branch'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
};
