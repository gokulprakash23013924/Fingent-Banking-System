import React, { useState, useEffect, useCallback } from 'react';
import Navbar from './components/Navbar';
import ChatView from './components/ChatView';
import CustomerView from './components/CustomerView';
import AlertsDrawer from './components/AlertsDrawer';
import LoginPage from './components/LoginPage';
import { api } from './api';
import './App.css';

export default function App() {
  const [currentUser, setCurrentUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);

  const [activeTab, setActiveTab] = useState('chat'); // 'chat' | 'customer' | 'approvals' | 'observatory'
  const [customerId, setCustomerId] = useState('C001');
  const [role, setRole] = useState('customer'); // 'customer' | 'supervisor' | 'rm'
  const [llmStatus, setLlmStatus] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [pendingApprovalsCount, setPendingApprovalsCount] = useState(0);
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [selectedPrompt, setSelectedPrompt] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // Check existing session on mount
  useEffect(() => {
    const checkExistingSession = async () => {
      const token = api.getToken();
      if (!token) {
        setAuthLoading(false);
        return;
      }
      try {
        const res = await api.getMe();
        if (res && res.authenticated && res.user) {
          handleLoginSuccess(res.user);
        } else {
          api.setToken(null);
          setCurrentUser(null);
        }
      } catch (e) {
        console.warn('Session verification failed:', e);
        api.setToken(null);
        setCurrentUser(null);
      } finally {
        setAuthLoading(false);
      }
    };
    checkExistingSession();
  }, []);

  const handleLoginSuccess = (user) => {
    setCurrentUser(user);
    const userRole = user.role || 'customer';
    setRole(userRole);
    if (userRole === 'customer') {
      const cid = user.customer_id || 'C001';
      setCustomerId(cid);
      setActiveTab('chat');
    } else {
      setCustomerId('C001'); // Supervisor starts on customer 360 overview
      setActiveTab('customer');
    }
    setRefreshKey((k) => k + 1);
  };

  const handleLogout = async () => {
    try {
      await api.logout();
    } catch (e) {
      console.warn('Logout error:', e);
    } finally {
      api.setToken(null);
      // Clear all active session chats upon logout
      try {
        Object.keys(sessionStorage).forEach((key) => {
          if (key.startsWith('fingent_chat_') || key.startsWith('fingent_conv_') || key.startsWith('nexus_chat_') || key.startsWith('nexus_conv_')) {
            sessionStorage.removeItem(key);
          }
        });
      } catch (e) {}
      setCurrentUser(null);
      setRole('customer');
      setCustomerId('C001');
      setActiveTab('chat');
    }
  };

  const fetchGlobalState = useCallback(async () => {
    if (!currentUser) return;

    try {
      // 1. LLM status
      try {
        const llm = await api.getLlmStatus();
        setLlmStatus(llm);
      } catch (e) {
        console.warn('Failed to load LLM status:', e);
      }

      // 2. Alerts (isolated by customer for customer role)
      try {
        const cidFilter = currentUser.role === 'customer' ? currentUser.customer_id : null;
        const alertsData = await api.getAlerts(cidFilter, 0, 30);
        setAlerts(Array.isArray(alertsData) ? alertsData : []);
      } catch (e) {
        console.warn('Failed to load alerts:', e);
      }

      // 3. Pending approvals count (isolated by customer for customer role)
      try {
        const cidFilter = currentUser.role === 'customer' ? currentUser.customer_id : null;
        const pending = await api.getPendingApprovals(cidFilter);
        setPendingApprovalsCount(Array.isArray(pending) ? pending.length : 0);
      } catch (e) {
        console.warn('Failed to load pending approvals:', e);
      }
    } catch (err) {
      console.error('Error fetching global telemetry state:', err);
    }
  }, [currentUser]);

  useEffect(() => {
    if (currentUser) {
      fetchGlobalState();
      const interval = setInterval(fetchGlobalState, 8000);
      return () => clearInterval(interval);
    }
  }, [currentUser, fetchGlobalState]);

  const handleToggleLlm = async () => {
    const nextState = !(llmStatus?.enabled ?? true);
    try {
      const res = await api.setLlmStatus(nextState);
      setLlmStatus((prev) => ({ ...prev, enabled: res.llm_enabled }));
    } catch (err) {
      alert(`Failed to toggle LLM mode: ${err.message}`);
    }
  };

  const handleSelectPromptForChat = (promptText) => {
    setSelectedPrompt(promptText);
    setActiveTab('chat');
  };

  const handleInvestigateAlert = (alertItem) => {
    if (currentUser?.role !== 'customer' && alertItem.customer_id) {
      setCustomerId(alertItem.customer_id);
    }
    const query = `Investigate alert: ${alertItem.title || alertItem.message || 'Suspicious payment activity'}`;
    handleSelectPromptForChat(query);
  };

  const handleRefreshAll = () => {
    fetchGlobalState();
    setRefreshKey((k) => k + 1);
  };

  // 1. Initial Authentication Gate: If unauthenticated, show ONLY the Login Page!
  if (authLoading) {
    return (
      <div className="login-screen-wrapper">
        <div className="login-card-container font-mono" style={{ textAlign: 'center', padding: '3rem' }}>
          <p>Verifying secure banking session...</p>
        </div>
      </div>
    );
  }

  if (!currentUser) {
    return <LoginPage onLoginSuccess={handleLoginSuccess} />;
  }

  // 2. Authenticated Experience (Role-Separated)
  const isSupervisor = role === 'supervisor' || role === 'rm';
  const effectiveCustomerId = isSupervisor ? customerId : (currentUser.customer_id || 'C001');

  return (
    <div className="app-wrapper">
      {/* Top Navbar & Header Controls */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        customerId={effectiveCustomerId}
        setCustomerId={setCustomerId}
        role={role}
        llmStatus={llmStatus}
        onToggleLlm={handleToggleLlm}
        alertsCount={alerts.length}
        onOpenAlerts={() => setAlertsOpen(true)}
        pendingApprovalsCount={pendingApprovalsCount}
        onRefreshAll={handleRefreshAll}
        currentUser={currentUser}
        onLogout={handleLogout}
      />

      {/* Main Viewport */}
      <main className="main-content">
        <div style={{ display: activeTab === 'chat' ? 'block' : 'none', height: '100%' }}>
          <ChatView
            customerId={effectiveCustomerId}
            role={role}
            onRequestCustomerRefresh={fetchGlobalState}
            injectedPrompt={selectedPrompt}
            onClearInjectedPrompt={() => setSelectedPrompt(null)}
          />
        </div>

        {activeTab === 'customer' && (
          <CustomerView
            key={`cust-${effectiveCustomerId}-${refreshKey}`}
            customerId={effectiveCustomerId}
            role={role}
            onSelectPromptForChat={handleSelectPromptForChat}
          />
        )}
      </main>

      {/* Real-time Alerts Drawer */}
      <AlertsDrawer
        isOpen={alertsOpen}
        onClose={() => setAlertsOpen(false)}
        alerts={alerts}
        onRefresh={fetchGlobalState}
        onInvestigateAlert={handleInvestigateAlert}
      />
    </div>
  );
}
