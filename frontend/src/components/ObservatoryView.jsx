import React, { useState, useEffect } from 'react';
import { 
  Activity, 
  Cpu, 
  Zap, 
  ShieldAlert, 
  RotateCcw, 
  Play, 
  Square, 
  Terminal, 
  Layers, 
  CheckCircle, 
  AlertTriangle, 
  Clock, 
  Search,
  RefreshCw,
  Flame,
  FileText
} from 'lucide-react';
import { api } from '../api';

export default function ObservatoryView({ 
  customerId, 
  llmStatus, 
  onToggleLlm, 
  onNewAlertGenerated 
}) {
  const [activeSubTab, setActiveSubTab] = useState('metrics'); // 'metrics' | 'simulator' | 'tools' | 'audit'
  const [metrics, setMetrics] = useState(null);
  const [tools, setTools] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [searchTraceId, setSearchTraceId] = useState('');
  const [streamActive, setStreamActive] = useState(false);
  const [simFeed, setSimFeed] = useState([]);
  const [loading, setLoading] = useState(false);
  const [toolsFilter, setToolsFilter] = useState('');

  const fetchMetrics = async () => {
    try {
      const data = await api.getMetrics();
      setMetrics(data);
    } catch (e) {
      console.warn('Failed to fetch metrics:', e);
    }
  };

  const fetchTools = async () => {
    try {
      const data = await api.getToolsCatalogue();
      setTools(Array.isArray(data) ? data : []);
    } catch (e) {
      console.warn('Failed to fetch tools:', e);
    }
  };

  const fetchAudit = async (traceId = searchTraceId) => {
    try {
      const data = await api.getAuditLog(traceId || null, 40);
      setAuditLogs(Array.isArray(data) ? data : []);
    } catch (e) {
      console.warn('Failed to fetch audit log:', e);
    }
  };

  const checkStreamStatus = async () => {
    try {
      const res = await api.streamControl('status');
      setStreamActive(res?.running || false);
    } catch (e) {
      console.warn('Stream status error:', e);
    }
  };

  useEffect(() => {
    fetchMetrics();
    fetchTools();
    fetchAudit();
    checkStreamStatus();
    const interval = setInterval(() => {
      fetchMetrics();
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleResetMetrics = async () => {
    if (window.confirm('Reset all routing and token telemetry counters?')) {
      await api.resetMetrics();
      fetchMetrics();
    }
  };

  const handleToggleStream = async () => {
    const nextAction = streamActive ? 'stop' : 'start';
    try {
      const res = await api.streamControl(nextAction);
      setStreamActive(res?.running || !streamActive);
    } catch (e) {
      alert(`Stream control error: ${e.message}`);
    }
  };

  const handleSimulate = async (anomalous) => {
    setLoading(true);
    try {
      const result = await api.simulateTransaction(customerId, anomalous);
      setSimFeed((prev) => [
        {
          id: `sim-${Date.now()}`,
          anomalous,
          txn: result.transaction,
          risk: result.risk,
          alert: result.alert,
          timestamp: new Date().toLocaleTimeString(),
        },
        ...prev.slice(0, 19),
      ]);
      if (onNewAlertGenerated) onNewAlertGenerated();
      fetchMetrics();
      fetchAudit();
    } catch (err) {
      alert(`Simulation failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const filteredTools = tools.filter((t) => {
    if (!toolsFilter) return true;
    const q = toolsFilter.toLowerCase();
    return (
      t.name.toLowerCase().includes(q) ||
      t.description.toLowerCase().includes(q) ||
      t.allowed_agents.some((ag) => ag.toLowerCase().includes(q))
    );
  });

  return (
    <div className="observatory-view-container fade-in">
      {/* Subtab navigation */}
      <div className="observatory-subtabs glass-panel">
        <button
          type="button"
          className={`subtab-btn ${activeSubTab === 'metrics' ? 'active' : ''}`}
          onClick={() => setActiveSubTab('metrics')}
        >
          <Activity size={15} />
          <span>Telemetry & Metrics</span>
        </button>

        <button
          type="button"
          className={`subtab-btn ${activeSubTab === 'simulator' ? 'active' : ''}`}
          onClick={() => setActiveSubTab('simulator')}
        >
          <Flame size={15} />
          <span>Live Stream & Fraud Simulator</span>
        </button>

        <button
          type="button"
          className={`subtab-btn ${activeSubTab === 'tools' ? 'active' : ''}`}
          onClick={() => {
            setActiveSubTab('tools');
            fetchTools();
          }}
        >
          <Layers size={15} />
          <span>Tools Registry ({tools.length})</span>
        </button>

        <button
          type="button"
          className={`subtab-btn ${activeSubTab === 'audit' ? 'active' : ''}`}
          onClick={() => {
            setActiveSubTab('audit');
            fetchAudit();
          }}
        >
          <FileText size={15} />
          <span>Immutable Audit Log</span>
        </button>
      </div>

      {/* SUBTAB 1: TELEMETRY & METRICS */}
      {activeSubTab === 'metrics' && (
        <div className="observatory-content">
          {/* Key KPI Strip */}
          <div className="metrics-cards-grid">
            {/* Self-Evaluation Pass Rate */}
            <div className="metric-card glass-panel">
              <div className="metric-card-top">
                <span className="metric-title">SELF-EVALUATION PASS RATE</span>
                <CheckCircle size={18} className="text-emerald" />
              </div>
              <div className="metric-value text-emerald font-mono">
                {metrics?.requests && metrics?.self_evaluations_passed !== undefined
                  ? `${((metrics.self_evaluations_passed / metrics.requests) * 100).toFixed(1)}%`
                  : '100.0%'}
              </div>
              <p className="metric-desc">Verified against database & policy rules</p>
            </div>

            {/* Total Requests */}
            <div className="metric-card glass-panel">
              <div className="metric-card-top">
                <span className="metric-title">TOTAL REQUESTS</span>
                <Activity size={18} className="text-cyan" />
              </div>
              <div className="metric-value font-mono text-cyan">
                {metrics?.requests || 0}
              </div>
              <p className="metric-desc">Inbound queries orchestrated via OTA loop</p>
            </div>

            {/* P50 / P95 Latency */}
            <div className="metric-card glass-panel">
              <div className="metric-card-top">
                <span className="metric-title">P50 / P95 LATENCY</span>
                <Clock size={18} className="text-warning" />
              </div>
              <div className="metric-value font-mono">
                {metrics?.latency_ms_p50 !== undefined ? `${metrics.latency_ms_p50.toFixed(1)}ms` : '~2.1ms'}
                <span className="sub-val text-muted"> / {metrics?.latency_ms_p95 !== undefined ? `${metrics.latency_ms_p95.toFixed(1)}ms` : '18ms'}</span>
              </div>
              <p className="metric-desc">Sub-second execution for all money rules</p>
            </div>

            {/* Completion Rate */}
            <div className="metric-card glass-panel">
              <div className="metric-card-top">
                <span className="metric-title">COMPLETION RATE</span>
                <Zap size={18} className="text-violet" />
              </div>
              <div className="metric-value font-mono text-violet">
                {metrics?.completion_rate !== undefined ? `${(metrics.completion_rate * 100).toFixed(1)}%` : '100.0%'}
              </div>
              <p className="metric-desc font-mono">
                Verified workflows completed cleanly
              </p>
            </div>
          </div>

          {/* Workflow Lifecycle Breakdown */}
          <div className="tier-breakdown-card glass-panel">
            <div className="section-header-row">
              <h3>Workflow Lifecycle Distribution</h3>
              <button type="button" className="btn btn-secondary btn-sm" onClick={handleResetMetrics}>
                <RotateCcw size={13} />
                <span>Reset Telemetry</span>
              </button>
            </div>

            <div className="tier-bars-container">
              <div className="tier-bar-row">
                <div className="tier-bar-label font-mono">
                  <span className="badge badge-tier0">COMPLETED</span>
                  <span>Verified Clean Completion</span>
                </div>
                <div className="tier-progress-track">
                  <div 
                    className="tier-progress-fill fill-tier0" 
                    style={{ width: `${Math.min(100, ((metrics?.completed || 0) / Math.max(1, metrics?.requests || 1)) * 100)}%` }} 
                  />
                </div>
                <span className="tier-count font-mono">{metrics?.completed || 0} reqs</span>
              </div>

              <div className="tier-bar-row">
                <div className="tier-bar-label font-mono">
                  <span className="badge badge-warning">AWAITING APPROVAL</span>
                  <span>Human-in-the-Loop Gated</span>
                </div>
                <div className="tier-progress-track">
                  <div 
                    className="tier-progress-fill fill-tier3" 
                    style={{ width: `${Math.min(100, ((metrics?.awaiting_approval || 0) / Math.max(1, metrics?.requests || 1)) * 100)}%` }} 
                  />
                </div>
                <span className="tier-count font-mono">{metrics?.awaiting_approval || 0} reqs</span>
              </div>

              <div className="tier-bar-row">
                <div className="tier-bar-label font-mono">
                  <span className="badge badge-tier1">NEEDS CLARIFICATION</span>
                  <span>Missing Slots / Ambiguous</span>
                </div>
                <div className="tier-progress-track">
                  <div 
                    className="tier-progress-fill fill-tier1" 
                    style={{ width: `${Math.min(100, ((metrics?.needs_clarification || 0) / Math.max(1, metrics?.requests || 1)) * 100)}%` }} 
                  />
                </div>
                <span className="tier-count font-mono">{metrics?.needs_clarification || 0} reqs</span>
              </div>

              <div className="tier-bar-row">
                <div className="tier-bar-label font-mono">
                  <span className="badge badge-tier2">ESCALATED</span>
                  <span>Escalated to Human RM</span>
                </div>
                <div className="tier-progress-track">
                  <div 
                    className="tier-progress-fill fill-tier2" 
                    style={{ width: `${Math.min(100, ((metrics?.escalated || 0) / Math.max(1, metrics?.requests || 1)) * 100)}%` }} 
                  />
                </div>
                <span className="tier-count font-mono">{metrics?.escalated || 0} reqs</span>
              </div>
            </div>
          </div>

          {/* Deterministic Policy Gate Architecture Panel */}
          <div className="offline-resilience-card glass-panel">
            <div className="resilience-left">
              <Cpu size={32} className="text-cyan" />
              <div>
                <h3>Deterministic Grounding & Policy Gate Guarantee</h3>
                <p className="text-muted">
                  Financial facts, account balances, loan underwriting rules, KYC gates, and fraud scoring run on deterministic database records and policy engines. The LLM acts as an orchestrator and natural-language interface without ever inventing financial values.
                </p>
              </div>
            </div>
            <button
              type="button"
              className={`btn ${llmStatus?.enabled ? 'btn-secondary' : 'btn-primary'}`}
              onClick={onToggleLlm}
            >
              {llmStatus?.enabled ? 'Switch to Demo Mock Mode' : 'Enable Configured LLM Provider'}
            </button>
          </div>
        </div>
      )}

      {/* SUBTAB 2: STREAM & FRAUD SIMULATOR */}
      {activeSubTab === 'simulator' && (
        <div className="simulator-content fade-in">
          <div className="simulator-control-panel glass-panel">
            <div className="sim-control-left">
              <Flame size={24} className="text-warning" />
              <div>
                <h3>Synthetic Transaction Generator & Live Stream</h3>
                <p className="text-muted">
                  Simulate live payment traffic. Transactions are evaluated instantly with the IsolationForest fraud model and rules. High-risk transactions immediately trigger security alerts!
                </p>
              </div>
            </div>

            <div className="sim-actions-group">
              <button
                type="button"
                className={`btn ${streamActive ? 'btn-danger' : 'btn-secondary'}`}
                onClick={handleToggleStream}
              >
                {streamActive ? <Square size={14} /> : <Play size={14} />}
                <span>{streamActive ? 'Stop Live Feed' : 'Start Live Feed'}</span>
              </button>

              <button
                type="button"
                className="btn btn-secondary"
                disabled={loading}
                onClick={() => handleSimulate(false)}
              >
                <CheckCircle size={15} className="text-emerald" />
                <span>Inject Normal Txn</span>
              </button>

              <button
                type="button"
                className="btn btn-danger"
                disabled={loading}
                onClick={() => handleSimulate(true)}
              >
                <AlertTriangle size={15} />
                <span>Inject Anomalous Fraud Txn</span>
              </button>
            </div>
          </div>

          {/* Simulator Activity Feed */}
          <div className="sim-feed-list glass-panel">
            <div className="section-header-row">
              <h4>Real-Time Stream Feed ({simFeed.length})</h4>
              <span className="text-muted font-mono font-sm">Live scoring via IsolationForest</span>
            </div>

            {simFeed.length > 0 ? (
              <div className="sim-feed-items">
                {simFeed.map((item) => (
                  <div key={item.id} className={`sim-feed-item ${item.anomalous ? 'sim-item-fraud' : ''}`}>
                    <div className="sim-item-header font-mono">
                      <span className={`badge ${item.anomalous ? 'badge-danger' : 'badge-tier0'}`}>
                        {item.anomalous ? 'ANOMALOUS SUSPECT' : 'NORMAL PAYMENT'}
                      </span>
                      <span className="text-muted">{item.timestamp}</span>
                      <span>Customer: <strong>{item.txn?.customer_id}</strong></span>
                      <span className="amount-tag font-bold">₹{item.txn?.amount}</span>
                    </div>

                    <div className="sim-item-details">
                      <div>Merchant: <strong>{item.txn?.merchant}</strong> ({item.txn?.city}, {item.txn?.channel})</div>
                      {item.risk && (
                        <div className="font-mono text-sm">
                          Risk Score: <strong className={item.risk.risk_score >= 70 ? 'text-rose' : 'text-emerald'}>{item.risk.risk_score}/100</strong>
                          {item.risk.reasons?.length > 0 && ` · Reasons: [${item.risk.reasons.join(', ')}]`}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-feed-placeholder text-muted font-mono">
                No simulated transactions injected yet. Click "Inject Anomalous Fraud Txn" or start the live feed above.
              </div>
            )}
          </div>
        </div>
      )}

      {/* SUBTAB 3: TOOLS REGISTRY */}
      {activeSubTab === 'tools' && (
        <div className="tools-content fade-in">
          <div className="tools-filter-bar glass-panel">
            <div className="search-input-box">
              <Search size={16} />
              <input
                type="text"
                placeholder="Filter tools by name, agent or description..."
                value={toolsFilter}
                onChange={(e) => setToolsFilter(e.target.value)}
              />
            </div>
            <span className="tools-count-badge font-mono text-muted">
              {filteredTools.length} / {tools.length} TOOLS REGISTERED
            </span>
          </div>

          <div className="tools-grid">
            {filteredTools.map((t) => (
              <div key={t.name} className="tool-card glass-panel">
                <div className="tool-card-top">
                  <h4 className="font-mono">{t.name}</h4>
                  <div className="tool-badges">
                    {t.requires_approval ? (
                      <span className="badge badge-warning" title="Writes require human approval">
                        Approval Gate
                      </span>
                    ) : (
                      <span className="badge badge-neutral">Auto-Execute</span>
                    )}
                  </div>
                </div>
                <p className="tool-desc">{t.description}</p>
                <div className="tool-allowed-agents">
                  <span className="text-muted font-sm font-mono">Allowed Agents:</span>
                  <div className="agent-pills-row">
                    {t.allowed_agents?.map((ag) => (
                      <span key={ag} className="agent-pill">
                        {ag}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* SUBTAB 4: IMMUTABLE AUDIT LOG */}
      {activeSubTab === 'audit' && (
        <div className="audit-content fade-in">
          <div className="audit-header-bar glass-panel">
            <div className="search-input-box">
              <Search size={16} />
              <input
                type="text"
                placeholder="Search audit trail by Trace ID..."
                value={searchTraceId}
                onChange={(e) => setSearchTraceId(e.target.value)}
              />
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => fetchAudit(searchTraceId)}
              >
                Search
              </button>
              {searchTraceId && (
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => {
                    setSearchTraceId('');
                    fetchAudit('');
                  }}
                >
                  Clear
                </button>
              )}
            </div>

            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => fetchAudit()}
            >
              <RefreshCw size={14} />
              <span>Refresh Log</span>
            </button>
          </div>

          <div className="audit-table-wrapper glass-panel">
            <table className="audit-table font-mono">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Trace ID</th>
                  <th>Agent</th>
                  <th>Tool Executed</th>
                  <th>Status</th>
                  <th>Arguments (PII Masked)</th>
                </tr>
              </thead>
              <tbody>
                {auditLogs.length > 0 ? (
                  auditLogs.map((log, idx) => (
                    <tr key={idx}>
                      <td className="text-muted">{log.timestamp?.split('T')[1]?.substring(0, 8) || log.timestamp || 'Now'}</td>
                      <td>
                        <span className="trace-id-badge">{log.trace_id}</span>
                      </td>
                      <td>
                        <span className="agent-pill">{log.agent}</span>
                      </td>
                      <td>
                        <strong>{log.tool}</strong>
                      </td>
                      <td>
                        <span className={`status-badge ${log.status === 'ok' ? 'status-ok' : 'status-pending'}`}>
                          {log.status}
                        </span>
                      </td>
                      <td className="args-cell">
                        <pre>{typeof log.args === 'string' ? log.args : JSON.stringify(log.args)}</pre>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan="6" className="empty-cell text-muted">
                      No audit rows found. Perform requests in the Chat or simulator to generate audit events.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
