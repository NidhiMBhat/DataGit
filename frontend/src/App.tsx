import React from 'react';
import { useApp } from './context/AppContext';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { ToastContainer } from './components/ToastContainer';
import { SettingsModal } from './components/SettingsModal';
import { HistoryTab } from './components/tabs/HistoryTab';
import { SchemaTab } from './components/tabs/SchemaTab';
import { SnapshotTab } from './components/tabs/SnapshotTab';
import { BranchesTab } from './components/tabs/BranchesTab';
import { DiffTab } from './components/tabs/DiffTab';
import { MergeTab } from './components/tabs/MergeTab';
import { BenchmarkTab } from './components/tabs/BenchmarkTab';
import { RollbackTab } from './components/tabs/RollbackTab';

export const AppContent: React.FC = () => {
  const { activeTab } = useApp();

  return (
    <div className="app-shell-layout">
      {/* Left Icon Rail */}
      <Sidebar />

      {/* Main App Workspace */}
      <div className="app-workspace">
        <Header />

        <main className="app-main-canvas">
          <div className="canvas-inner-card">
            {activeTab === 'history' && <HistoryTab />}
            {activeTab === 'schema' && <SchemaTab />}
            {activeTab === 'snapshot' && <SnapshotTab />}
            {activeTab === 'branches' && <BranchesTab />}
            {activeTab === 'diff' && <DiffTab />}
            {activeTab === 'merge' && <MergeTab />}
            {activeTab === 'benchmark' && <BenchmarkTab />}
            {activeTab === 'rollback' && <RollbackTab />}
          </div>
        </main>
      </div>

      <SettingsModal />
      <ToastContainer />
    </div>
  );
};

export default AppContent;
