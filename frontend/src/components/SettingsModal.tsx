import React, { useState } from 'react';
import { KeyRound, Shield, X } from 'lucide-react';
import { useApp } from '../context/AppContext';

export const SettingsModal: React.FC = () => {
  const { isSettingsOpen, setIsSettingsOpen, settings, updateSettings, refreshState, addToast } = useApp();

  const [apiKey, setApiKey] = useState(settings.apiKey);
  const [authHeaderType, setAuthHeaderType] = useState(settings.authHeaderType);
  const [apiBaseUrl, setApiBaseUrl] = useState(settings.apiBaseUrl);
  const [defaultAllowDirty, setDefaultAllowDirty] = useState(settings.defaultAllowDirty);
  const [author, setAuthor] = useState(settings.author);

  if (!isSettingsOpen) return null;

  const handleSave = async () => {
    updateSettings({
      apiKey,
      authHeaderType,
      apiBaseUrl,
      defaultAllowDirty,
      author,
    });
    addToast('Settings updated successfully', 'success');
    setIsSettingsOpen(false);
    await refreshState();
  };

  return (
    <div className="modal-overlay">
      <div className="modal-card">
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <KeyRound size={18} className="text-indigo-400" />
            <h3>Auth &amp; Safeguards Settings</h3>
          </div>
          <button className="modal-close" onClick={() => setIsSettingsOpen(false)}>
            <X size={20} />
          </button>
        </div>

        <div className="modal-body form-layout">
          <div className="form-group">
            <label className="form-label">API Key (Admin or Read-Only):</label>
            <input
              type="password"
              className="form-input"
              placeholder="e.g. your-datagit-api-key"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
            <span className="text-muted text-xs">
              Required when <code>DATAGIT_API_KEY</code>, <code>DATAGIT_READ_API_KEY</code>, or{' '}
              <code>DATAGIT_REQUIRE_AUTH</code> is active.
            </span>
          </div>

          <div className="form-group">
            <label className="form-label">Auth Header Type:</label>
            <select
              className="form-select"
              value={authHeaderType}
              onChange={(e) => setAuthHeaderType(e.target.value as 'X-API-Key' | 'Bearer')}
            >
              <option value="X-API-Key">X-API-Key (Standard)</option>
              <option value="Bearer">Authorization: Bearer</option>
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">Default Author Name:</label>
            <input
              type="text"
              className="form-input"
              value={author}
              onChange={(e) => setAuthor(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label className="form-label">API Base URL:</label>
            <input
              type="text"
              className="form-input"
              value={apiBaseUrl}
              onChange={(e) => setApiBaseUrl(e.target.value)}
            />
          </div>

          <div className="form-group checkbox-group">
            <input
              type="checkbox"
              id="chkAllowDirty"
              className="form-checkbox"
              checked={defaultAllowDirty}
              onChange={(e) => setDefaultAllowDirty(e.target.checked)}
            />
            <label htmlFor="chkAllowDirty" className="checkbox-label">
              <strong>Default <code>allow_dirty=true</code> for branch checkouts</strong>
              <span className="text-muted block text-xs">
                Permits checking out even when uncommitted changes exist in the working database.
              </span>
            </label>
          </div>

          <div className="callout callout-info">
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <Shield size={16} />
              <span>Settings are securely persisted to local browser storage.</span>
            </div>
          </div>

          <div className="modal-footer">
            <button className="btn btn-secondary" onClick={() => setIsSettingsOpen(false)}>
              Cancel
            </button>
            <button className="btn btn-primary" onClick={handleSave}>
              Save Settings
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
