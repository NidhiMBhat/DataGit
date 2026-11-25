import React from 'react';
import { Database, GitBranch, RefreshCw, Settings, ShieldAlert } from 'lucide-react';
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
          {/* Active Branch Pill */}
          <div className="header-badge-pill" title="Active Working Branch">
            <GitBranch size={13} className="text-accent" />
            <span className="badge-text">{activeBranch || 'Detached'}</span>
          </div>

          {/* Live Backend Connection Pill */}
          <div className="header-badge-pill" title={isOnline ? "Backend Live (Port 8000)" : "Backend Disconnected"}>
            <span className={`badge-dot ${isOnline ? 'online' : 'offline'}`} />
            <span className="badge-text font-mono">{isOnline ? 'Online' : 'Offline'}</span>
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
