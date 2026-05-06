import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { api, createChatWS, getRefreshToken } from '../services/api';
import { format } from 'date-fns';
import {
  MessageCircle, X, ChevronLeft, Send, Plus, Wifi, WifiOff,
  Ticket, Clock, CheckCircle, XCircle, CircleDot, Loader2, Bot,
  LogOut, Sun, Moon
} from 'lucide-react';

// ─── Auth Gate (Login / Register) ────────────────────────────────────────────

function AuthGate({ onSuccess }) {
  const { login } = useAuth();
  const [mode, setMode] = useState('login'); // 'login' | 'register'
  const [form, setForm] = useState({ name: '', email: '', password: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      if (mode === 'register') {
        await api.customerRegister({ name: form.name, email: form.email, password: form.password });
      }
      const tokens = await api.customerLogin({ email: form.email, password: form.password });
      await login(tokens);
      onSuccess?.();
    } catch (err) {
      try {
        const parsed = JSON.parse(err.message);
        setError(parsed.detail || err.message);
      } catch {
        setError(err.message || 'Something went wrong');
      }
    }
    setLoading(false);
  };

  const field = (label, name, type = 'text') => (
    <div>
      <label className="block text-xs font-medium text-gray-500 mb-1">{label}</label>
      <input
        type={type}
        required
        value={form[name]}
        onChange={(e) => setForm(f => ({ ...f, [name]: e.target.value }))}
        className="w-full px-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 outline-none focus:ring-2 focus:ring-indigo-500 transition"
      />
    </div>
  );

  return (
    <div className="flex flex-col h-full p-5 justify-center">
      <div className="mb-6 text-center">
        <div className="w-12 h-12 bg-indigo-100 dark:bg-indigo-950 rounded-full flex items-center justify-center mx-auto mb-3">
          <MessageCircle size={24} className="text-indigo-600" />
        </div>
        <h3 className="font-semibold text-gray-800 dark:text-gray-100">
          {mode === 'login' ? 'Sign in to continue' : 'Create an account'}
        </h3>
        <p className="text-xs text-gray-400 mt-1">Get instant support from our team</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-3">
        {mode === 'register' && field('Full Name', 'name')}
        {field('Email', 'email', 'email')}
        {field('Password', 'password', 'password')}
        {error && (
          <p className="text-xs text-red-500 bg-red-50 dark:bg-red-950/30 px-3 py-2 rounded-lg">{error}</p>
        )}
        <button
          type="submit"
          disabled={loading}
          className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium transition disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {loading && <Loader2 size={14} className="animate-spin" />}
          {mode === 'login' ? 'Sign In' : 'Create Account'}
        </button>
      </form>

      <p className="text-center text-xs text-gray-400 mt-4">
        {mode === 'login' ? "Don't have an account? " : 'Already have an account? '}
        <button
          onClick={() => { setMode(m => m === 'login' ? 'register' : 'login'); setError(''); }}
          className="text-indigo-600 hover:underline font-medium"
        >
          {mode === 'login' ? 'Sign Up' : 'Sign In'}
        </button>
      </p>
    </div>
  );
}

// ─── Ticket List ──────────────────────────────────────────────────────────────

const STATUS_ICON = {
  open: <CircleDot size={13} className="text-blue-500" />,
  in_progress: <Clock size={13} className="text-amber-500" />,
  resolved: <CheckCircle size={13} className="text-green-500" />,
  closed: <XCircle size={13} className="text-gray-400" />,
};

