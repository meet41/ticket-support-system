import { useState, useEffect, useRef, useCallback } from 'react';
import { createChatWS } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { format } from 'date-fns';
import { Send, ArrowLeft, MessageSquare, Wifi, WifiOff, Check, CheckCheck, X, Eye, Minus } from 'lucide-react';

/**
 * ChatPanel — supports two render modes:
 *
 * WIDGET mode  (isWidget=true)  — Now dynamically tiles to fit the flex container.
 * EMBEDDED mode (isWidget=false) — fills its parent flex container.
 * Used by AdminDashboard.
 *
 * BUG FIX (chat reload): We key the WebSocket connection on ticket_id ONLY.
 * Status / subject updates to the ticket object no longer tear down the socket
 * because we read ticket_id from a ref and only restart the socket when the
 * ticket_id actually changes.
 */
export default function ChatPanel({
  ticket,
  onBack,
  onClose,
  readOnly = false,
  onStatusUpdate,
  isWidget = false,
  widgetIndex = 0,
}) {
  const { user } = useAuth();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [connected, setConnected] = useState(false);
  const [customerTyping, setCustomerTyping] = useState(false);
  const [serverReadOnly, setServerReadOnly] = useState(false);
  const [viewers, setViewers] = useState([]);
  const [minimized, setMinimized] = useState(false);

  // Store latest ticket in a ref so the WS handler always has current values
  // without those values being in the effect dependency array (avoids restarts).
  const ticketRef = useRef(ticket);
  ticketRef.current = ticket;

  const wsRef = useRef(null);
  const bottomRef = useRef(null);
  const typingTimerRef = useRef(null);
  const typingSentRef = useRef(false);
  const reconnectTimerRef = useRef(null);
  const mountedRef = useRef(true);
  // Track the ticket_id the WS is currently connected to
  const connectedTicketIdRef = useRef(null);

  const scrollToBottom = useCallback(() => {
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
  }, []);

  // KEY FIX: Only restart the WebSocket when ticket_id changes, not on every
  // object update (status, subject, etc. changes must NOT trigger a reconnect).
  const ticketId = ticket?.ticket_id;

  useEffect(() => {
    if (!ticketId) return;

    // If already connected to this exact ticket, do nothing (BUG FIX).
    if (connectedTicketIdRef.current === ticketId) return;

    mountedRef.current = true;
    connectedTicketIdRef.current = ticketId;

    // Clean up any prior connection
    clearTimeout(reconnectTimerRef.current);
    if (wsRef.current) {
      wsRef.current.onclose = null; // prevent reconnect loop from old socket
      wsRef.current.close();
      wsRef.current = null;
    }

    setMessages([]);
    setConnected(false);
    setCustomerTyping(false);
    setServerReadOnly(false);
    setViewers([]);

    const connect = () => {
      if (!mountedRef.current || connectedTicketIdRef.current !== ticketId) return;
      const ws = createChatWS(ticketId);
      wsRef.current = ws;

      ws.onopen = () => {
        if (mountedRef.current && connectedTicketIdRef.current === ticketId) {
          setConnected(true);
        }
      };

      ws.onmessage = (event) => {
        if (!mountedRef.current || connectedTicketIdRef.current !== ticketId) return;
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'history') {
            setMessages(data.messages || []);
          } else if (data.type === 'message') {
            setMessages(prev => {
              if (data.message?.message_id && prev.some(m => m.message_id === data.message.message_id)) return prev;
              return [...prev, data.message];
            });
            setCustomerTyping(false);
          } else if (data.type === 'typing') {
            if (data.sender_type === 'customer') setCustomerTyping(data.is_typing);
          } else if (data.type === 'status_update') {
            onStatusUpdate?.(data);
          } else if (data.type === 'access_info') {
            setServerReadOnly(data.read_only === true);
          } else if (data.type === 'viewer_joined') {
            setViewers(prev => {
              if (prev.some(v => v.viewer_id === data.viewer_id)) return prev;
              return [...prev, { viewer_id: data.viewer_id, viewer_name: data.viewer_name }];
            });
          } else if (data.type === 'viewer_left') {
            setViewers(prev => prev.filter(v => v.viewer_id !== data.viewer_id));
          }
        } catch { /* ignore */ }
      };

      ws.onclose = () => {
        if (!mountedRef.current || connectedTicketIdRef.current !== ticketId) return;
        setConnected(false);
        setCustomerTyping(false);
        reconnectTimerRef.current = setTimeout(connect, 3000);
      };
      ws.onerror = () => ws.close();
    };

    connect();

    return () => {
      // Only truly tear down when the component unmounts (onClose / widget close).
      // We use connectedTicketIdRef reset as the unmount signal, not ticketId change.
      mountedRef.current = false;
      connectedTicketIdRef.current = null;
      clearTimeout(reconnectTimerRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [ticketId]); // ← ONLY ticketId, not the whole ticket object

  useEffect(() => {
    if (!minimized) scrollToBottom();
  }, [messages, customerTyping, minimized, scrollToBottom]);

  const sendTyping = useCallback((isTyping) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'typing', is_typing: isTyping }));
    }
  }, []);

  const handleInputChange = (e) => {
    setInput(e.target.value);
    if (!typingSentRef.current) { sendTyping(true); typingSentRef.current = true; }
    clearTimeout(typingTimerRef.current);
    typingTimerRef.current = setTimeout(() => { sendTyping(false); typingSentRef.current = false; }, 2000);
  };

  const sendMessage = (e) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    clearTimeout(typingTimerRef.current);
    sendTyping(false);
    typingSentRef.current = false;
    wsRef.current.send(JSON.stringify({ type: 'message', message: text, message_type: 'text' }));
    setInput('');
  };

  // Always read status from the ticketRef so widgets stay fresh after status updates
  const isClosed = ticketRef.current?.status === 'closed';

  if (!ticket && !isWidget) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-400 dark:text-gray-600 gap-3">
        <MessageSquare size={48} strokeWidth={1} />
        <p className="text-sm">Select a ticket to view chat</p>
      </div>
    );
  }
  if (!ticket) return null;

  // ── Header ────────────────────────────────────────────────────────────────
  const Header = (
    <div
      className={`bg-indigo-600 px-3 py-2.5 flex items-center gap-2 shrink-0 ${isWidget ? 'cursor-pointer select-none' : 'bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800'}`}
      onClick={isWidget ? (e) => { if (e.target === e.currentTarget || !e.target.closest('button')) setMinimized(m => !m); } : undefined}
    >
      {!isWidget && onBack && (
        <button onClick={onBack} className="lg:hidden p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg">
          <ArrowLeft size={18} />
        </button>
      )}

      <div className="min-w-0 flex-1">
        <h3 className={`text-xs font-semibold truncate ${isWidget ? 'text-white' : ''}`}>
          {ticket.ticket_number} — {ticket.subject}
        </h3>
        <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
          <p className={`text-[10px] capitalize ${isWidget ? 'text-indigo-200' : 'text-gray-500 dark:text-gray-400'}`}>
            {ticketRef.current?.status?.replace('_', ' ')} · {ticket.priority}
          </p>
          {viewers.length > 0 && (
            <span className={`flex items-center gap-1 text-[10px] font-medium ${isWidget ? 'text-indigo-100' : 'text-amber-600 dark:text-amber-400'}`}>
              <Eye size={10} />
              {viewers.map(v => v.viewer_name).join(', ')} viewing
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-1 shrink-0">
        {connected
          ? <Wifi size={12} className={isWidget ? 'text-green-300' : 'text-emerald-500'} />
          : <WifiOff size={12} className={isWidget ? 'text-red-300' : 'text-red-400'} />}
        <span className={`text-[10px] font-medium ${connected
          ? (isWidget ? 'text-green-300' : 'text-emerald-600 dark:text-emerald-400')
          : (isWidget ? 'text-red-300' : 'text-red-500')}`}>
          {connected ? 'Live' : 'Off'}
        </span>
        {isWidget && (
          <>
            <button
              onClick={(e) => { e.stopPropagation(); setMinimized(m => !m); }}
              className="ml-1 p-1 rounded hover:bg-white/20 text-indigo-200 hover:text-white"
              title={minimized ? 'Expand' : 'Minimise'}
            >
              <Minus size={12} />
            </button>
            {onClose && (
              <button
                onClick={(e) => { e.stopPropagation(); onClose(); }}
                className="p-1 rounded hover:bg-white/20 text-indigo-200 hover:text-white"
                title="Close"
              >
                <X size={12} />
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );

  const ViewerBanner = serverReadOnly && !isClosed ? (
    <div className="bg-amber-50 dark:bg-amber-950/30 border-b border-amber-200 dark:border-amber-800 px-3 py-1.5 flex items-center gap-1.5 shrink-0">
      <Eye size={12} className="text-amber-600 dark:text-amber-400" />
      <span className="text-[11px] text-amber-700 dark:text-amber-400 font-medium">
        Viewing only — only the assigned engineer can send messages.
      </span>
    </div>
  ) : null;

  const Body = (
    <>
      {ticket.description && !isWidget && (
        <div className="px-4 py-2.5 bg-indigo-50/50 dark:bg-indigo-950/20 border-b border-gray-200 dark:border-gray-800 shrink-0">
          <p className="text-xs font-medium text-indigo-600 dark:text-indigo-400 mb-0.5">Description</p>
          <p className="text-sm text-gray-700 dark:text-gray-300">{ticket.description}</p>
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
        {messages.length === 0 && (
          <p className="text-center text-xs text-gray-400 py-6">No messages yet.</p>
        )}
        {messages.map((msg, i) => {
          const isSystem = msg.sender_type === 'system';
          const isMe = !isSystem && msg.sender_type === 'support';
          const label = isSystem ? 'System' : isMe ? (msg.sender_name || 'Support') : 'Customer';

          if (isSystem) {
            return (
              <div key={msg.message_id || i} className="flex justify-center">
                <div className="max-w-[80%] bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 text-[10px] px-3 py-1.5 rounded-full text-center">
                  {msg.message}
                </div>
              </div>
            );
          }
          return (
            <div key={msg.message_id || i} className={`flex ${isMe ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[80%] rounded-2xl px-3 py-2 ${
                isMe
                  ? 'bg-indigo-600 text-white rounded-br-md'
                  : 'bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 border border-gray-200 dark:border-gray-700 rounded-bl-md'
              }`}>
                <p className="text-[12px] leading-relaxed whitespace-pre-wrap break-words">{msg.message}</p>
                <p className={`text-[9px] mt-0.5 ${isMe ? 'text-indigo-200' : 'text-gray-400'} flex items-center gap-1`}>
                  {label}{msg.timestamp ? ` · ${format(new Date(msg.timestamp), 'HH:mm')}` : ''}
                  {isMe && (msg.is_read_by_customer
                    ? <CheckCheck size={9} className="text-indigo-300" />
                    : <Check size={9} className="text-indigo-400" />
                  )}
                </p>
              </div>
            </div>
          );
        })}

        {customerTyping && (
          <div className="flex justify-start">
            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-2xl rounded-bl-md px-3 py-2 flex items-center gap-1.5">
              <span className="flex gap-1">
                {[0, 150, 300].map(d => (
                  <span key={d} className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: `${d}ms` }} />
                ))}
              </span>
              <span className="text-[10px] text-gray-400">Customer typing</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {!readOnly && !serverReadOnly && !isClosed ? (
        <form onSubmit={sendMessage} className="bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-800 p-2 flex gap-2 shrink-0">
          <input
            type="text"
            value={input}
            onChange={handleInputChange}
            placeholder={connected ? 'Type a message…' : 'Reconnecting…'}
            disabled={!connected}
            className="flex-1 px-3 py-2 rounded-full border border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-sm outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!input.trim() || !connected}
            className="p-2 rounded-full bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition"
          >
            <Send size={14} />
          </button>
        </form>
      ) : isClosed ? (
        <div className="bg-gray-100 dark:bg-gray-900 border-t border-gray-200 dark:border-gray-800 p-2.5 text-center text-xs text-gray-500">
          Ticket closed.
        </div>
      ) : null}
    </>
  );

  // ── Widget render ─────────────────────────────────────────────────────────
  if (isWidget) {
    return (
      <div className="flex flex-col flex-1 min-w-0 h-full bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl shadow-sm overflow-hidden">
        {Header}
        {!minimized && ViewerBanner}
        {!minimized && (
          <div className="flex flex-col flex-1 min-h-0 bg-gray-50 dark:bg-gray-950">
            {Body}
          </div>
        )}
      </div>
    );
  }

  // ── Embedded render ───────────────────────────────────────────────────────
  return (
    <div className="flex flex-col flex-1 min-h-0 bg-gray-50 dark:bg-gray-950">
      {Header}
      {ViewerBanner}
      {Body}
    </div>
  );
}