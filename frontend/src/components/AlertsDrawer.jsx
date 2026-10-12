import React from 'react';
import { 
  X, 
  Bell, 
  AlertTriangle, 
  ShieldAlert, 
  CheckCircle, 
  ExternalLink,
  RefreshCw 
} from 'lucide-react';

export default function AlertsDrawer({ 
  isOpen, 
  onClose, 
  alerts, 
  onRefresh, 
  onInvestigateAlert 
}) {
  if (!isOpen) return null;

  return (
    <div className="alerts-drawer-overlay" onClick={onClose}>
      <div className="alerts-drawer-content glass-panel-elevated" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-header">
          <div className="drawer-title-box">
            <Bell size={20} className="text-warning" />
            <h3>Real-Time Security & Banking Alerts</h3>
          </div>
          <div className="drawer-header-actions">
            <button 
              type="button" 
              className="icon-action-btn"
              onClick={onRefresh}
              title="Refresh alerts"
            >
              <RefreshCw size={15} />
            </button>
            <button 
              type="button" 
              className="icon-action-btn"
              onClick={onClose}
              title="Close drawer"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="drawer-list-scroll">
          {alerts && alerts.length > 0 ? (
            alerts.map((al) => {
              const isHigh = al.severity === 'high' || al.severity === 'critical' || (al.title && al.title.toLowerCase().includes('fraud'));
              return (
                <div key={al.alert_id || al.id} className={`alert-drawer-card ${isHigh ? 'alert-high' : ''}`}>
                  <div className="alert-top-row">
                    <span className={`badge ${isHigh ? 'badge-danger' : 'badge-warning'}`}>
                      {isHigh ? <ShieldAlert size={12} /> : <AlertTriangle size={12} />}
                      {al.severity?.toUpperCase() || 'ALERT'}
                    </span>
                    <span className="alert-time font-mono text-muted">
                      {al.created_at || al.timestamp || 'Recent'}
                    </span>
                  </div>

                  <h4 className="alert-title">{al.title || al.message || 'Suspicious Activity Detected'}</h4>
                  {al.details && <p className="alert-details text-muted">{al.details}</p>}

                  <div className="alert-meta-row font-mono text-sm">
                    <span>Customer: <strong>{al.customer_id}</strong></span>
                    {al.account_id && <span>Account: {al.account_id}</span>}
                  </div>

                  {onInvestigateAlert && (
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm alert-action-btn"
                      onClick={() => {
                        onInvestigateAlert(al);
                        onClose();
                      }}
                    >
                      <ShieldAlert size={13} />
                      <span>Investigate in AI Assistant</span>
                    </button>
                  )}
                </div>
              );
            })
          ) : (
            <div className="empty-alerts-box text-muted">
              <CheckCircle size={36} className="text-emerald" />
              <p>No active security alerts.</p>
              <span className="font-mono text-sm">
                Inject anomalous transactions in the Telemetry tab to simulate fraud alerts!
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
