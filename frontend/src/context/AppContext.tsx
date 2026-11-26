import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { Branch, Commit, AuthSettings, WorkspaceStatus, DemoSimulateResult } from '../types/api';
import { apiRequest, ApiError, defaultSettings } from '../services/api';

export type TabType = 'history' | 'schema' | 'snapshot' | 'branches' | 'diff' | 'merge' | 'benchmark' | 'rollback';
export type ThemeMode = 'light' | 'dark';

export interface ToastItem {
  id: string;
  message: string;
  type: 'success' | 'error' | 'warning' | 'info';
}

interface AppContextType {
  theme: ThemeMode;
  setTheme: (theme: ThemeMode) => void;
  toggleTheme: () => void;
  activeTab: TabType;
  setActiveTab: (tab: TabType) => void;
  branches: Branch[];
  activeBranch: string | null;
  currentHead: number | null;
  history: Commit[];
  isOnline: boolean;
  safeguardsActive: boolean;
  safeguardsMessage: string;
  settings: AuthSettings;
  updateSettings: (newSettings: Partial<AuthSettings>) => void;
  refreshState: () => Promise<void>;
  diffPair: { from: number | ''; to: number | '' };
  setDiffPair: React.Dispatch<React.SetStateAction<{ from: number | ''; to: number | '' }>>;
  toasts: ToastItem[];
  addToast: (message: string, type?: 'success' | 'error' | 'warning' | 'info', duration?: number) => void;
  removeToast: (id: string) => void;
  isSettingsOpen: boolean;
  setIsSettingsOpen: (open: boolean) => void;
  workspaceStatus: WorkspaceStatus | null;
  isWorkspaceDirty: boolean;
  checkWorkspaceStatus: () => Promise<WorkspaceStatus | null>;
  isDemoModalOpen: boolean;
  setIsDemoModalOpen: (open: boolean) => void;
  suggestedCommitMessage: string;
  setSuggestedCommitMessage: (msg: string) => void;
  executeScenario: (scenario: string, customSql?: string) => Promise<DemoSimulateResult>;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export const AppProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [theme, setThemeState] = useState<ThemeMode>(
    (localStorage.getItem('datagit_theme') as ThemeMode) || 'light'
  );
  const [activeTab, setActiveTab] = useState<TabType>('history');
  const [branches, setBranches] = useState<Branch[]>([]);
  const [activeBranch, setActiveBranch] = useState<string | null>(null);
  const [currentHead, setCurrentHead] = useState<number | null>(null);
  const [history, setHistory] = useState<Commit[]>([]);
  const [isOnline, setIsOnline] = useState<boolean>(false);
  const [safeguardsActive, setSafeguardsActive] = useState<boolean>(false);
  const [safeguardsMessage, setSafeguardsMessage] = useState<string>('');
  const [settings, setSettings] = useState<AuthSettings>(defaultSettings);
  const [diffPair, setDiffPair] = useState<{ from: number | ''; to: number | '' }>({ from: '', to: '' });
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [isSettingsOpen, setIsSettingsOpen] = useState<boolean>(false);
  const [workspaceStatus, setWorkspaceStatus] = useState<WorkspaceStatus | null>(null);
  const [isWorkspaceDirty, setIsWorkspaceDirty] = useState<boolean>(false);
  const [isDemoModalOpen, setIsDemoModalOpen] = useState<boolean>(false);
  const [suggestedCommitMessage, setSuggestedCommitMessage] = useState<string>('');

