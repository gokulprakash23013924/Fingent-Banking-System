import React from 'react';
import { 
  Shield, 
  User, 
  Briefcase, 
  Cpu, 
  Bell, 
  Activity, 
  Sparkles, 
  RefreshCw,
  Power,
  Lock,
  Search
} from 'lucide-react';

export const DEMO_CUSTOMERS = [
  { id: 'C001', name: 'Aarav Mehta', story: 'Prime Client (780 CIBIL, Clean Profile)', city: 'Mumbai' },
  { id: 'C002', name: 'Diya Nair', story: 'Fraud Victim (₹48k Suspicious Intl Txn)', city: 'Kochi' },
  { id: 'C003', name: 'Rohan Das', story: 'Subprime Credit (580 CIBIL, Loan Decline)', city: 'Kolkata' },
  { id: 'C004', name: 'Meera Iyer', story: 'KYC Pending (High earner, writes held)', city: 'Chennai' },
  { id: 'C005', name: 'Karthik Raman', story: 'High DTI / Overleveraged (Counter-offers)', city: 'Bengaluru' },
  { id: 'C006', name: 'Sana Khan', story: 'Risky Payment History (Referred to manual)', city: 'Hyderabad' },
  { id: 'C009', name: 'Imran Sheikh', story: 'KYC Expired (Transfers blocked)', city: 'Lucknow' },
  { id: 'C010', name: 'Lakshmi Pillai', story: 'AML Watchlist Flag (RM view shows flag)', city: 'Coimbatore' },
];

export default function Navbar({
  activeTab,
  setActiveTab,
  customerId,
  setCustomerId,
  role,
  llmStatus,
  onToggleLlm,
  alertsCount,
  onOpenAlerts,
  pendingApprovalsCount,
  onRefreshAll,
  currentUser,
  onLogout
}) {
  const isSupervisor = role === 'supervisor' || role === 'rm';
  const currentCustomer = DEMO_CUSTOMERS.find(c => c.id === customerId) || DEMO_CUSTOMERS[0];

  return (
    <header className="navbar-container">
      <div className="navbar-top">
        {/* Brand */}
        <div className="navbar-brand">
          <div className="brand-logo-wrapper">
            <div className="brand-icon-glow">
              <Shield size={22} className="brand-icon" />
            </div>
          </div>
          <div className="brand-text">
            <div className="brand-title-row">
              <h1 className="brand-title">FIN<span>GENT</span></h1>
              <span className="badge badge-completed font-mono">OBSERVE–THINK–ACT ARCHITECTURE</span>
            </div>
            <p className="brand-subtitle">
              {isSupervisor 
                ? 'Supervisor Portal · Bank-Wide Customer Lookup & Approval Authority' 
                : 'Customer Banking Portal · Strict Account Isolation Enforced'}
            </p>
          </div>
        </div>

        {/* Global Controls */}
        <div className="navbar-controls">
          {/* Authenticated Session Badge */}
          <div className="auth-session-badge" id="authenticated-session-badge" title={`Server-authenticated as: ${currentUser?.name || customerId} (${currentUser?.role || role})`}>
            <Lock size={12} className="auth-lock-icon" />
            <div className="auth-badge-details">
              <span className="auth-username">{currentUser?.name || (isSupervisor ? 'Supervisor' : customerId)}</span>
              <span className="auth-user-id font-mono">{currentUser?.customer_id ? `[${currentUser.customer_id}]` : `[${currentUser?.username || 'STAFF'}]`}</span>
            </div>
            <span className={`auth-badge-role ${isSupervisor ? 'role-supervisor' : 'role-customer'}`}>
              {isSupervisor ? 'SUPERVISOR' : 'CUSTOMER'}
            </span>
          </div>

          {/* Supervisor-Only Target Customer Selector */}
          {isSupervisor && (
            <div className="persona-selector-box supervisor-lookup-box">
              <div className="selector-label">
                <Search size={13} />
                <span>Target Customer 360:</span>
              </div>
              <select 
                id="customer-persona-select"
                value={customerId} 
                onChange={(e) => setCustomerId(e.target.value)}
                className="persona-select"
              >
                {DEMO_CUSTOMERS.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.id} · {c.name} ({c.city})
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Offline Resilience Switch (LLM Available toggle) */}
          <button 
            id="llm-toggle-btn"
            type="button"
            className={`llm-status-pill ${llmStatus?.enabled ? 'llm-on' : 'llm-off'}`}
            onClick={onToggleLlm}
            title={llmStatus?.enabled ? "LLM is enabled. Click to toggle Demo/Mock mode" : "System running in Mock / Demo mode (zero API key needed)"}
          >
            <Cpu size={14} />
            <span>LLM: {llmStatus?.enabled ? 'Active Model' : 'Demo / Mock'}</span>
            <span className={`pulse-indicator ${llmStatus?.enabled ? '' : 'warning'}`} />
          </button>

          {/* Alerts Bell */}
          <button 
            id="alerts-bell-btn"
            type="button"
            className="icon-action-btn"
            onClick={onOpenAlerts}
            title="Real-time Banking & Fraud Alerts"
          >
            <Bell size={18} />
            {alertsCount > 0 && (
              <span className="alerts-badge-count">{alertsCount}</span>
            )}
          </button>

          {/* Refresh global state */}
          <button 
            id="refresh-all-btn"
            type="button"
            className="icon-action-btn"
            onClick={onRefreshAll}
            title="Refresh Bank State & Telemetry"
          >
            <RefreshCw size={17} />
          </button>

          {/* Logout Button */}
          <button
            id="logout-btn"
            type="button"
            className="logout-btn"
            onClick={onLogout}
            title="Sign out of current banking session"
          >
            <Power size={14} />
            <span>Sign Out</span>
          </button>
        </div>
      </div>

      {/* Role-Differentiated Navigation Tabs */}
      <nav className="navbar-nav">
        {isSupervisor ? (
          /* Supervisor Navigation Tabs */
          <>
            <button
              id="nav-tab-customer"
              type="button"
              className={`nav-tab ${activeTab === 'customer' ? 'active' : ''}`}
              onClick={() => setActiveTab('customer')}
            >
              <User size={16} />
              <span>Customer 360 & Search</span>
              <span className="nav-tab-hint">{currentCustomer.name} ({currentCustomer.id})</span>
            </button>

            <button
              id="nav-tab-chat"
              type="button"
              className={`nav-tab ${activeTab === 'chat' ? 'active' : ''}`}
              onClick={() => setActiveTab('chat')}
            >
              <Sparkles size={16} />
              <span>Supervisor AI Assistant</span>
              <span className="nav-tab-hint">Cross-Customer Query Allowed</span>
            </button>
          </>
        ) : (
          /* Customer Navigation Tabs */
          <>
            <button
              id="nav-tab-chat"
              type="button"
              className={`nav-tab ${activeTab === 'chat' ? 'active' : ''}`}
              onClick={() => setActiveTab('chat')}
            >
              <Sparkles size={16} />
              <span>AI Banking Assistant</span>
              <span className="nav-tab-hint">Accounts · Cards · Razorpay · Loans</span>
            </button>

            <button
              id="nav-tab-customer"
              type="button"
              className={`nav-tab ${activeTab === 'customer' ? 'active' : ''}`}
              onClick={() => setActiveTab('customer')}
            >
              <User size={16} />
              <span>My Accounts & Statements</span>
              <span className="nav-tab-hint">{currentUser?.name || currentCustomer.name}</span>
            </button>
          </>
        )}
      </nav>
    </header>
  );
}