function TicketList({ tickets, loading, onSelect, onCreateNew }) {
  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 size={24} className="animate-spin text-indigo-500" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="p-3 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between">
        <span className="text-sm font-semibold text-gray-700 dark:text-gray-200">My Tickets</span>
        <button
          onClick={onCreateNew}
          className="flex items-center gap-1 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs rounded-lg font-medium transition"
        >
          <Plus size={12} /> New Ticket
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {tickets.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-400 gap-3 p-6">
            <Ticket size={36} strokeWidth={1} />
            <p className="text-sm text-center">No tickets yet.<br />Create your first support request.</p>
            <button
              onClick={onCreateNew}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs rounded-lg font-medium transition"
            >
              Create Ticket
            </button>
          </div>
        ) : (
          tickets.map(t => (
            <button
              key={t.ticket_number}
              onClick={() => onSelect(t)}
              className="w-full text-left p-3 border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition"
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-semibold text-gray-700 dark:text-gray-200">{t.ticket_number}</span>
                <div className="flex items-center gap-1">
                  {STATUS_ICON[t.status]}
                  <span className="text-[10px] text-gray-400 capitalize">{t.status.replace('_', ' ')}</span>
                </div>
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{t.subject}</p>
              <p className="text-[10px] text-gray-400 mt-0.5">
                {format(new Date(t.created_at), 'MMM dd, HH:mm')}
              </p>
            </button>
          ))
        )}
      </div>
    </div>
  );
}

// ─── Create Ticket Form ───────────────────────────────────────────────────────

