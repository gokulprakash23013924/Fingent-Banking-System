import React, { useState, useEffect, useRef } from 'react';
import { 
  Send, 
  Sparkles, 
  ShieldCheck, 
  ShieldAlert, 
  Clock, 
  Terminal, 
  CheckCircle2, 
  XCircle, 
  ChevronDown, 
  ChevronUp, 
  Zap, 
  Bot, 
  User, 
  Wallet, 
  CreditCard,
  AlertCircle,
  FileText,
  RotateCcw,
  Info,
  HelpCircle,
  CheckCircle,
  Activity,
  Layers,
  ArrowRight
} from 'lucide-react';
import { api } from '../api';
import { formatMessageText } from '../utils/formatText';

const CUSTOMER_PROMPTS = {
  C001: [
    "What is my balance?",
    "Show my last 5 transactions",
    "Can I get a loan of 5 lakh for 3 years?",
    "Apply for a loan of 5 lakh for 3 years",
    "Transfer 500 to A1003",
  ],
  C002: [
    "I did not make this ₹48,000 payment",
    "What is my balance?",
    "Check my card status",
    "Show my alerts",
  ],
  C003: [
    "Apply for a loan of 5 lakh",
    "Why was my loan declined?",
    "What is my credit score?",
    "Calculate EMI for 2 lakh for 2 years",
  ],
  C004: [
    "Is my KYC up to date?",
    "Apply for a loan of 5 lakh for 3 years",
    "Transfer 60000 to A1002",
    "What is my balance?",
  ],
  C005: [
    "Can I get a loan of 5 lakh for 3 years?",
    "Calculate EMI for 5 lakh for 3 years",
    "Why was my loan declined?",
    "What are my loan offers?",
  ],
  C006: [
    "Assess my recent transaction risk",
    "Can I apply for a loan of 2 lakh?",
    "Show my last 5 transactions",
    "Check my card status",
  ],
  C009: [
    "Is my KYC up to date?",
    "Apply for a loan of 3 lakh",
    "Transfer 5000 to A1001",
  ],
  C010: [
    "Check my KYC status and compliance",
    "Transfer 20000 to A1001",
    "Show my alerts",
  ],
};

const GENERAL_PROMPTS = [
  "Can I get a loan? I also see a transaction I don't recognize",
  "Invest my savings in mutual funds",
  "asdf",
];

