// API service client for Fingent Banking AI

const BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

let _sessionToken = localStorage.getItem('fingent_auth_token') || localStorage.getItem('nexus_auth_token') || null;

async function request(endpoint, options = {}) {
  const url = `${BASE_URL}${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };
  if (_sessionToken) {
    headers['Authorization'] = `Bearer ${_sessionToken}`;
  }

  const config = {
    ...options,
    headers,
  };

  try {
    const res = await fetch(url, config);
    if (!res.ok) {
      let errorMsg = `HTTP Error ${res.status}`;
      try {
        const data = await res.json();
        if (data && data.detail) errorMsg = data.detail;
      } catch (e) {
        // use fallback message
      }
      throw new Error(errorMsg);
    }
    return await res.json();
  } catch (err) {
    console.error(`API Error on [${options.method || 'GET'} ${endpoint}]:`, err);
    throw err;
  }
}

export const api = {
  // Authentication & Sessions
  setToken: (token) => {
    _sessionToken = token;
    if (token) {
      localStorage.setItem('fingent_auth_token', token);
    } else {
      localStorage.removeItem('fingent_auth_token');
      localStorage.removeItem('nexus_auth_token');
    }
  },
  getToken: () => _sessionToken,

  login: async (username, password) => {
    const res = await request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
    if (res && res.token) {
      api.setToken(res.token);
    }
    return res;
  },

  logout: async () => {
    try {
      await request('/auth/logout', { method: 'POST' });
    } finally {
      api.setToken(null);
    }
  },

  getMe: () => request('/auth/me'),

  getDemoUsers: () => request('/auth/demo-users'),

  // Chat & Supervision
  chat: (payload) =>
    request('/chat', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // Human-in-the-loop Approvals
  decideApproval: (groupId, { approve, customer_id, role = 'customer' }) =>
    request(`/approvals/${groupId}`, {
      method: 'POST',
      body: JSON.stringify({ approve, customer_id, role }),
    }),

  getPendingApprovals: (customerId) => {
    const q = customerId ? `?customer_id=${customerId}` : '';
    return request(`/approvals/pending${q}`);
  },

  // Simulated Banking Backends
  getCustomers: () => request('/customers'),

  getCustomer: (cid) => request(`/customers/${cid}`),

  getBalance: (accountId) => request(`/accounts/${accountId}/balance`),

  getTransactions: (accountId, limit = 15) =>
    request(`/accounts/${accountId}/transactions?limit=${limit}`),

  getTxnRisk: (txnId) => request(`/transactions/${txnId}/risk`),

  getBureauScore: (cid) => request(`/bureau/${cid}/score`),

  getKyc: (cid) => request(`/kyc/${cid}`),

  getAlerts: (customerId, afterId = 0, limit = 30) => {
    let q = `?limit=${limit}&after_id=${afterId}`;
    if (customerId) q += `&customer_id=${customerId}`;
    return request(`/alerts${q}`);
  },

  // Architecture & Observability
  getToolsCatalogue: () => request('/tools'),

  getIntentsCatalogue: () => request('/intents'),

  getAuditLog: (traceId, limit = 50) => {
    let q = `?limit=${limit}`;
    if (traceId) q += `&trace_id=${traceId}`;
    return request(`/audit${q}`);
  },

  getMetrics: () => request('/metrics'),

  resetMetrics: () =>
    request('/metrics/reset', {
      method: 'POST',
    }),

  getLlmStatus: () => request('/admin/llm'),

  setLlmStatus: (enabled) =>
    request(`/admin/llm?enabled=${enabled}`, {
      method: 'POST',
    }),

  simulateTransaction: (customerId, anomalous = false) =>
    request('/simulate/transaction', {
      method: 'POST',
      body: JSON.stringify({ customer_id: customerId, anomalous }),
    }),

  streamControl: (action) =>
    request(`/stream/${action}`, {
      method: 'POST',
    }),

  getHealth: () => request('/health'),
};