function CreateTicketForm({ onCreated, onBack }) {
  const [subjects, setSubjects] = useState([]);
  const [form, setForm] = useState({ subject: '', description: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    api.getSubjects().then(d => setSubjects(d?.subjects || [])).catch(() => {});
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const ticket = await api.createTicket(form);
      onCreated(ticket);
    } catch (err) {
      try {
        const parsed = JSON.parse(err.message);
        setError(parsed.detail || err.message);
      } catch {
        setError(err.message);
      }
    }
    setLoading(false);
  };

  return (
    <div className="flex flex-col h-full">
      <div className="p-3 border-b border-gray-100 dark:border-gray-800 flex items-center gap-2">
        <button onClick={onBack} className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg">
          <ChevronLeft size={16} />
        </button>
        <span className="text-sm font-semibold text-gray-700 dark:text-gray-200">New Support Ticket</span>
      </div>

      <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-4 space-y-3">
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">Subject</label>
          <select
            required
            value={form.subject}
            onChange={(e) => setForm(f => ({ ...f, subject: e.target.value }))}
            className="w-full px-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="">Select a subject...</option>
            {subjects.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">Description</label>
          <textarea
            required
            minLength={10}
            maxLength={1000}
            rows={5}
            value={form.description}
            onChange={(e) => setForm(f => ({ ...f, description: e.target.value }))}
            placeholder="Describe your issue in detail..."
            className="w-full px-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
          />
        </div>

        {error && <p className="text-xs text-red-500 bg-red-50 dark:bg-red-950/30 px-3 py-2 rounded-lg">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium transition disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {loading && <Loader2 size={14} className="animate-spin" />}
          Submit Ticket
        </button>
      </form>
    </div>
  );
}

// ─── Chat Panel (in Widget) ───────────────────────────────────────────────────

function WidgetChat({ ticket, onBack, onNewTicket, user }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [connected, setConnected] = useState(false);
  const [agentTyping, setAgentTyping] = useState(false);
  const [ticketDetail, setTicketDetail] = useState(ticket);
  const wsRef = useRef(null);
  const bottomRef = useRef(null);
  const typingTimerRef = useRef(null);
  const isTypingRef = useRef(false);
  const reconnectTimerRef = useRef(null);
  const mountedRef = useRef(true);

  const scrollToBottom = useCallback(() => {
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
  }, []);

  useEffect(() => {
    if (!ticket?.ticket_id) return;
    mountedRef.current = true;
    setMessages([]);
    setConnected(false);

    // Issue 2: Auto-reconnect helper — retries every 3 s on unexpected close
    const connect = () => {
      if (!mountedRef.current) return;
      const ws = createChatWS(ticket.ticket_id);
      wsRef.current = ws;

      ws.onopen = () => { if (mountedRef.current) setConnected(true); };

      ws.onmessage = (event) => {
        if (!mountedRef.current) return;
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'history') {
            setMessages(data.messages || []);
          } else if (data.type === 'message') {
            setMessages(prev => {
              // Deduplicate by message_id to prevent double render from change stream
              if (data.message?.message_id && prev.some(m => m.message_id === data.message.message_id)) return prev;
              return [...prev, data.message];
            });
            setAgentTyping(false);
          } else if (data.type === 'typing') {
            if (data.sender_type === 'support') setAgentTyping(data.is_typing);
          } else if (data.type === 'status_update') {
            setTicketDetail(prev => ({ ...prev, status: data.status }));
          } else if (data.type === 'error') {
            setMessages(prev => [...prev, {
              sender_type: 'system',
              sender_name: 'Support Bot',
              message: data.message,
              timestamp: new Date().toISOString(),
            }]);
          }
        } catch { /* ignore */ }
      };

      ws.onclose = () => {
        if (!mountedRef.current) return;
        setConnected(false);
        setAgentTyping(false);
        // Issue 2: Auto-reconnect after 3 s
        reconnectTimerRef.current = setTimeout(connect, 3000);
      };
      ws.onerror = () => ws.close();
    };

    connect();

    return () => {
      mountedRef.current = false;
      clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [ticket?.ticket_id]);

  useEffect(() => { scrollToBottom(); }, [messages, agentTyping, scrollToBottom]);

  // Send typing indicator
  const sendTypingIndicator = useCallback((isTyping) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'typing', is_typing: isTyping }));
    }
  }, []);

  const handleInputChange = (e) => {
    setInput(e.target.value);
    if (!isTypingRef.current) {
      isTypingRef.current = true;
      sendTypingIndicator(true);
    }
    clearTimeout(typingTimerRef.current);
    typingTimerRef.current = setTimeout(() => {
      isTypingRef.current = false;
      sendTypingIndicator(false);
    }, 1500);
  };

  const sendMessage = (e) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    // Stop typing indicator
    clearTimeout(typingTimerRef.current);
    isTypingRef.current = false;
    sendTypingIndicator(false);
    wsRef.current.send(JSON.stringify({ type: 'message', message: text, message_type: 'text' }));
    setInput('');
  };

  const isClosed = ticketDetail?.status === 'closed';

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="bg-white dark:bg-gray-900 border-b border-gray-100 dark:border-gray-800 px-3 py-2.5 flex items-center gap-2 shrink-0">
        <button onClick={onBack} className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg">
          <ChevronLeft size={16} />
        </button>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold truncate text-gray-700 dark:text-gray-200">
            {ticket.ticket_number} — {ticket.subject}
          </p>
          <p className="text-[10px] text-gray-400 capitalize">{ticketDetail?.status?.replace('_', ' ')}</p>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {connected
            ? <Wifi size={12} className="text-emerald-500" />
            : <WifiOff size={12} className="text-red-400" />}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2 bg-gray-50 dark:bg-gray-950">
        {messages.length === 0 && (
          <p className="text-center text-xs text-gray-400 py-4">Loading conversation...</p>
        )}
        {messages.map((msg, i) => {
          const isSystem = msg.sender_type === 'system';
          const isMe = !isSystem && msg.sender_id === user?.id;

          // Identity rules: show agent name, hide customer name (show "You")
          const label = isSystem
            ? null
            : isMe ? null : msg.sender_name || 'Agent';

          if (isSystem) {
            return (
              <div key={msg.message_id || i} className="flex justify-center">
                <div className="flex items-start gap-1.5 max-w-[90%] bg-indigo-50 dark:bg-indigo-950/40 border border-indigo-100 dark:border-indigo-900 rounded-xl px-3 py-2">
                  <Bot size={12} className="text-indigo-500 mt-0.5 shrink-0" />
                  <p className="text-[11px] text-indigo-700 dark:text-indigo-300 leading-relaxed">{msg.message}</p>
                </div>
              </div>
            );
          }

          return (
            <div key={msg.message_id || i} className={`flex ${isMe ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[80%] rounded-2xl px-3 py-2 ${
                isMe
                  ? 'bg-indigo-600 text-white rounded-br-sm'
                  : 'bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 border border-gray-100 dark:border-gray-700 rounded-bl-sm'
              }`}>
                {label && <p className="text-[9px] font-medium mb-0.5 opacity-60">{label}</p>}
                <p className="text-[12px] leading-relaxed whitespace-pre-wrap break-words">{msg.message}</p>
                {msg.timestamp && (
                  <p className={`text-[9px] mt-0.5 ${isMe ? 'text-indigo-200' : 'text-gray-400'}`}>
                    {format(new Date(msg.timestamp), 'HH:mm')}
                  </p>
                )}
              </div>
            </div>
          );
        })}

        {/* Agent typing indicator */}
        {agentTyping && (
          <div className="flex justify-start">
            <div className="bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700 rounded-2xl rounded-bl-sm px-3 py-2.5">
              <div className="flex items-center gap-1">
                <span className="text-[10px] text-gray-400 mr-1">Agent is typing</span>
                <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:0ms]" />
                <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:150ms]" />
                <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:300ms]" />
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      {!isClosed ? (
        <form onSubmit={sendMessage} className="bg-white dark:bg-gray-900 border-t border-gray-100 dark:border-gray-800 p-2.5 flex gap-2 shrink-0">
          <input
            type="text"
            value={input}
            onChange={handleInputChange}
            placeholder={connected ? 'Type a message...' : 'Reconnecting...'}
            disabled={!connected}
            className="flex-1 px-3 py-2 text-sm rounded-full border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!input.trim() || !connected}
            className="p-2.5 rounded-full bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition"
          >
            <Send size={14} />
          </button>
        </form>
      ) : (
        <div className="bg-gray-50 dark:bg-gray-900 border-t border-gray-100 dark:border-gray-800 p-3 text-center space-y-2">
          <p className="text-xs text-gray-500 dark:text-gray-400">This ticket is closed. Need more help?</p>
          <button
            onClick={onNewTicket}
            className="flex items-center gap-1.5 mx-auto px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs rounded-lg font-medium transition"
          >
            <Plus size={12} /> Raise New Ticket
          </button>
        </div>
      )}
    </div>
  );
}

