import React, { useState } from 'react';
import { RotateCcw, AlertTriangle } from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { apiRequest } from '../../services/api';

export const RollbackTab: React.FC = () => {
  const { settings, setActiveTab, refreshState, addToast } = useApp();

  const [mode, setMode] = useState<'previous' | 'specific'>('previous');
  const [targetCommitId, setTargetCommitId] = useState('');
  const [author, setAuthor] = useState(settings.author || 'DataGit Engineer');
  const [allowDirty, setAllowDirty] = useState(settings.defaultAllowDirty);
  const [isRollingBack, setIsRollingBack] = useState(false);

  const handleRollback = async (e: React.FormEvent) => {
    e.preventDefault();

    const payload: {
      author: string;
      allow_dirty: boolean;
      commit_id?: number;
    } = {
      author: author.trim(),
      allow_dirty: allowDirty,
    };

    if (mode === 'specific') {
      const cId = parseInt(targetCommitId.trim(), 10);
      if (isNaN(cId)) {
        addToast('Please enter a target commit ID to rollback to', 'warning');
        return;
      }
      payload.commit_id = cId;
    }

    const confirmMsg =
      mode === 'specific'
        ? `Are you sure you want to rollback to Commit #${payload.commit_id}? All subsequent database tables and rows will be replaced transactionally!`
        : `Are you sure you want to rollback to the previous commit?`;

    if (!window.confirm(confirmMsg)) return;

    setIsRollingBack(true);
    try {
      const res = await apiRequest<{ rollback_commit_id: number }>('/rollback', {
        method: 'POST',
        body: payload,
      }, settings);

      addToast(`Rollback complete! New audit commit #${res.rollback_commit_id} created.`, 'success');
      await refreshState();
      setActiveTab('history');
    } catch (err: unknown) {
      const msg = (err as Error).message || 'Rollback failed';
      addToast(msg, 'error');
    } finally {
      setIsRollingBack(false);
    }
  };

  return (
    <section className="tab-content">
      <div className="view-header">
        <div>
          <h2>Time Travel &amp; Database Rollback</h2>
          <p className="text-secondary">
            Atomically restore your live database to any historical snapshot state with transactional exact object replacement.
          </p>
        </div>
      </div>

      <div className="card-grid two-column">
        <div className="card">
          <h3 className="card-title">Rollback Configuration</h3>
          <form className="form-layout" onSubmit={handleRollback}>
            <div className="form-group">
              <label className="form-label">Target Mode:</label>
              <div className="segmented-control">
                <label className="segment-label">
                  <input
                    type="radio"
                    name="rmode"
                    value="previous"
                    checked={mode === 'previous'}
                    onChange={() => setMode('previous')}
                  />
                  <span>Revert to Previous (HEAD~1)</span>
                </label>
                <label className="segment-label">
                  <input
                    type="radio"
                    name="rmode"
                    value="specific"
                    checked={mode === 'specific'}
                    onChange={() => setMode('specific')}
                  />
                  <span>Revert to Specific Commit</span>
                </label>
              </div>
            </div>

            {mode === 'specific' && (
              <div className="form-group">
                <label className="form-label">
                  Target Commit ID <span className="required">*</span>
                </label>
                <input
                  type="number"
                  className="form-input"
                  placeholder="e.g. 1"
                  value={targetCommitId}
                  onChange={(e) => setTargetCommitId(e.target.value)}
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

            <div className="form-group checkbox-group">
              <input
                type="checkbox"
                id="rollbackDirty"
                className="form-checkbox"
                checked={allowDirty}
                onChange={(e) => setAllowDirty(e.target.checked)}
              />
              <label htmlFor="rollbackDirty" className="checkbox-label">
                <strong>Allow dirty workspace (<code>allow_dirty=true</code>)</strong>
                <span className="text-muted block text-xs">
                  Bypasses uncommitted workspace safeguards if <code>DATAGIT_PROTECT_UNCOMMITTED</code> is enabled.
                </span>
              </label>
            </div>

            <div className="form-actions">
              <button
                type="submit"
                className="btn btn-danger btn-lg"
                disabled={isRollingBack}
              >
                <RotateCcw size={18} />
                <span>{isRollingBack ? 'Restoring Database...' : 'Perform Exact Rollback'}</span>
              </button>
            </div>
          </form>
        </div>

        <div className="card card-danger">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <AlertTriangle size={20} color="#f87171" />
            <h3 className="card-title text-danger" style={{ margin: 0 }}>Exact Restoration Guarantee</h3>
          </div>
          <p className="mt-4" style={{ fontSize: '0.875rem' }}>
            DataGit rollback applies <strong>exact restoration</strong>:
          </p>
          <ul className="danger-checklist mt-2">
            <li>All application views, standalone sequences, and base tables in <code>public</code> are restored to match the selected snapshot.</li>
            <li>Tables or columns created <em>after</em> the target snapshot will be transactionally dropped.</li>
            <li>DataGit version metadata tables are always preserved.</li>
            <li>Rollback records a new rollback audit commit for full traceability.</li>
          </ul>
        </div>
      </div>
    </section>
  );
};
