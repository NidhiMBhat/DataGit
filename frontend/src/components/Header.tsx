import React from 'react';
import {
  Database,
  GitBranch,
  RefreshCw,
  Settings,
  ShieldAlert,
  Zap,
  ArrowRight,
  Camera
} from 'lucide-react';
import { useApp, TabType } from '../context/AppContext';

export const Header: React.FC = () => {
  const {
    activeTab,
    setActiveTab,
    activeBranch,
    currentHead,
    isOnline,
    safeguardsActive,
    safeguardsMessage,
    setIsSettingsOpen,
    refreshState,
    addToast,
    settings,
    isWorkspaceDirty,
    workspaceStatus,
    setIsDemoModalOpen,
  } = useApp();

  const navItems: { id: TabType; label: string }[] = [
    { id: 'history', label: 'Timeline' },
    { id: 'schema', label: 'Schema' },
    { id: 'snapshot', label: 'Snapshot' },
    { id: 'branches', label: 'Branches' },
    { id: 'diff', label: 'Diff' },
    { id: 'merge', label: 'Merge' },
    { id: 'benchmark', label: 'Benchmark' },
    { id: 'rollback', label: 'Rollback' },
  ];

  const handleRefresh = async () => {
    addToast('Refreshing repository state...', 'info');
    await refreshState();
  };

  const getInitials = (name: string) => {
    if (!name) return 'DG';
    const parts = name.split(' ');
    if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
    return name.substring(0, 2).toUpperCase();
  };

  return (
    <>
      <header className="app-top-header">
        {/* Left: Brand */}
        <div className="header-brand-group">
          <div className="brand-box-icon">
            <Database size={18} />
          </div>
          <div className="brand-text">
            <span className="brand-name">datagit</span>
            <span className="brand-tag">v-control</span>
          </div>
        </div>

        {/* Center: Sleek Horizontal Pill Nav matching reference design */}
        <nav className="header-pill-nav">
          {navItems.map((item) => (
            <button
              key={item.id}
              className={`pill-nav-item ${activeTab === item.id ? 'active' : ''}`}
              onClick={() => setActiveTab(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>

        {/* Right: Status Pills & Action Icons */}
        <div className="header-actions-group">
          {/* Live Demo Playground Trigger Button */}
          <button
            onClick={() => setIsDemoModalOpen(true)}
            className="header-demo-btn"
            title="Open Live Database Playground (Simulate PostgreSQL Changes)"
          >
            <Zap size={14} className="text-amber-400" />
            <span>Live Demo</span>
          </button>

          {/* Active Branch Pill */}
          <div className="header-badge-pill" title="Active Working Branch">
            <GitBranch size={13} className="text-accent" />
            <span className="badge-text">{activeBranch || 'Detached'}</span>
          </div>

          {/* Working Workspace Status Pill */}
          <div
            className={`header-badge-pill cursor-pointer ${isWorkspaceDirty ? 'dirty-pill' : ''}`}
            title={
              isWorkspaceDirty
                ? 'Uncommitted changes detected in PostgreSQL - click to inspect'
                : 'Workspace in sync with HEAD'
            }
            onClick={() => setIsDemoModalOpen(true)}
          >
            <span className={`badge-dot ${isWorkspaceDirty ? 'dirty' : 'clean'}`} />
            <span className={`badge-text font-mono ${isWorkspaceDirty ? 'text-amber-400 font-bold' : ''}`}>
              {isWorkspaceDirty ? 'Dirty DB' : 'Clean'}
            </span>
          </div>

          {/* Live Backend Connection Pill */}
          <div className="header-badge-pill" title={isOnline ? "Backend Live (Port 8000)" : "Backend Disconnected"}>
            <span className={`badge-dot ${isOnline ? 'online' : 'offline'}`} />
            <span className="badge-text font-mono">{isOnline ? 'Live' : 'Offline'}</span>
          </div>

          {/* HEAD Commit Pill */}
          <div className="header-badge-pill" title="Current HEAD Commit">
            <span className="badge-text font-mono">
              {currentHead !== null ? `HEAD #${currentHead}` : 'No HEAD'}
            </span>
          </div>

          {/* Circular Utility Action Buttons */}
          <button
            onClick={handleRefresh}
            className="circular-icon-btn"
            title="Refresh repository status"
          >
            <RefreshCw size={15} />
          </button>

          <button
            onClick={() => setIsSettingsOpen(true)}
            className="circular-icon-btn"
            title="Configure Auth API Keys & Safeguards"
          >
            <Settings size={15} />
          </button>

          {/* User Avatar Circle */}
          <div
            className="user-avatar-circle"
            title={`Active Author: ${settings.author}`}
            onClick={() => setIsSettingsOpen(true)}
          >
            {getInitials(settings.author)}
          </div>
        </div>
      </header>

      {/* Uncommitted Live Changes Banner */}
      {isWorkspaceDirty && (
        <div className="uncommitted-live-banner">
          <div className="banner-content">
            <div className="banner-left">
              <Zap size={16} className="text-amber-400 inline mr-2" />
              <strong>Live PostgreSQL Changes Detected:</strong>{' '}
              <span>
                {workspaceStatus?.summary?.rows_updated ? `~${workspaceStatus.summary.rows_updated} rows updated ` : ''}
                {workspaceStatus?.summary?.rows_inserted ? `+${workspaceStatus.summary.rows_inserted} rows inserted ` : ''}
                {workspaceStatus?.summary?.rows_deleted ? `-${workspaceStatus.summary.rows_deleted} rows deleted ` : ''}
                {workspaceStatus?.summary?.tables_altered ? `~${workspaceStatus.summary.tables_altered} tables altered ` : ''}
                {workspaceStatus?.summary?.tables_added ? `+${workspaceStatus.summary.tables_added} tables added ` : ''}
              </span>
            </div>
            <div className="banner-actions">
              <button
                className="banner-action-btn secondary"
                onClick={() => setActiveTab('diff')}
              >
                <span>Inspect in Diff</span>
                <ArrowRight size={13} />
              </button>
              <button
                className="banner-action-btn primary"
                onClick={() => setActiveTab('snapshot')}
              >
                <Camera size={13} />
                <span>Commit Now</span>
              </button>
              <button
                className="banner-action-btn icon"
                onClick={() => setIsDemoModalOpen(true)}
                title="Open Live Playground"
              >
                <Zap size={13} />
              </button>
            </div>
          </div>
        </div>
      )}

      {safeguardsActive && (
        <div className="safeguards-banner">
          <div className="banner-content">
            <ShieldAlert size={16} />
            <span>{safeguardsMessage}</span>
          </div>
        </div>
      )}
    </>
  );
};
