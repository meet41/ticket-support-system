// LOCAL DEV: BASE_URL is empty — Vite proxy forwards requests to the backend.
// PRODUCTION: Set VITE_API_BASE_URL to your deployed backend URL.
const BASE_URL = ''; // import.meta.env.VITE_API_BASE_URL || '';

export const getAccessToken = () => localStorage.getItem('access_token');
export const getRefreshToken = () => localStorage.getItem('refresh_token');
export const getUser = () => {
  try { const u = localStorage.getItem('user'); return u ? JSON.parse(u) : null; }
  catch { return null; }
};
export const setTokens = (access, refresh, user) => {
  localStorage.setItem('access_token', access);
  localStorage.setItem('refresh_token', refresh);
  localStorage.setItem('user', JSON.stringify(user));
};
export const clearTokens = () => {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('user');
};

async function request(path, options = {}, retry = true) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  const token = getAccessToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });
  if (res.status === 401 && retry) {
    const refreshed = await refreshTokens();
    if (refreshed) return request(path, options, false);
    clearTokens();
    window.location.href = '/login';
    return;
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || 'Request failed');
  }
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

let _refreshPromise = null;
async function refreshTokens() {
  if (_refreshPromise) return _refreshPromise;
  _refreshPromise = (async () => {
    const rt = getRefreshToken();
    if (!rt) return false;
    try {
      const res = await fetch(`${BASE_URL}/auth/staff/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: rt }),
      });
      if (!res.ok) return false;
      const data = await res.json();
      localStorage.setItem('access_token', data.access_token);
      return true;
    } catch { return false; }
  })();
  try { return await _refreshPromise; } finally { _refreshPromise = null; }
}

export const api = {
  staffLogin:    (data) => request('/auth/staff/login',  { method: 'POST', body: JSON.stringify(data) }),
  staffLogout:   (rt)   => request('/auth/staff/logout', { method: 'POST', body: JSON.stringify({ refresh_token: rt }) }),
  getMe:         ()     => request('/auth/staff/me'),
  createStaff:   (data) => request('/auth/staff/create', { method: 'POST', body: JSON.stringify(data) }),
  getSubjects:   ()     => request('/tickets/subjects'),
  getOpenTickets: ()    => request('/tickets/open'),
  getAllTickets:  (params = {}) => {
    const qs = new URLSearchParams();
    if (params.status)               qs.set('status', params.status);
    if (params.priority)             qs.set('priority', params.priority);
    if (params.assigned_engineer_id) qs.set('assigned_engineer_id', params.assigned_engineer_id);
    return request(`/tickets/all${qs.toString() ? '?' + qs : ''}`);
  },
  getTicket:     (tn) => request(`/tickets/${tn}`),
  takeTicket:    (tn) => request(`/tickets/take/${tn}`,    { method: 'POST' }),
  resolveTicket: (tn) => request(`/tickets/resolve/${tn}`, { method: 'POST' }),
  closeTicket:   (tn) => request(`/tickets/close/${tn}`,   { method: 'POST' }),
  getEngineers:  ()   => request('/auth/admin/engineers'),
  getCustomers:  ()   => request('/auth/admin/customers'),
};

export function createChatWS(ticketId) {
  const token = getAccessToken();
  // PRODUCTION: Uncomment and set VITE_API_BASE_URL
  // if (import.meta.env.VITE_API_BASE_URL) {
  //   const wsBase = import.meta.env.VITE_API_BASE_URL.replace(/^https?/, p => p === 'https' ? 'wss' : 'ws');
  //   return new WebSocket(`${wsBase}/ws/${ticketId}?token=${token}`);
  // }
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return new WebSocket(`ws://${window.location.host}/ws/${ticketId}?token=${token}`);
}

export function createNotificationWS() {
  const token = getAccessToken();
  // PRODUCTION: Uncomment and set VITE_API_BASE_URL
  // if (import.meta.env.VITE_API_BASE_URL) {
  //   const wsBase = import.meta.env.VITE_API_BASE_URL.replace(/^https?/, p => p === 'https' ? 'wss' : 'ws');
  //   return new WebSocket(`${wsBase}/ws/notifications/live?token=${token}`);
  // }
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return new WebSocket(`ws://${window.location.host}/ws/notifications/live?token=${token}`);
}
