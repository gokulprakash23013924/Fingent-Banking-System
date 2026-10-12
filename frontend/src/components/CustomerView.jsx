import React, { useState, useEffect } from 'react';
import { 
  User, 
  CreditCard, 
  Wallet, 
  ShieldCheck, 
  ShieldAlert, 
  Clock, 
  ArrowUpRight, 
  ArrowDownLeft, 
  RefreshCw, 
  AlertTriangle,
  FileCheck,
  CheckCircle,
  HelpCircle
} from 'lucide-react';
import { api } from '../api';

export default function CustomerView({ 
  customerId, 
  role, 
  onSelectPromptForChat 
}) {
  const [customer, setCustomer] = useState(null);
  const [bureau, setBureau] = useState(null);
  const [kyc, setKyc] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [selectedAccountId, setSelectedAccountId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [riskScores, setRiskScores] = useState({});

  const fetchCustomerData = async () => {
    setLoading(true);
    setError(null);
    try {
      const custData = await api.getCustomer(customerId);
      setCustomer(custData);

      // Default to first account
      const firstAccId = custData.accounts?.[0]?.account_id;
      setSelectedAccountId(firstAccId);

      // Fetch Bureau score
      try {
        const bureauData = await api.getBureauScore(customerId);
        setBureau(bureauData);
      } catch (e) {
        console.warn('Bureau score not found or error:', e);
      }

      // Fetch KYC
      try {
        const kycData = await api.getKyc(customerId);
        setKyc(kycData);
      } catch (e) {
        console.warn('KYC not found or error:', e);
      }

      // Fetch transactions for primary account
      if (firstAccId) {
        fetchTransactionsForAccount(firstAccId);
      }
    } catch (err) {
      setError(err.message || 'Failed to load customer profile');
    } finally {
      setLoading(false);
    }
  };

  const fetchTransactionsForAccount = async (accId) => {
    try {
      const txns = await api.getTransactions(accId, 15);
      setTransactions(txns);

      // Fetch risk scores for transactions
      txns.slice(0, 8).forEach(async (t) => {
        try {
          const risk = await api.getTxnRisk(t.txn_id);
          setRiskScores((prev) => ({ ...prev, [t.txn_id]: risk }));
        } catch (e) {
          // ignore individual risk fetch errors
        }
      });
    } catch (err) {
      console.warn('Failed to load transactions for account:', accId, err);
    }
  };

  useEffect(() => {
    fetchCustomerData();
  }, [customerId]);

  const handleAccountChange = (accId) => {
    setSelectedAccountId(accId);
    fetchTransactionsForAccount(accId);
  };

  const formatRupees = (amount) => {
    if (amount === undefined || amount === null) return '₹0';
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0,
    }).format(amount);
  };

  if (loading) {
    return (
      <div className="customer-view-container loading-state">
        <div className="agent-avatar-badge spinning">
          <RefreshCw size={24} />
        </div>
        <p className="font-mono text-muted">Retrieving Customer 360 & Core Ledger records...</p>
      </div>
    );
  }

  if (error || !customer) {
    return (
      <div className="customer-view-container error-state">
        <AlertTriangle size={32} className="text-warning" />
        <h3>Unable to load customer profile</h3>
        <p className="text-muted">{error}</p>
        <button type="button" className="btn btn-secondary" onClick={fetchCustomerData}>
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="customer-view-container fade-in">
      {/* Top Profile Summary Bar */}
      <div className="customer-hero-card glass-panel">
        <div className="hero-left">
          <div className="customer-avatar-large">
            <User size={32} />
          </div>
          <div>
            <div className="name-row">
              <h2>{customer.name}</h2>
              <span className="badge badge-neutral font-mono">{customer.customer_id}</span>
              <span className="badge badge-info">{customer.segment}</span>
            </div>
            <p className="customer-sub-info">
              {customer.city}, {customer.home_country || 'IN'} · Monthly Income: <strong>{formatRupees(customer.income)}</strong>
            </p>
          </div>
        </div>

        <div className="hero-stats">
          {/* Bureau Credit Score */}
          <div className="hero-stat-box">
            <span className="stat-label">CIBIL Bureau Score</span>
            <div className="stat-value-row">
              <span className={`bureau-score ${bureau?.score >= 750 ? 'excellent' : bureau?.score >= 650 ? 'good' : 'poor'}`}>
                {bureau?.score || 'N/A'}
              </span>
              <span className="score-band">
                {bureau?.score >= 750 ? 'Super Prime' : bureau?.score >= 650 ? 'Standard' : 'Subprime'}
              </span>
            </div>
          </div>

          {/* KYC Status */}
          <div className="hero-stat-box">
            <span className="stat-label">KYC Verification</span>
            <div className="stat-value-row">
              <span className={`badge ${kyc?.status === 'verified' ? 'badge-success' : kyc?.status === 'pending' ? 'badge-warning' : 'badge-danger'}`}>
                {kyc?.status === 'verified' ? <CheckCircle size={12} /> : <AlertTriangle size={12} />}
                {kyc?.status?.toUpperCase() || 'UNKNOWN'}
              </span>
            </div>
          </div>

          {/* AML Risk (Revealed in RM role) */}
          <div className="hero-stat-box">
            <span className="stat-label">Compliance / AML</span>
            <div className="stat-value-row">
              {role === 'rm' ? (
                customer.customer_id === 'C010' ? (
                  <span className="badge badge-danger">FLAGGED (PEP / High Risk)</span>
                ) : (
                  <span className="badge badge-success">CLEAN SCREENING</span>
                )
              ) : (
                <span className="badge badge-neutral">Standard</span>
              )}
            </div>
          </div>

          <button 
            type="button" 
            className="icon-action-btn"
            onClick={fetchCustomerData}
            title="Refresh Ledger"
          >
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      {/* Accounts & Cards Grid */}
      <div className="accounts-cards-grid">
        {/* Accounts Card Column */}
        <div className="dashboard-column">
          <div className="section-header-row">
            <div className="section-title">
              <Wallet size={18} className="text-cyan" />
              <h3>Ledger Accounts ({customer.accounts?.length || 0})</h3>
            </div>
          </div>

          <div className="accounts-list">
            {customer.accounts?.map((acc) => (
              <div 
                key={acc.account_id}
                className={`account-card glass-panel ${selectedAccountId === acc.account_id ? 'active-account' : ''}`}
                onClick={() => handleAccountChange(acc.account_id)}
              >
                <div className="acc-top">
                  <div>
                    <span className="acc-type font-mono">{acc.type?.toUpperCase()} ACCOUNT</span>
                    <h4 className="acc-id font-mono">{acc.account_id}</h4>
                  </div>
                  <span className={`badge ${acc.status === 'active' ? 'badge-success' : 'badge-danger'}`}>
                    {acc.status}
                  </span>
                </div>
                <div className="acc-balance-row">
                  <span className="balance-label">Available Balance</span>
                  <span className="balance-amount font-mono">{formatRupees(acc.balance)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Cards Column */}
        <div className="dashboard-column">
          <div className="section-header-row">
            <div className="section-title">
              <CreditCard size={18} className="text-primary" />
              <h3>Payment Cards ({customer.cards?.length || 0})</h3>
            </div>
          </div>

          <div className="cards-list">
            {customer.cards?.map((card) => (
              <div key={card.card_id} className={`card-item glass-panel ${card.status === 'blocked' ? 'blocked-card' : ''}`}>
                <div className="card-item-top">
                  <span className="card-id-tag font-mono">{card.card_id}</span>
                  <span className={`badge ${card.status === 'active' ? 'badge-success' : 'badge-danger'}`}>
                    {card.status === 'active' ? 'ACTIVE' : 'BLOCKED / FROZEN'}
                  </span>
                </div>
                <div className="card-number font-mono">
                  •••• •••• •••• {card.last4}
                </div>
                <div className="card-footer">
                  <div>
                    <span className="text-muted font-sm">Credit / Daily Limit:</span>
                    <strong className="font-mono"> {formatRupees(card.limit)}</strong>
                  </div>
                  {card.status === 'active' && onSelectPromptForChat && (
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => onSelectPromptForChat(`Block card ending ${card.last4}`)}
                    >
                      Block Card
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Active Loans & Credit Facilities */}
      {customer.loans && customer.loans.length > 0 && (
        <div className="loans-section glass-panel" style={{ marginBottom: '1.5rem', padding: '1.25rem' }}>
          <div className="section-header-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div className="section-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <FileCheck size={18} className="text-cyan" />
              <h3>Active Loans & Credit Facilities ({customer.loans.length})</h3>
            </div>
            <span className="badge badge-tier0 font-mono">Underwritten & Approved</span>
          </div>

          <div className="loans-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1rem', marginTop: '1rem' }}>
            {customer.loans.map((loan) => (
              <div key={loan.app_id} className="loan-card glass-panel" style={{ padding: '1rem', borderLeft: '3px solid #10b981' }}>
                <div className="acc-top" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <span className="acc-type font-mono text-muted" style={{ fontSize: '0.75rem' }}>FACILITY ID</span>
                    <h4 className="acc-id font-mono text-cyan" style={{ margin: '2px 0' }}>{loan.app_id}</h4>
                  </div>
                  <span className={`badge ${loan.status === 'approved' ? 'badge-success' : 'badge-warning'}`}>
                    {loan.status?.toUpperCase()}
                  </span>
                </div>
                <div style={{ marginTop: '0.75rem', display: 'flex', justifyContent: 'space-between' }}>
                  <span className="text-muted font-sm">Principal Amount:</span>
                  <strong className="font-mono text-emerald">{formatRupees(loan.amount)}</strong>
                </div>
                <div style={{ marginTop: '0.25rem', display: 'flex', justifyContent: 'space-between' }}>
                  <span className="text-muted font-sm">Monthly EMI:</span>
                  <strong className="font-mono">{formatRupees(loan.emi)} / mo</strong>
                </div>
                <div style={{ marginTop: '0.25rem', display: 'flex', justifyContent: 'space-between' }}>
                  <span className="text-muted font-sm">Tenure & Rate:</span>
                  <span className="font-mono font-sm">{loan.tenure_months} mos @ {loan.rate || 10.5}% p.a.</span>
                </div>
                <div style={{ marginTop: '0.5rem', fontSize: '0.72rem', color: '#94a3b8' }}>
                  Reason: {loan.decision_reason || 'Underwriting approved'}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent Ledger Transactions */}
      <div className="transactions-section glass-panel">
        <div className="section-header-row">
          <div className="section-title">
            <Clock size={18} className="text-emerald" />
            <h3>Recent Transactions · Account <span className="font-mono">{selectedAccountId}</span></h3>
          </div>
          <span className="text-muted font-sm font-mono">Real-time IsolationForest risk scoring</span>
        </div>

        <div className="table-responsive">
          <table className="transactions-table font-mono">
            <thead>
              <tr>
                <th>Txn ID</th>
                <th>Timestamp</th>
                <th>Merchant / Description</th>
                <th>Channel / City</th>
                <th>Amount</th>
                <th>Fraud Risk</th>
                <th>AI Action</th>
              </tr>
            </thead>
            <tbody>
              {transactions.length > 0 ? (
                transactions.map((txn) => {
                  const risk = riskScores[txn.txn_id];
                  const isHighRisk = risk?.risk_score >= 70 || txn.amount >= 45000;
                  return (
                    <tr key={txn.txn_id} className={isHighRisk ? 'highlight-row' : ''}>
                      <td>
                        <span className="txn-id-pill">{txn.txn_id}</span>
                      </td>
                      <td className="text-muted">{txn.ts ? new Date(txn.ts).toLocaleDateString() : (txn.timestamp || 'Recent')}</td>
                      <td>
                        <strong>{txn.merchant || txn.description || 'Transfer'}</strong>
                        {txn.merchant?.includes('RAZORPAY') && (
                          <span className="badge badge-tier0 font-mono" style={{ marginLeft: '6px', fontSize: '0.68rem', padding: '1px 6px' }}>Razorpay P2P</span>
                        )}
                        {txn.category && <span className="cat-pill">{txn.category}</span>}
                      </td>
                      <td className="text-muted">
                        {txn.channel || 'online'} · {txn.country || txn.city || 'Domestic'}
                      </td>
                      <td className="amount-cell">
                        <span className={txn.type === 'debit' || txn.amount < 0 ? 'text-rose' : 'text-emerald'}>
                          {txn.type === 'debit' ? '- ' : txn.type === 'credit' ? '+ ' : ''}{formatRupees(txn.amount)}
                        </span>
                      </td>
                      <td>
                        {risk ? (
                          <span className={`badge ${risk.risk_score >= 70 ? 'badge-danger' : risk.risk_score >= 30 ? 'badge-warning' : 'badge-success'}`}>
                            {risk.risk_score}/100 {risk.risk_score >= 70 ? 'ANOMALOUS' : 'NORMAL'}
                          </span>
                        ) : (
                          <span className="badge badge-neutral">Scored</span>
                        )}
                      </td>
                      <td>
                        {onSelectPromptForChat && (
                          <button
                            type="button"
                            className="btn btn-ghost btn-sm"
                            title="Investigate in AI Assistant"
                            onClick={() => onSelectPromptForChat(`I did not make this ${formatRupees(txn.amount)} payment at ${txn.merchant || txn.description}`)}
                          >
                            <ShieldAlert size={14} className="text-warning" />
                            <span>Inquire</span>
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan="7" className="empty-cell text-muted">
                    No transactions found for this account.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
