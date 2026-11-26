import React from 'react';
import { History, Camera, GitBranch, GitCompare, GitMerge, Gauge, RotateCcw, BarChart3 } from 'lucide-react';
import { useApp, TabType } from '../context/AppContext';

export const NavigationTabs: React.FC = () => {
  const { activeTab, setActiveTab } = useApp();

  const tabs: { id: TabType; label: string; icon: React.ReactNode }[] = [
    { id: 'history', label: 'History & Timeline', icon: <History size={16} /> },
    { id: 'snapshot', label: 'Create Snapshot', icon: <Camera size={16} /> },
    { id: 'branches', label: 'Branches', icon: <GitBranch size={16} /> },
    { id: 'diff', label: 'Diff Inspector', icon: <GitCompare size={16} /> },
    { id: 'merge', label: '3-Way Merge', icon: <GitMerge size={16} /> },
    { id: 'reports', label: 'Reports & Analytics', icon: <BarChart3 size={16} /> },
    { id: 'benchmark', label: 'Storage Benchmark', icon: <Gauge size={16} /> },
    { id: 'rollback', label: 'Time-Travel & Rollback', icon: <RotateCcw size={16} /> },
  ];

  return (
    <nav className="nav-tabs-bar">
      <div className="tabs-container">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`tab-btn ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.icon}
            <span>{tab.label}</span>
          </button>
        ))}
      </div>
    </nav>
  );
};
