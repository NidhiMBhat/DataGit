import React from 'react';
import {
  History,
  Camera,
  GitBranch,
  GitCompare,
  GitMerge,
  Gauge,
  RotateCcw,
  Sun,
  Moon,
  Settings,
  Database
} from 'lucide-react';
import { useApp, TabType } from '../context/AppContext';

export const Sidebar: React.FC = () => {
  const { activeTab, setActiveTab, theme, toggleTheme, setIsSettingsOpen } = useApp();

  const navItems: { id: TabType; label: string; icon: React.ReactNode }[] = [
    { id: 'history', label: 'Timeline & Commits', icon: <History size={18} /> },
    { id: 'snapshot', label: 'Create Snapshot', icon: <Camera size={18} /> },
    { id: 'branches', label: 'Branches', icon: <GitBranch size={18} /> },
    { id: 'diff', label: 'Diff Inspector', icon: <GitCompare size={18} /> },
    { id: 'merge', label: '3-Way Merge', icon: <GitMerge size={18} /> },
    { id: 'benchmark', label: 'Storage Benchmark', icon: <Gauge size={18} /> },
    { id: 'rollback', label: 'Time-Travel & Rollback', icon: <RotateCcw size={18} /> },
  ];

  return (
    <aside className="app-sidebar-rail">
      <div className="sidebar-top">
        <div className="sidebar-brand-btn" title="DataGit Studio">
          <Database size={20} />
        </div>

        <div className="sidebar-nav-icons">
          {navItems.map((item) => (
            <button
              key={item.id}
              className={`sidebar-icon-btn ${activeTab === item.id ? 'active' : ''}`}
              onClick={() => setActiveTab(item.id)}
              title={item.label}
            >
              {item.icon}
            </button>
          ))}
        </div>
      </div>

      <div className="sidebar-bottom">
        {/* Settings button */}
        <button
          className="sidebar-icon-btn"
          onClick={() => setIsSettingsOpen(true)}
          title="Auth & Safeguards Settings"
        >
          <Settings size={18} />
        </button>

        {/* Vertical Theme Toggle Pill (matching the uploaded design!) */}
        <div className="theme-toggle-pill" onClick={toggleTheme} title={`Switch to ${theme === 'dark' ? 'Light' : 'Dark'} mode`}>
          <button
            type="button"
            className={`theme-pill-btn ${theme === 'light' ? 'active' : ''}`}
            aria-label="Light mode"
          >
            <Sun size={15} />
          </button>
          <button
            type="button"
            className={`theme-pill-btn ${theme === 'dark' ? 'active' : ''}`}
            aria-label="Dark mode"
          >
            <Moon size={15} />
          </button>
        </div>
      </div>
    </aside>
  );
};
