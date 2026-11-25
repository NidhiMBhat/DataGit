import React from 'react';
import { CheckCircle2, AlertTriangle, XCircle, Info } from 'lucide-react';
import { useApp } from '../context/AppContext';

export const ToastContainer: React.FC = () => {
  const { toasts, removeToast } = useApp();

  return (
    <div className="toast-container">
      {toasts.map((toast) => {
        const icon =
          toast.type === 'success' ? (
            <CheckCircle2 size={18} className="text-emerald-400" />
          ) : toast.type === 'error' ? (
            <XCircle size={18} className="text-rose-400" />
          ) : toast.type === 'warning' ? (
            <AlertTriangle size={18} className="text-amber-400" />
          ) : (
            <Info size={18} className="text-sky-400" />
          );

        return (
          <div key={toast.id} className={`toast ${toast.type}`} onClick={() => removeToast(toast.id)}>
            <div>{icon}</div>
            <div style={{ flex: 1, wordBreak: 'break-word' }}>{toast.message}</div>
          </div>
        );
      })}
    </div>
  );
};
