import React, { useState } from 'react';
import { Shield, User, Briefcase, Lock, KeyRound, AlertCircle, CheckCircle2, ArrowRight } from 'lucide-react';
import { api } from '../api';

const DEMO_USERS_LIST = [
  {
    role: 'customer',
    username: 'C001',
    password: 'password123',
    name: 'Aarav Mehta',
    badge: 'Prime (780 CIBIL)',
    desc: 'Prime banking client with clean credit profile',
  },
  {
    role: 'customer',
    username: 'C002',
    password: 'password123',
    name: 'Diya Nair',
    badge: 'Fraud Victim',
    desc: 'Customer with pending international fraud alerts',
  },
  {
    role: 'customer',
    username: 'C003',
    password: 'password123',
    name: 'Rohan Das',
    badge: 'Subprime (580 CIBIL)',
    desc: 'Customer with subprime credit rating & auto-declines',
  },
  {
    role: 'supervisor',
    username: 'supervisor',
    password: 'admin123',
    name: 'Chief Banking Supervisor',
    badge: 'Supervisor Lead',
    desc: 'Full supervisor authority: cross-customer search & approval queue',
  },
  {
    role: 'supervisor',
    username: 'rm001',
    password: 'admin123',
    name: 'Senior Relationship Manager',
    badge: 'Senior RM',
    desc: 'Relationship manager view with customer 360 & override authority',
  },
];

export default function LoginPage({ onLoginSuccess }) {
  const [activeRoleTab, setActiveRoleTab] = useState('customer'); // 'customer' | 'supervisor'
  const [username, setUsername] = useState('C001');
  const [password, setPassword] = useState('password123');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleRoleTabChange = (role) => {
    setActiveRoleTab(role);
    setError(null);
    if (role === 'customer') {
      setUsername('C001');
      setPassword('password123');
    } else {
      setUsername('supervisor');
      setPassword('admin123');
    }
  };

  const handleQuickDemoClick = (demo) => {
    setActiveRoleTab(demo.role === 'customer' ? 'customer' : 'supervisor');
    setUsername(demo.username);
    setPassword(demo.password);
    setError(null);
    executeLogin(demo.username, demo.password);
  };

  const executeLogin = async (u, p) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.login(u, p);
      if (res && res.token && res.user) {
        onLoginSuccess(res.user);
      } else {
        setError('Authentication response was invalid.');
      }
    } catch (err) {
      setError(err.message || 'Invalid username or password. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError('Please enter both username and password.');
      return;
    }
    executeLogin(username.trim(), password);
  };

  return (
    <div className="login-screen-wrapper">
      <div className="login-background-glow" />
      
      <div className="login-card-container">
        {/* Brand Header */}
        <div className="login-brand-header">
          <div className="login-brand-icon-wrapper">
            <Shield size={36} className="login-brand-icon" />
          </div>
          <h1 className="login-brand-title">
            FIN<span>GENT</span>
          </h1>
          <p className="login-brand-subtitle">
            Autonomous Multi-Agent Banking Platform
          </p>
          <div className="login-security-tag font-mono">
            <Lock size={12} />
            <span>SECURE SERVER-AUTHENTICATED SESSION</span>
          </div>
        </div>

        {/* Role Selector Tabs */}
        <div className="login-role-tabs">
          <button
            type="button"
            id="login-role-customer"
            className={`login-role-tab ${activeRoleTab === 'customer' ? 'active' : ''}`}
            onClick={() => handleRoleTabChange('customer')}
          >
            <User size={16} />
            <span>Customer Portal</span>
          </button>
          <button
            type="button"
            id="login-role-supervisor"
            className={`login-role-tab ${activeRoleTab === 'supervisor' ? 'active' : ''}`}
            onClick={() => handleRoleTabChange('supervisor')}
          >
            <Briefcase size={16} />
            <span>Supervisor / RM</span>
          </button>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="login-error-banner" id="login-error-message">
            <AlertCircle size={16} className="login-error-icon" />
            <span>{error}</span>
          </div>
        )}

        {/* Login Form */}
        <form onSubmit={handleSubmit} className="login-form">
          <div className="form-group">
            <label htmlFor="username-input" className="form-label">
              {activeRoleTab === 'customer' ? 'Customer ID or Username' : 'Supervisor / RM Username'}
            </label>
            <div className="input-with-icon">
              <User size={16} className="field-icon" />
              <input
                id="username-input"
                type="text"
                className="form-input"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder={activeRoleTab === 'customer' ? 'e.g. C001, C002, C003' : 'e.g. supervisor, rm001'}
                autoComplete="username"
                required
              />
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="password-input" className="form-label">
              Password
            </label>
            <div className="input-with-icon">
              <KeyRound size={16} className="field-icon" />
              <input
                id="password-input"
                type="password"
                className="form-input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter password"
                autoComplete="current-password"
                required
              />
            </div>
          </div>

          <button
            id="login-submit-btn"
            type="submit"
            className="login-submit-btn"
            disabled={loading}
          >
            {loading ? (
              <span className="login-loading-spinner">Authenticating...</span>
            ) : (
              <>
                <span>Sign In to {activeRoleTab === 'customer' ? 'Banking' : 'Supervisor Portal'}</span>
                <ArrowRight size={16} />
              </>
            )}
          </button>
        </form>

        {/* Demo Accounts Pill List */}
        <div className="login-demo-accounts-section">
          <div className="demo-accounts-header">
            <span>Quick Demo Credentials (1-Click Login):</span>
          </div>
          <div className="demo-accounts-grid">
            {DEMO_USERS_LIST.map((demo) => (
              <button
                key={demo.username}
                type="button"
                id={`demo-user-${demo.username.toLowerCase()}`}
                className={`demo-pill-btn ${demo.role === activeRoleTab ? 'highlighted' : ''}`}
                onClick={() => handleQuickDemoClick(demo)}
                title={demo.desc}
              >
                <div className="demo-pill-header">
                  <span className="demo-pill-name">{demo.name}</span>
                  <span className="demo-pill-role font-mono">{demo.badge}</span>
                </div>
                <div className="demo-pill-creds font-mono">
                  {demo.username} / {demo.password}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Security Footer */}
        <div className="login-security-footer font-mono">
          <span>SHA-256 HASHED</span> · <span>ROLE-BASED AUTHORIZATION</span> · <span>DATA ISOLATION</span>
        </div>
      </div>
    </div>
  );
}
