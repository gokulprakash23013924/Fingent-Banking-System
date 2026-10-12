import React, { useState, useEffect } from 'react';
import { 
  Shield, 
  ShieldCheck, 
  ShieldAlert, 
  CheckCircle2, 
  XCircle, 
  RefreshCw, 
  Lock, 
  ArrowRight,
  Filter,
  UserCheck,
  AlertCircle
} from 'lucide-react';
import { api } from '../api';

export default function ApprovalsView({ 
  customerId, 
  role, 
  onApprovalDecided,
  onRequestCustomerRefresh 
}) {
  const [approvalsList, setApprovalsList] = useState([]);
  const [filterCustomer, setFilterCustomer] = useState(role === 'customer');
  const [loading, setLoading] = useState(false);
  const [decisionState, setDecisionState] = useState({});
  const [lastRefreshed, setLastRefreshed] = useState(new Date());

  useEffect(() => {
    setFilterCustomer(role === 'customer');
  }, [role]);

  const fetchApprovals = async () => {
    setLoading(true);
    try {
      const data = await api.getPendingApprovals(filterCustomer ? customerId : null);
      setApprovalsList(Array.isArray(data) ? data : []);
      setLastRefreshed(new Date());
    } catch (err) {
      console.error('Failed to load pending approvals:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchApprovals();
    const interval = setInterval(fetchApprovals, 6000);
    return () => clearInterval(interval);
  }, [customerId, filterCustomer]);

  const handleDecision = async (group, approve) => {
    const groupId = group.group_id;
    setDecisionState((prev) => ({ ...prev, [groupId]: { loading: true } }));

    try {
      const res = await api.decideApproval(groupId, {
        approve,
        customer_id: group.customer_id || customerId,
        role,
      });

      setDecisionState((prev) => ({
        ...prev,
        [groupId]: {
          loading: false,
          decided: true,
          status: res.status,
          approved: approve,
          message: res.answer,
        },
      }));

      // Refresh list after brief delay
      setTimeout(fetchApprovals, 1500);
      if (onApprovalDecided) onApprovalDecided();
      if (onRequestCustomerRefresh) onRequestCustomerRefresh();
    } catch (err) {
      alert(`Approval decision failed: ${err.message}`);
      setDecisionState((prev) => ({ ...prev, [groupId]: { loading: false, error: err.message } }));
    }
  };

  return (
    <div className="approvals-view-container fade-in">
      {/* View Header */}
      <div className="view-header-bar glass-panel">
        <div>
          <div className="view-title-row">
            <ShieldAlert size={22} className="text-warning" />
            <h2>Human-in-the-Loop Approvals Gate</h2>
            <span className="badge badge-warning font-mono">
              {approvalsList.length} PENDING ACTION{approvalsList.length !== 1 ? 'S' : ''}
            </span>
          </div>
          <p className="text-muted">
            All write tools (e.g. <code>block_card</code>, <code>create_dispute</code>, <code>create_loan_application</code>, transfers &ge; ₹50,000) are proposed first and held here. No LLM or agent can execute money writes without explicit cryptographic human confirmation.
          </p>
        </div>

        <div className="view-header-actions">
          {/* Customer vs All filter */}
          <div className="filter-toggle-box">
            <button
              type="button"
              className={`filter-btn ${!filterCustomer ? 'active' : ''}`}
              onClick={() => setFilterCustomer(false)}
            >
              All Bank Approvals
            </button>
            <button
              type="button"
              className={`filter-btn ${filterCustomer ? 'active' : ''}`}
              onClick={() => setFilterCustomer(true)}
            >
              Current Persona ({customerId})
            </button>
          </div>

          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={fetchApprovals}
            disabled={loading}
          >
            <RefreshCw size={14} className={loading ? 'spinning' : ''} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Approvals Cards Stream */}
      <div className="approvals-grid">
        {approvalsList.length > 0 ? (
          approvalsList.map((appr) => {
            const decision = decisionState[appr.group_id];
            return (
              <div key={appr.group_id} className="approval-gate-card glass-panel-elevated">
                <div className="card-top-row">
                  <div className="appr-id-badge">
                    <Lock size={14} className="text-warning" />
                    <span className="font-mono">{appr.group_id}</span>
                  </div>
                  <div className="appr-customer-pill font-mono">
                    Customer: <strong>{appr.customer_id}</strong>
                  </div>
                </div>

                <h3 className="appr-desc-heading">{appr.description}</h3>

                {/* Actions breakdown */}
                <div className="appr-actions-breakdown">
                  <span className="breakdown-label font-mono">PENDING TOOL INVOCATIONS:</span>
                  {appr.actions?.map((act, idx) => (
                    <div key={idx} className="tool-invocation-row font-mono">
                      <span className="tool-badge">{act.tool}</span>
                      <span className="tool-summary-text">{act.summary}</span>
                      {act.args && (
                        <div className="tool-args-box">
                          {JSON.stringify(act.args, null, 2)}
                        </div>
                      )}
                    </div>
                  ))}
                </div>

                {/* Decision UI */}
                {decision?.decided ? (
                  <div className={`decision-result-banner ${decision.approved ? 'approved' : 'rejected'}`}>
                    {decision.approved ? (
                      <>
                        <CheckCircle2 size={18} />
                        <div>
                          <strong>Tool Executed Successfully</strong>
                          <p className="font-mono text-sm">{decision.message}</p>
                        </div>
                      </>
                    ) : (
                      <>
                        <XCircle size={18} />
                        <div>
                          <strong>Action Rejected</strong>
                          <p className="text-sm">Write request discarded.</p>
                        </div>
                      </>
                    )}
                  </div>
                ) : (
                  <div className="appr-decision-footer">
                    <button
                      id={`btn-gate-approve-${appr.group_id}`}
                      type="button"
                      className="btn btn-success"
                      disabled={decision?.loading}
                      onClick={() => handleDecision(appr, true)}
                    >
                      <CheckCircle2 size={16} />
                      <span>Approve & Execute Tool</span>
                    </button>
                    <button
                      id={`btn-gate-reject-${appr.group_id}`}
                      type="button"
                      className="btn btn-danger"
                      disabled={decision?.loading}
                      onClick={() => handleDecision(appr, false)}
                    >
                      <XCircle size={16} />
                      <span>Reject & Cancel</span>
                    </button>
                  </div>
                )}
              </div>
            );
          })
        ) : (
          <div className="empty-approvals-card glass-panel">
            <ShieldCheck size={48} className="text-emerald" />
            <h3>No Actions Pending Approval</h3>
            <p className="text-muted">
              All write tools have been resolved or executed. When an agent proposes a card block, loan application, or dispute in the chat, it will instantly appear in this gate.
            </p>
            <div className="test-prompt-hint">
              <span className="font-mono">Tip to test:</span> Switch to customer <code>C002</code> in Chat and send:
              <em> "I did not make this ₹48,000 payment"</em>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
