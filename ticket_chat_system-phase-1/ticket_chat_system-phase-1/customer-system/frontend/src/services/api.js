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
      const res = await fetch(`${BASE_URL}/auth/customer/refresh`, {
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
  customerRegister: (data) => request('/auth/customer/register', { method: 'POST', body: JSON.stringify(data) }),
  customerLogin:    (data) => request('/auth/customer/login',    { method: 'POST', body: JSON.stringify(data) }),
  customerLogout:   (rt)   => request('/auth/customer/logout',   { method: 'POST', body: JSON.stringify({ refresh_token: rt }) }),
  getMe:            ()     => request('/auth/customer/me'),
  getSubjects:      ()     => request('/tickets/subjects'),
  createTicket:     (data) => request('/tickets/create', { method: 'POST', body: JSON.stringify(data) }),
  getMyTickets:     ()     => request('/tickets/my'),
  getTicket:        (tn)   => request(`/tickets/${tn}`),
};

export function createChatWS(ticketId) {
  const token = getAccessToken();
  // PRODUCTION: Uncomment and set VITE_API_BASE_URL
  // if (import.meta.env.VITE_API_BASE_URL) {
  //   const wsBase = import.meta.env.VITE_API_BASE_URL.replace(/^https?/, p => p === 'https' ? 'wss' : 'ws');
  //   return new WebSocket(`${wsBase}/ws/${ticketId}?token=${token}`);
  // }
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return new WebSocket(`${proto}://${window.location.host}/ws/${ticketId}?token=${token}`);
}