export default function ChatView({ 
  customerId, 
  role, 
  onApprovalDecided,
  onRequestCustomerRefresh,
  injectedPrompt,
  onClearInjectedPrompt
}) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const [expandedTraceId, setExpandedTraceId] = useState(null);
  const [approvalDecisions, setApprovalDecisions] = useState({});
  const [customerSnapshot, setCustomerSnapshot] = useState(null);
  const [lastTelemetry, setLastTelemetry] = useState(null);
  const messagesEndRef = useRef(null);

  // Fetch quick snapshot for active customer sidebar
  useEffect(() => {
    let isMounted = true;
    async function loadSnapshot() {
      try {
        const cust = await api.getCustomer(customerId);
        if (isMounted) setCustomerSnapshot(cust);
      } catch (e) {
        console.warn('Failed to load snapshot for sidebar:', e);
      }
    }
    loadSnapshot();
    return () => { isMounted = false; };
  }, [customerId]);

  const storageKey = `fingent_chat_${customerId}_${role}`;
  const convKey = `fingent_conv_${customerId}_${role}`;

  // Initialize or restore messages for the active session
  useEffect(() => {
    try {
      const saved = sessionStorage.getItem(storageKey);
      const savedConv = sessionStorage.getItem(convKey);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) {
          setMessages(parsed);
          setConversationId(savedConv || `conv-${customerId}-${Date.now()}`);
          return;
        }
      }
    } catch (e) {
      console.warn('Failed to restore saved chat from sessionStorage:', e);
    }

    const initMsgs = [
      {
        id: 'init-msg',
        role: 'system',
        text: `Welcome! Active Persona: **${customerId}** (${role === 'rm' ? 'Relationship Manager mode' : 'Customer mode'}). You can ask about account balances, send money via Razorpay, card controls, loan eligibility & EMI, or report unauthorised transactions.`,
        timestamp: new Date().toLocaleTimeString(),
      }
    ];
    setMessages(initMsgs);
    const newConvId = `conv-${customerId}-${Date.now()}`;
    setConversationId(newConvId);
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(initMsgs));
      sessionStorage.setItem(convKey, newConvId);
    } catch (e) {}
  }, [customerId, role, storageKey, convKey]);

  // Persist messages to sessionStorage whenever they update
  useEffect(() => {
    if (messages.length > 0) {
      try {
        sessionStorage.setItem(storageKey, JSON.stringify(messages));
      } catch (e) {}
    }
  }, [messages, storageKey]);

  // Handle injected prompt from other tabs or alerts
  useEffect(() => {
    if (injectedPrompt) {
      handleSend(injectedPrompt);
      if (onClearInjectedPrompt) onClearInjectedPrompt();
    }
  }, [injectedPrompt]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleSend = async (messageText = input) => {
    const textToSend = (messageText || '').trim();
    if (!textToSend || loading) return;

    const userMsgId = `user-${Date.now()}`;
    const userMsg = {
      id: userMsgId,
      role: 'user',
      text: textToSend,
      timestamp: new Date().toLocaleTimeString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const response = await api.chat({
        message: textToSend,
        customer_id: customerId,
        role: role,
        conversation_id: conversationId,
      });

      const botMsgId = `bot-${Date.now()}`;
      const botMsg = {
        id: botMsgId,
        role: 'agent',
        text: response.answer,
        status: response.status,
        workflowState: response.workflow_state || response.execution_summary?.workflow_state || 'COMPLETED',
        executionSummary: response.execution_summary,
        agents: response.execution_summary?.think?.required_agents || (response.agent ? [response.agent] : ['supervisor']),
        tools: response.execution_summary?.act || [],
        latencyMs: response.execution_summary?.latency_ms,
        approval: response.approval,
        traceId: response.trace_id,
        trace: response.trace,
        data: response.data,
        timestamp: new Date().toLocaleTimeString(),
      };

      setMessages((prev) => [...prev, botMsg]);
      setLastTelemetry(botMsg);

      // If approval required, notify parent
      if (response.approval && onApprovalDecided) {
        onApprovalDecided();
      }
      if (onRequestCustomerRefresh) {
        onRequestCustomerRefresh();
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: 'agent',
          error: true,
          text: `⚠️ Request failed: ${err.message || 'Unable to connect to banking core'}. Ensure the backend is active at http://127.0.0.1:8000.`,
          timestamp: new Date().toLocaleTimeString(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleApprovalAction = async (groupId, approve, botMsgId) => {
    setApprovalDecisions((prev) => ({ ...prev, [groupId]: { loading: true } }));

    try {
      const result = await api.decideApproval(groupId, {
        approve,
        customer_id: customerId,
        role,
      });

      setApprovalDecisions((prev) => ({
        ...prev,
        [groupId]: {
          decided: true,
          status: result.status,
          approved: approve,
          executed: result.executed,
          answer: result.answer,
        },
      }));

      // Append confirmation message to chat
      setMessages((prev) => [
        ...prev,
        {
          id: `approval-res-${Date.now()}`,
          role: 'system',
          text: approve 
            ? `✅ Human-in-the-Loop Gate: Approval group \`${groupId}\` was **APPROVED** and executed. ${result.answer || ''}`
            : `❌ Human-in-the-Loop Gate: Approval group \`${groupId}\` was **REJECTED**. No tools were executed.`,
          timestamp: new Date().toLocaleTimeString(),
        }
      ]);

      if (onApprovalDecided) onApprovalDecided();
      if (onRequestCustomerRefresh) onRequestCustomerRefresh();
    } catch (err) {
      alert(`Approval error: ${err.message}`);
      setApprovalDecisions((prev) => ({ ...prev, [groupId]: { loading: false, error: err.message } }));
    }
  };

  const getWorkflowBadge = (msg) => {
    const state = msg.workflowState || (
      msg.status === 'awaiting_approval' ? 'AWAITING_APPROVAL' :
      msg.status === 'needs_clarification' ? 'NEEDS_CLARIFICATION' :
      msg.status === 'escalated' ? 'ESCALATED' :
      msg.status === 'error' || msg.status === 'failed' ? 'FAILED' : 'COMPLETED'
    );
    const latencyMs = msg.latencyMs;

    switch (state) {
      case 'COMPLETED':
      case 'ok':
        return (
          <span className="badge badge-tier0 font-mono" title="Workflow Completed: Tasks executed, verified against database, policies satisfied.">
            <CheckCircle2 size={12} /> COMPLETED {latencyMs ? `· ${latencyMs.toFixed(1)}ms` : ''}
          </span>
        );
      case 'AWAITING_APPROVAL':
        return (
          <span className="badge badge-warning font-mono" title="Awaiting Approval: Sensitive financial write action requires user authorization.">
            <ShieldAlert size={12} /> AWAITING APPROVAL
          </span>
        );
      case 'NEEDS_CLARIFICATION':
        return (
          <span className="badge badge-tier1 font-mono" title="Needs Clarification: Required slot missing or goal ambiguous. Grounding safety engaged.">
            <HelpCircle size={12} /> NEEDS CLARIFICATION
          </span>
        );
      case 'ESCALATED':
        return (
          <span className="badge badge-tier2 font-mono" title="Escalated: Out of scope request escalated to human Relationship Manager.">
            <ArrowRight size={12} /> ESCALATED TO RM
          </span>
        );
      case 'RECOVERING':
        return (
          <span className="badge badge-warning font-mono" title="Recovering: Self-correction loop active. Safe bounded retry.">
            <RotateCcw size={12} /> RECOVERING
          </span>
        );
      case 'VALIDATING':
        return (
          <span className="badge badge-tier1 font-mono" title="Validating: Evaluating tool outputs against deterministic policies.">
            <CheckCircle size={12} /> VALIDATING
          </span>
        );
      case 'FAILED':
      case 'error':
        return (
          <span className="badge badge-danger font-mono" title="Failed: Workflow halted safely to prevent erroneous financial execution.">
            <XCircle size={12} /> FAILED
          </span>
        );
      default:
        return (
          <span className="badge badge-neutral font-mono">
            {state} {latencyMs ? `· ${latencyMs.toFixed(1)}ms` : ''}
          </span>
        );
    }
  };

  const currentPrompts = CUSTOMER_PROMPTS[customerId] || CUSTOMER_PROMPTS.C001;

  const formatRupees = (amount) => {
    if (amount === undefined || amount === null) return '₹0';
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0,
    }).format(amount);
  };

  return (
    <div className="chat-layout-split">
      {/* Main Chat Stream Area */}
      <div className="chat-main-column">
        {/* Messages Stream */}
        <div className="chat-messages-scroll">
          {messages.map((msg) => (
            <div key={msg.id} className={`message-row ${msg.role}`}>
              {msg.role === 'user' ? (
                <div className="user-avatar-badge">
                  <User size={16} />
                </div>
              ) : msg.role === 'agent' ? (
                <div className="agent-avatar-badge">
                  <ShieldCheck size={18} />
                </div>
              ) : (
                <div className="system-avatar-badge">
                  <Info size={14} />
                </div>
              )}

              <div className={`message-bubble ${msg.role} ${msg.error ? 'error-bubble' : ''}`}>
                {/* Message Header (for agent responses) */}
                {msg.role === 'agent' && !msg.error && (
                  <div className="message-meta-header">
                    <div className="agent-badges-group">
                      {msg.agents?.length > 0 ? (
                        msg.agents.map((ag) => (
                          <span key={ag} className="agent-pill">
                            {ag}
                          </span>
                        ))
                      ) : (
                        <span className="agent-pill">supervisor</span>
                      )}
                    </div>

                    <div className="tier-latency-group">
                      {getWorkflowBadge(msg)}
                    </div>
                  </div>
                )}

                {/* Message Body Content formatted with markdown/rupees */}
                <div className="message-text">
                  {formatMessageText(msg.text)}
                </div>

                {/* Optional LLM Explanation for loan underwriting */}
                {msg.explanation && (
                  <div className="explanation-callout">
                    <div className="explanation-title">
                      <Sparkles size={13} />
                      <span>LLM Synthesis (Grounding Verified):</span>
                    </div>
                    <p>{msg.explanation}</p>
                  </div>
                )}

                {/* Interactive Human Approval Card */}
                {msg.approval && (
                  <div className="approval-card glass-panel-elevated">
                    <div className="approval-card-header">
                      <div className="approval-title-box">
                        <ShieldAlert size={18} className="text-warning" />
                        <div>
                          <h4>Approval Gate Triggered</h4>
                          <span className="approval-id-tag font-mono">{msg.approval.group_id}</span>
                        </div>
                      </div>
                      <span className="badge badge-warning">Awaiting Decision</span>
                    </div>

                    <p className="approval-description">{msg.approval.description}</p>

                    <div className="approval-actions-list">
                      {msg.approval.actions?.map((act, i) => (
                        <div key={i} className="approval-action-item">
                          <span className="action-tool font-mono">{act.tool}</span>
                          <span className="action-summary">{act.summary}</span>
                          {act.args && (
                            <div className="action-args font-mono">
                              {JSON.stringify(act.args)}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>

                    {/* Actions or Decision Status */}
                    {approvalDecisions[msg.approval.group_id]?.decided ? (
                      <div className={`approval-decided-banner ${approvalDecisions[msg.approval.group_id].approved ? 'approved' : 'rejected'}`}>
                        {approvalDecisions[msg.approval.group_id].approved ? (
                          <>
                            <CheckCircle2 size={16} />
                            <span>Approved & Executed successfully</span>
                          </>
                        ) : (
                          <>
                            <XCircle size={16} />
                            <span>Action was rejected by user</span>
                          </>
                        )}
                      </div>
                    ) : (
                      <div className="approval-btn-row">
                        <button
                          id={`btn-approve-${msg.approval.group_id}`}
                          type="button"
                          className="btn btn-success btn-sm"
                          disabled={approvalDecisions[msg.approval.group_id]?.loading}
                          onClick={() => handleApprovalAction(msg.approval.group_id, true, msg.id)}
                        >
                          <CheckCircle2 size={15} />
                          <span>Confirm & Execute Write Tool</span>
                        </button>
                        <button
                          id={`btn-reject-${msg.approval.group_id}`}
                          type="button"
                          className="btn btn-danger btn-sm"
                          disabled={approvalDecisions[msg.approval.group_id]?.loading}
                          onClick={() => handleApprovalAction(msg.approval.group_id, false, msg.id)}
                        >
                          <XCircle size={15} />
                          <span>Reject</span>
                        </button>
                      </div>
                    )}
                  </div>
                )}

                {/* Observe–Think–Act Execution Summary Accordion */}
                {msg.traceId && (
                  <div className="trace-accordion-wrapper">
                    <button
                      type="button"
                      className="trace-toggle-btn"
                      onClick={() => setExpandedTraceId(expandedTraceId === msg.traceId ? null : msg.traceId)}
                    >
                      <Terminal size={13} />
                      <span>Observe–Think–Act Execution Summary ({msg.traceId})</span>
                      {expandedTraceId === msg.traceId ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </button>

                    {expandedTraceId === msg.traceId && (
                      <div className="trace-details-panel font-mono">
                        {/* 1. OBSERVE */}
                        <div className="trace-section">
                          <div className="trace-sec-title">👁️ 1. OBSERVE — INTENT & ENTITY EXTRACTION</div>
                          <div className="trace-sec-body">
                            <div>Goal: <strong className="text-cyan">{msg.executionSummary?.observe?.goal || 'Understand user goal'}</strong></div>
                            <div className="trace-sub-row">
                              → Intent: <code>{msg.executionSummary?.observe?.intent || 'classified'}</code>
                            </div>
                            {msg.executionSummary?.observe?.entities && Object.keys(msg.executionSummary.observe.entities).length > 0 && (
                              <div className="trace-sub-row">
                                → Entities: <code>{JSON.stringify(msg.executionSummary.observe.entities)}</code>
                              </div>
                            )}
                          </div>
                        </div>

                        {/* 2. THINK */}
                        <div className="trace-section">
                          <div className="trace-sec-title">🧠 2. THINK — DYNAMIC TASK PLAN & POLICY GATES</div>
                          <div className="trace-sec-body">
                            <div>Assigned Agents: <strong className="text-violet">[{msg.executionSummary?.think?.required_agents?.join(', ') || 'supervisor'}]</strong></div>
                            <div className="trace-sub-row">
                              → Parallel Underwriting: {msg.executionSummary?.think?.parallel_groups?.length > 0 ? (
                                <span className="text-emerald">ENABLED (Credit, Fraud & Compliance concurrently)</span>
                              ) : (
                                <span>Sequential Workflow</span>
                              )}
                            </div>
                            <div className="trace-sub-row">
                              → Approval Gate: {msg.executionSummary?.think?.approval_required ? (
                                <span className="text-warning">REQUIRED (Sensitive financial write action)</span>
                              ) : (
                                <span className="text-muted">None (Read-only query)</span>
                              )}
                            </div>
                          </div>
                        </div>

                        {/* 3. ACT */}
                        <div className="trace-section">
                          <div className="trace-sec-title">⚡ 3. ACT — AUTHORIZED TOOL EXECUTION</div>
                          <div className="trace-sec-body">
                            {msg.tools && msg.tools.length > 0 ? (
                              msg.tools.map((t, idx) => (
                                <div key={idx} className="trace-tool-item">
                                  <span className="agent-tag">[{t.agent}]</span>
                                  <span className="tool-name">{t.tool}</span>
                                  <span className={`status-tag ${t.status}`}>{t.status}</span>
                                  {t.duration_ms !== undefined && (
                                    <span className="text-muted font-sm">({t.duration_ms}ms)</span>
                                  )}
                                </div>
                              ))
                            ) : (
                              <div className="text-muted">No external tools required for this request.</div>
                            )}
                          </div>
                        </div>

                        {/* 4. SELF-EVALUATE & RECOVER */}
                        <div className="trace-section">
                          <div className="trace-sec-title">🛡️ 4. SELF-EVALUATE & SELF-CORRECT</div>
                          <div className="trace-sec-body">
                            <div>
                              Grounding & Policy Checks:{' '}
                              {msg.executionSummary?.self_evaluation?.is_valid !== false ? (
                                <strong className="text-emerald">VERIFIED (100% Deterministic Agreement)</strong>
                              ) : (
                                <strong className="text-rose">VALIDATION FAILED</strong>
                              )}
                            </div>
                            {msg.executionSummary?.self_evaluation?.checks_passed?.map((chk, idx) => (
                              <div key={idx} className="trace-sub-row text-muted">
                                ✓ {chk}
                              </div>
                            ))}
                            {msg.executionSummary?.self_evaluation?.failures?.map((fl, idx) => (
                              <div key={idx} className="trace-sub-row text-rose">
                                ✗ [{fl.category}] {fl.reason}
                              </div>
                            ))}
                            {msg.executionSummary?.self_correction ? (
                              <div className="trace-sub-row text-warning">
                                🔄 Recovery Attempted: {msg.executionSummary.self_correction.action} ({msg.executionSummary.self_correction.recovered ? 'Recovered' : 'Halted safely'})
                              </div>
                            ) : (
                              <div className="trace-sub-row text-muted">
                                🔄 Self-Correction: Clean execution, no recovery needed.
                              </div>
                            )}
                          </div>
                        </div>

                        {/* Latency & Telemetry */}
                        {msg.latencyMs !== undefined && (
                          <div className="trace-section">
                            <div className="trace-sec-title">⏱️ 5. PERFORMANCE TELEMETRY</div>
                            <div className="trace-sec-body trace-metrics-grid">
                              <div>Latency: <strong>{msg.latencyMs.toFixed(1)} ms</strong></div>
                              <div>Workflow: <strong>{msg.workflowState}</strong></div>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                <div className="message-timestamp font-mono">{msg.timestamp}</div>
              </div>
            </div>
          ))}

          {/* Loading indicator */}
          {loading && (
            <div className="message-row agent">
              <div className="agent-avatar-badge spinning">
                <ShieldCheck size={18} />
              </div>
              <div className="message-bubble agent loading-bubble">
                <div className="loading-dots">
                  <span />
                  <span />
                  <span />
                </div>
                <span className="loading-label font-mono">
                  Supervisor orchestrating Observe–Think–Act loop...
                </span>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Quick Action Prompts */}
        <div className="chat-prompts-tray">
          <div className="prompts-scroll">
            <span className="prompts-tray-label font-mono">Suggested:</span>
            {currentPrompts.map((promptText, i) => (
              <button
                key={i}
                type="button"
                className="quick-prompt-chip"
                onClick={() => handleSend(promptText)}
                disabled={loading}
              >
                {promptText}
              </button>
            ))}
            {GENERAL_PROMPTS.map((promptText, i) => (
              <button
                key={`gen-${i}`}
                type="button"
                className="quick-prompt-chip chip-secondary"
                onClick={() => handleSend(promptText)}
                disabled={loading}
              >
                {promptText}
              </button>
            ))}
          </div>
        </div>

        {/* Input Form */}
        <form 
          className="chat-input-bar"
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
        >
          <button
            type="button"
            className="reset-conv-btn"
            title="Reset conversation context"
            onClick={() => {
              setConversationId(`conv-${customerId}-${Date.now()}`);
              setMessages((prev) => [
                ...prev,
                {
                  id: `reset-${Date.now()}`,
                  role: 'system',
                  text: `Conversation context cleared for customer ${customerId}. Starting fresh session.`,
                  timestamp: new Date().toLocaleTimeString(),
                }
              ]);
            }}
          >
            <RotateCcw size={15} />
          </button>

          <input
            id="chat-input-field"
            type="text"
            placeholder={`Ask about balance, loans, card block, disputes (Persona: ${customerId})...`}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={loading}
            className="chat-text-input"
          />

          <button 
            id="chat-send-btn"
            type="submit" 
            disabled={!input.trim() || loading} 
            className="btn btn-primary chat-submit-btn"
          >
            <Send size={16} />
          </button>
        </form>
      </div>

      {/* Right Sidebar: Persona Context & Live Architecture Telemetry */}
      <aside className="chat-context-sidebar glass-panel">
        {/* Persona Snapshot Card */}
        <div className="sidebar-section">
          <div className="sidebar-sec-header">
            <User size={15} className="text-cyan" />
            <h4>Active Customer Context</h4>
          </div>

          {customerSnapshot ? (
            <div className="sidebar-persona-card">
              <div className="persona-name-row">
                <span className="persona-name">{customerSnapshot.name}</span>
                <span className="badge badge-neutral font-mono">{customerSnapshot.customer_id}</span>
              </div>
              <div className="persona-meta-text">
                {customerSnapshot.city} · {customerSnapshot.segment}
              </div>

              {/* Balances List */}
              <div className="sidebar-balances-list">
                {customerSnapshot.accounts?.map((acc) => (
                  <div key={acc.account_id} className="sidebar-balance-item">
                    <span className="font-mono text-muted">{acc.type?.toUpperCase()} ({acc.account_id}):</span>
                    <strong className="font-mono">{formatRupees(acc.balance)}</strong>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="text-muted font-mono font-sm">Loading persona records...</div>
          )}
        </div>

        {/* Live Router & Safety Inspector */}
        <div className="sidebar-section">
          <div className="sidebar-sec-header">
            <Activity size={15} className="text-emerald" />
            <h4>Live Architecture Inspector</h4>
          </div>

          {lastTelemetry ? (
            <div className="sidebar-telemetry-box font-mono">
              <div className="telemetry-line">
                <span className="text-muted">Workflow State:</span>
                <strong className="text-cyan">
                  {lastTelemetry.workflowState || lastTelemetry.status}
                </strong>
              </div>
              <div className="telemetry-line">
                <span className="text-muted">Observed Intent:</span>
                <span className="text-emerald">
                  {lastTelemetry.executionSummary?.observe?.intent || 'Ready'}
                </span>
              </div>
              <div className="telemetry-line">
                <span className="text-muted">Agents:</span>
                <span>[{lastTelemetry.agents?.join(', ') || 'supervisor'}]</span>
              </div>
              <div className="telemetry-line">
                <span className="text-muted">Self-Evaluation:</span>
                <span className="text-cyan">
                  {lastTelemetry.executionSummary?.self_evaluation?.is_valid !== false ? 'Verified (Grounding OK)' : 'Failed'}
                </span>
              </div>
              <div className="telemetry-line">
                <span className="text-muted">Latency:</span>
                <span>{lastTelemetry.latencyMs ? `${lastTelemetry.latencyMs.toFixed(1)} ms` : '—'}</span>
              </div>
            </div>
          ) : (
            <div className="telemetry-empty-hint font-mono text-muted font-sm">
              Send a query to inspect the Observe–Think–Act loop and agent dispatch in real time.
            </div>
          )}
        </div>

        {/* Quick Action Shortcuts */}
        <div className="sidebar-section">
          <div className="sidebar-sec-header">
            <Layers size={15} className="text-violet" />
            <h4>Quick Intent Triggers</h4>
          </div>

          <div className="sidebar-action-buttons">
            <button
              type="button"
              className="sidebar-quick-btn"
              onClick={() => handleSend("what is my balance")}
              disabled={loading}
            >
              <Wallet size={13} />
              <span>Check Account Balance</span>
            </button>

            <button
              type="button"
              className="sidebar-quick-btn"
              onClick={() => handleSend("show my last 5 transactions")}
              disabled={loading}
            >
              <Clock size={13} />
              <span>Mini Statement (5 Txns)</span>
            </button>

            <button
              type="button"
              className="sidebar-quick-btn"
              onClick={() => handleSend("Can I get a loan of 5 lakh for 3 years?")}
              disabled={loading}
            >
              <CheckCircle size={13} />
              <span>Check Loan Eligibility</span>
            </button>

            <button
              type="button"
              className="sidebar-quick-btn btn-fraud-trigger"
              onClick={() => handleSend("I did not make this ₹48,000 payment")}
              disabled={loading}
            >
              <ShieldAlert size={13} />
              <span>Report ₹48,000 Fraud (Diya)</span>
            </button>
          </div>
        </div>
      </aside>
    </div>
  );
}
