import React, { useState } from 'react';
import { Gauge } from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { apiRequest } from '../../services/api';
import { StorageBenchmarkResult, StrategyMeasurement, RecommendationInfo } from '../../types/api';

export const BenchmarkTab: React.FC = () => {
  const { settings, addToast } = useApp();

  const [mode, setMode] = useState<'synthetic' | 'existing'>('synthetic');
  const [tableCount, setTableCount] = useState(3);
  const [rowsPerTable, setRowsPerTable] = useState(50);
  const [snapshotCount, setSnapshotCount] = useState(8);
  const [changeRatio, setChangeRatio] = useState(0.15);
  const [commitIdsStr, setCommitIdsStr] = useState('');
  const [iterations, setIterations] = useState(3);
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<StorageBenchmarkResult | null>(null);

  const handleRun = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setResult(null);

    try {
      const payload: {
        iterations: number;
        synthetic_workload?: {
          table_count: number;
          rows_per_table: number;
          snapshot_count: number;
          change_ratio: number;
        };
        commit_ids?: number[];
      } = { iterations };

      if (mode === 'synthetic') {
        payload.synthetic_workload = {
          table_count: tableCount,
          rows_per_table: rowsPerTable,
          snapshot_count: snapshotCount,
          change_ratio: changeRatio,
        };
      } else {
        const ids = commitIdsStr
          .split(',')
          .map((s) => parseInt(s.trim(), 10))
          .filter((n) => !isNaN(n));
        if (ids.length === 0) {
          addToast('Please enter at least one valid commit ID', 'warning');
          setIsLoading(false);
          return;
        }
        payload.commit_ids = ids;
      }

      const data = await apiRequest<StorageBenchmarkResult>('/storage/benchmark', {
        method: 'POST',
        body: payload,
      }, settings);

      setResult(data);
      addToast('Storage benchmark completed successfully!', 'success');
    } catch (err: unknown) {
      const msg = (err as Error).message || 'Benchmark failed';
      addToast(msg, 'error');
    } finally {
      setIsLoading(false);
    }
  };

  const measurements = result?.measurements || result?.strategies || {};
  const snapshotData: StrategyMeasurement = measurements.full_snapshot || measurements.snapshot || {};
  const deltaData: StrategyMeasurement = measurements.delta || {};
  const sharedData: StrategyMeasurement = measurements.shared_tables || measurements.shared_table || measurements.shared || {};

  const snapBytes = snapshotData.payload_bytes || snapshotData.size_bytes || 0;
  const deltaBytes = deltaData.payload_bytes || deltaData.size_bytes || 0;
  const sharedBytes = sharedData.payload_bytes || sharedData.size_bytes || 0;

  const maxBytes = Math.max(snapBytes, deltaBytes, sharedBytes, 1);
  const deltaSavings =
    snapBytes > 0 ? (((snapBytes - deltaBytes) / snapBytes) * 100).toFixed(1) : '0';

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const toMs = (seconds?: number, ms?: number) => {
    if (typeof seconds === 'number') return (seconds * 1000).toFixed(2);
    if (typeof ms === 'number') return ms.toFixed(2);
    return '0.00';
  };

  // Safe recommendation extraction
  let strategyTitle = 'Evaluation complete';
  let rationaleText = 'Based on TOAST overhead, savings, and timings';

  if (result?.recommendation) {
    if (typeof result.recommendation === 'object' && result.recommendation !== null) {
      const rec = result.recommendation as RecommendationInfo;
      const strat = rec.recommended_strategy;
      if (strat === 'delta') {
        strategyTitle = 'Delta Persistence';
      } else if (strat === 'shared_tables' || strat === 'shared_table') {
        strategyTitle = 'Shared Table Storage';
      } else if (strat === 'full_snapshot' || strat === 'snapshot') {
        strategyTitle = 'Full JSONB Snapshot';
      } else if (strat) {
        strategyTitle = strat;
      }
      if (rec.rationale) {
        rationaleText = rec.rationale;
      }
    } else {
      strategyTitle = String(result.recommendation);
    }
  }

  const isVerified =
    deltaData.verified_reconstruction !== false &&
    sharedData.verified_reconstruction !== false &&
    result?.integrity_verified !== false;

  return (
    <section className="tab-content">
      <div className="view-header">
        <div>
          <h2>Storage &amp; Performance Benchmark</h2>
          <p className="text-secondary">
            Evaluate PostgreSQL JSONB full snapshots vs. deltas vs. shared tables with TOAST overhead and reconstruction timings.
          </p>
        </div>
      </div>

      <div className="card-grid two-column">
        <div className="card">
          <h3 className="card-title">Run Benchmark</h3>
          <form className="form-layout" onSubmit={handleRun}>
            <div className="form-group">
              <label className="form-label">Workload Selection:</label>
              <div className="segmented-control">
                <label className="segment-label">
                  <input
                    type="radio"
                    name="bmode"
                    value="synthetic"
                    checked={mode === 'synthetic'}
                    onChange={() => setMode('synthetic')}
                  />
                  <span>Synthetic Workload</span>
                </label>
                <label className="segment-label">
                  <input
                    type="radio"
                    name="bmode"
                    value="existing"
                    checked={mode === 'existing'}
                    onChange={() => setMode('existing')}
                  />
                  <span>Existing Commits</span>
                </label>
              </div>
            </div>

            {mode === 'synthetic' ? (
              <div>
                <div className="form-row">
                  <div className="form-group col-6">
                    <label className="form-label">Table Count (1-20):</label>
                    <input
                      type="number"
                      className="form-input"
                      value={tableCount}
                      min={1}
                      max={20}
                      onChange={(e) => setTableCount(parseInt(e.target.value, 10))}
                    />
                  </div>
                  <div className="form-group col-6">
                    <label className="form-label">Rows Per Table (1-1000):</label>
                    <input
                      type="number"
                      className="form-input"
                      value={rowsPerTable}
                      min={1}
                      max={1000}
                      onChange={(e) => setRowsPerTable(parseInt(e.target.value, 10))}
                    />
                  </div>
                </div>

                <div className="form-row mt-4">
                  <div className="form-group col-6">
                    <label className="form-label">Snapshot Count (1-100):</label>
                    <input
                      type="number"
                      className="form-input"
                      value={snapshotCount}
                      min={1}
                      max={100}
                      onChange={(e) => setSnapshotCount(parseInt(e.target.value, 10))}
                    />
                  </div>
                  <div className="form-group col-6">
                    <label className="form-label">Change Ratio (0.0 - 1.0):</label>
                    <input
                      type="number"
                      step={0.05}
                      min={0}
                      max={1}
                      className="form-input"
                      value={changeRatio}
                      onChange={(e) => setChangeRatio(parseFloat(e.target.value))}
                    />
                  </div>
                </div>
              </div>
            ) : (
              <div className="form-group">
                <label className="form-label">Commit IDs (comma separated):</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. 1, 2, 3"
                  value={commitIdsStr}
                  onChange={(e) => setCommitIdsStr(e.target.value)}
                  required
                />
              </div>
            )}

            <div className="form-group">
              <div className="slider-header">
                <label className="form-label">Iterations (Repeatability):</label>
                <span className="slider-badge">{iterations} runs</span>
              </div>
              <input
                type="range"
                className="form-range"
                min={1}
                max={10}
                value={iterations}
                onChange={(e) => setIterations(parseInt(e.target.value, 10))}
              />
            </div>

            <div className="form-actions">
              <button type="submit" className="btn btn-primary btn-lg" disabled={isLoading}>
                <Gauge size={18} />
                <span>{isLoading ? 'Benchmarking in PostgreSQL...' : 'Execute Benchmark'}</span>
              </button>
            </div>
          </form>
        </div>

        <div className="card">
          <h3 className="card-title">What is Evaluated?</h3>
          <div className="benchmark-strategy-cards">
            <div className="strategy-item">
              <span className="badge badge-snapshot">Full Snapshot</span>
              <p>Full JSONB snapshot per commit. Immediate reconstruction, highest disk payload.</p>
            </div>
            <div className="strategy-item">
              <span className="badge badge-delta">Delta Persistence</span>
              <p>Base snapshot + cumulative forward diffs. Lowest byte payload, reconstruction CPU overhead.</p>
            </div>
            <div className="strategy-item">
              <span className="badge badge-shared">Shared Table</span>
              <p>Table-level deduplication across snapshots. High compression for multi-table schemas.</p>
            </div>
          </div>
          <div className="callout callout-warning mt-4">
            <strong>Relation Overhead:</strong> Includes <code>pg_total_relation_size</code> (heap, TOAST, index) to report true disk cost.
          </div>
        </div>
      </div>

      {isLoading && (
        <div className="loading-state">
          <div className="spinner" />
          <p>Running benchmark iterations in temporary PostgreSQL tables...</p>
        </div>
      )}

      {result && !isLoading && (
        <div className="mt-6">
          <div className="benchmark-stats-grid">
            <div className="stat-box" style={{ borderColor: '#6366f1' }}>
              <div className="stat-title">Strategy Recommendation</div>
              <div className="stat-value" style={{ fontSize: '1.25rem', color: '#a5b4fc' }}>
                {strategyTitle}
              </div>
              <div className="stat-subtext">{rationaleText}</div>
            </div>

            <div className="stat-box">
              <div className="stat-title">Delta Storage Savings</div>
              <div className="stat-value" style={{ color: '#34d399' }}>
                {Number(deltaSavings) > 0 ? `${deltaSavings}%` : 'Baseline'}
              </div>
              <div className="stat-subtext">Space reduction compared to full snapshots</div>
            </div>

            <div className="stat-box">
              <div className="stat-title">Integrity Verification</div>
              <div className="stat-value" style={{ color: isVerified ? '#34d399' : '#ef4444' }}>
                {isVerified ? '✓ 100% SHA-256' : 'Mismatch'}
              </div>
              <div className="stat-subtext">Reconstructed snapshots match original hashes</div>
            </div>

            <div className="stat-box">
              <div className="stat-title">Workload Scope</div>
              <div className="stat-value">{result.snapshot_count || 'N/A'} Snapshots</div>
              <div className="stat-subtext">{result.iterations} iteration(s) in PostgreSQL</div>
            </div>
          </div>

          <div className="card">
            <h3 className="card-title">Payload Size Comparison (pg_column_size)</h3>
            <div className="benchmark-bars-container">
              <div className="metric-bar-group">
                <div className="metric-label-row">
                  <span><strong>Full JSONB Snapshot:</strong></span>
                  <span>{formatBytes(snapBytes)}</span>
                </div>
                <div className="bar-track">
                  <div className="bar-fill fill-snapshot" style={{ width: `${(snapBytes / maxBytes) * 100}%` }}>
                    {formatBytes(snapBytes)}
                  </div>
                </div>
              </div>

              <div className="metric-bar-group">
                <div className="metric-label-row">
                  <span><strong>Delta Forward Chain:</strong></span>
                  <span>{formatBytes(deltaBytes)} ({deltaSavings}% savings)</span>
                </div>
                <div className="bar-track">
                  <div className="bar-fill fill-delta" style={{ width: `${(deltaBytes / maxBytes) * 100}%` }}>
                    {formatBytes(deltaBytes)}
                  </div>
                </div>
              </div>

              <div className="metric-bar-group">
                <div className="metric-label-row">
                  <span><strong>Shared Table Storage:</strong></span>
                  <span>{formatBytes(sharedBytes)}</span>
                </div>
                <div className="bar-track">
                  <div className="bar-fill fill-shared" style={{ width: `${(sharedBytes / maxBytes) * 100}%` }}>
                    {formatBytes(sharedBytes)}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="card mt-4">
            <h3 className="card-title">Detailed Performance &amp; Relation Overhead</h3>
            <div className="diff-table-container">
              <table className="diff-table">
                <thead>
                  <tr>
                    <th>Storage Strategy</th>
                    <th>Payload Bytes</th>
                    <th>Total Relation (with TOAST &amp; Indexes)</th>
                    <th>Write Time (ms)</th>
                    <th>Scan / Read Time (ms)</th>
                    <th>Reconstruction Time (ms)</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td><span className="badge badge-snapshot">Full Snapshot</span></td>
                    <td>{formatBytes(snapBytes)}</td>
                    <td>{formatBytes(snapshotData.total_relation_bytes || 0)}</td>
                    <td>{toMs(snapshotData.write_seconds, snapshotData.write_ms)} ms</td>
                    <td>{toMs(snapshotData.read_seconds, snapshotData.read_ms)} ms</td>
                    <td>-</td>
                  </tr>
                  <tr>
                    <td><span className="badge badge-delta">Delta Persistence</span></td>
                    <td>{formatBytes(deltaBytes)}</td>
                    <td>{formatBytes(deltaData.total_relation_bytes || 0)}</td>
                    <td>{toMs(deltaData.write_seconds, deltaData.write_ms)} ms</td>
                    <td>{toMs(deltaData.read_seconds, deltaData.read_ms)} ms</td>
                    <td>{toMs(deltaData.reconstruct_seconds, deltaData.reconstruction_ms)} ms</td>
                  </tr>
                  <tr>
                    <td><span className="badge badge-shared">Shared Table</span></td>
                    <td>{formatBytes(sharedBytes)}</td>
                    <td>{formatBytes(sharedData.total_relation_bytes || 0)}</td>
                    <td>{toMs(sharedData.write_seconds, sharedData.write_ms)} ms</td>
                    <td>{toMs(sharedData.read_seconds, sharedData.read_ms)} ms</td>
                    <td>{toMs(sharedData.reconstruct_seconds, sharedData.reconstruction_ms)} ms</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </section>
  );
};