  const setTheme = useCallback((newTheme: ThemeMode) => {
    setThemeState(newTheme);
    localStorage.setItem('datagit_theme', newTheme);
    document.documentElement.setAttribute('data-theme', newTheme);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(theme === 'dark' ? 'light' : 'dark');
  }, [theme, setTheme]);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  const addToast = useCallback((message: string, type: 'success' | 'error' | 'warning' | 'info' = 'info', duration: number = 4500) => {
    const id = `${Date.now()}-${Math.random()}`;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, duration);
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const updateSettings = useCallback((newSettings: Partial<AuthSettings>) => {
    setSettings((prev) => {
      const merged = { ...prev, ...newSettings };
      localStorage.setItem('datagit_api_key', merged.apiKey);
      localStorage.setItem('datagit_auth_header', merged.authHeaderType);
      localStorage.setItem('datagit_api_base', merged.apiBaseUrl);
      localStorage.setItem('datagit_default_allow_dirty', merged.defaultAllowDirty ? 'true' : 'false');
      localStorage.setItem('datagit_author', merged.author);
      return merged;
    });
  }, []);

  const refreshState = useCallback(async () => {
    try {
      const branchesData = await apiRequest<Branch[]>('/branches', {}, settings);
      setBranches(branchesData);
      setIsOnline(true);
      setSafeguardsActive(false);

      const active = branchesData.find((b) => b.is_current);
      if (active) {
        setActiveBranch(active.name);
        const head = active.head_commit ?? active.head_commit_id ?? null;
        setCurrentHead(head);
      } else {
        setActiveBranch(null);
        setCurrentHead(null);
      }
    } catch (err) {
      setIsOnline(false);
      const apiErr = err as ApiError;
      if (apiErr.status === 401) {
        setSafeguardsActive(true);
        setSafeguardsMessage('Authentication required (401). Please configure an API key in Auth Settings.');
      } else if (apiErr.status === 403) {
        setSafeguardsActive(true);
        setSafeguardsMessage('DataGit API is operating in Read-Only mode (mutating POST endpoints are blocked).');
      }
    }

    try {
      const historyData = await apiRequest<Commit[]>('/history?limit=50', {}, settings);
      setHistory(Array.isArray(historyData) ? historyData : []);
    } catch (e) {
      console.warn('Could not refresh history:', e);
    }

    try {
      const status = await apiRequest<WorkspaceStatus>('/workspace/status', {}, settings);
      setWorkspaceStatus(status);
      setIsWorkspaceDirty(Boolean(status?.is_dirty));
    } catch (e) {
      console.warn('Could not check workspace status:', e);
    }
  }, [settings]);

  const checkWorkspaceStatus = useCallback(async (): Promise<WorkspaceStatus | null> => {
    try {
      const status = await apiRequest<WorkspaceStatus>('/workspace/status', {}, settings);
      setWorkspaceStatus(status);
      setIsWorkspaceDirty(Boolean(status?.is_dirty));
      return status;
    } catch (e) {
      console.warn('Could not check workspace status:', e);
      return null;
    }
  }, [settings]);

  const executeScenario = useCallback(
    async (scenario: string, customSql?: string): Promise<DemoSimulateResult> => {
      const result = await apiRequest<DemoSimulateResult>(
        '/demo/simulate',
        {
          method: 'POST',
          body: { scenario, custom_sql: customSql },
        },
        settings
      );
      if (result.workspace_status) {
        setWorkspaceStatus(result.workspace_status);
        setIsWorkspaceDirty(Boolean(result.workspace_status.is_dirty));
      }
      if (result.suggested_commit_message) {
        setSuggestedCommitMessage(result.suggested_commit_message);
      }
      await refreshState();
      return result;
    },
    [settings, refreshState]
  );

  useEffect(() => {
    refreshState();
  }, [refreshState]);

  return (
    <AppContext.Provider
      value={{
        theme,
        setTheme,
        toggleTheme,
        activeTab,
        setActiveTab,
        branches,
        activeBranch,
        currentHead,
        history,
        isOnline,
        safeguardsActive,
        safeguardsMessage,
        settings,
        updateSettings,
        refreshState,
        diffPair,
        setDiffPair,
        toasts,
        addToast,
        removeToast,
        isSettingsOpen,
        setIsSettingsOpen,
        workspaceStatus,
        isWorkspaceDirty,
        checkWorkspaceStatus,
        isDemoModalOpen,
        setIsDemoModalOpen,
        suggestedCommitMessage,
        setSuggestedCommitMessage,
        executeScenario,
      }}
    >
      {children}
    </AppContext.Provider>
  );
};

export const useApp = () => {
  const context = useContext(AppContext);
  if (!context) throw new Error('useApp must be used within an AppProvider');
  return context;
};