// ─── Main Chat Widget ─────────────────────────────────────────────────────────

export default function ChatWidget() {
  const { user, loading, logout } = useAuth();
  const { dark, toggle: toggleTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const [view, setView] = useState('list'); // 'list' | 'create' | 'chat'
  const [tickets, setTickets] = useState([]);
  const [ticketsLoading, setTicketsLoading] = useState(false);
  const [selectedTicket, setSelectedTicket] = useState(() => {
    // Issue 2: Restore selected ticket from localStorage across refresh
    try {
      const saved = localStorage.getItem('widget_selected_ticket');
      return saved ? JSON.parse(saved) : null;
    } catch { return null; }
  });

  const handleLogout = async () => {
    try {
      const rt = getRefreshToken();
      if (rt) await api.customerLogout(rt);
    } catch { /* ignore errors, still logout */ }
    logout();
    setOpen(false);
    setView('list');
    setSelectedTicket(null);
    setTickets([]);
    localStorage.removeItem('widget_selected_ticket');
  };

  // Auto-open widget as soon as user logs in (feature 3)
  useEffect(() => {
    if (user && !loading) {
      setOpen(true);
      // Issue 2: If we had a ticket open before refresh, go straight to chat view
      if (selectedTicket) setView('chat');
    }
  }, [user, loading]);

  const fetchTickets = useCallback(async () => {
    if (!user) return;
    setTicketsLoading(true);
    try {
      const data = await api.getMyTickets();
      setTickets(data || []);
    } catch { /* ignore */ }
    setTicketsLoading(false);
  }, [user]);

  // Load tickets when widget opens and user is logged in
  useEffect(() => {
    if (open && user && view === 'list') {
      fetchTickets();
    }
  }, [open, user, view, fetchTickets]);

  const handleSelectTicket = async (ticket) => {
    try {
      const detail = await api.getTicket(ticket.ticket_number);
      setSelectedTicket(detail);
      localStorage.setItem('widget_selected_ticket', JSON.stringify(detail));
    } catch {
      setSelectedTicket(ticket);
      localStorage.setItem('widget_selected_ticket', JSON.stringify(ticket));
    }
    setView('chat');
  };

  const handleTicketCreated = async (ticket) => {
    // After creation, open the chat for that ticket directly
    try {
      const detail = await api.getTicket(ticket.ticket_number);
      setSelectedTicket(detail);
      localStorage.setItem('widget_selected_ticket', JSON.stringify(detail));
    } catch {
      setSelectedTicket(ticket);
      localStorage.setItem('widget_selected_ticket', JSON.stringify(ticket));
    }
    setView('chat');
    fetchTickets();
  };

  const handleBack = () => {
    setSelectedTicket(null);
    localStorage.removeItem('widget_selected_ticket');
    setView('list');
    fetchTickets();
  };

  return (
    <>
      {/* ── Floating Chat Window ─────────────────────────────────────────── */}
      {open && (
        <div className="fixed bottom-20 right-4 z-[9999] w-[360px] h-[560px] bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-700 flex flex-col overflow-hidden"
          style={{ maxHeight: 'calc(100vh - 100px)' }}
        >
          {/* Widget Header */}
          <div className="bg-indigo-600 px-4 py-3.5 flex items-center justify-between shrink-0">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 bg-white/20 rounded-full flex items-center justify-center">
                <MessageCircle size={16} className="text-white" />
              </div>
              <div>
                <p className="text-sm font-semibold text-white">Support Chat</p>
                <p className="text-[10px] text-indigo-200">We typically reply within minutes</p>
              </div>
            </div>
            <div className="flex items-center gap-1">
              {/* Feature #3: Theme toggle */}
              <button
                onClick={toggleTheme}
                className="p-1.5 rounded-lg hover:bg-white/20 transition text-white"
                title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
              >
                {dark ? <Sun size={14} /> : <Moon size={14} />}
              </button>
              {/* Feature #1: Logout (only shown when logged in) */}
              {user && (
                <button
                  onClick={handleLogout}
                  className="p-1.5 rounded-lg hover:bg-white/20 transition text-white"
                  title="Logout"
                >
                  <LogOut size={14} />
                </button>
              )}
              <button
                onClick={() => setOpen(false)}
                className="p-1.5 rounded-lg hover:bg-white/20 transition text-white"
              >
                <X size={16} />
              </button>
            </div>
          </div>

          {/* Widget Body */}
          <div className="flex-1 overflow-hidden">
            {loading ? (
              <div className="flex items-center justify-center h-full">
                <Loader2 size={24} className="animate-spin text-indigo-500" />
              </div>
            ) : !user ? (
              <AuthGate onSuccess={() => { setView('list'); }} />
            ) : view === 'list' ? (
              <TicketList
                tickets={tickets}
                loading={ticketsLoading}
                onSelect={handleSelectTicket}
                onCreateNew={() => setView('create')}
              />
            ) : view === 'create' ? (
              <CreateTicketForm
                onCreated={handleTicketCreated}
                onBack={() => setView('list')}
              />
            ) : view === 'chat' && selectedTicket ? (
              <WidgetChat
                ticket={selectedTicket}
                onBack={handleBack}
                onNewTicket={() => { setSelectedTicket(null); setView('create'); }}
                user={user}
              />
            ) : null}
          </div>
        </div>
      )}

      {/* ── Floating Toggle Button ───────────────────────────────────────── */}
      <button
        onClick={() => setOpen(o => !o)}
        className="fixed bottom-4 right-4 z-[9999] w-14 h-14 bg-indigo-600 hover:bg-indigo-700 text-white rounded-full shadow-lg flex items-center justify-center transition-all hover:scale-105 active:scale-95"
        aria-label="Open support chat"
      >
        {open ? <X size={22} /> : <MessageCircle size={22} />}
      </button>
    </>
  );
}