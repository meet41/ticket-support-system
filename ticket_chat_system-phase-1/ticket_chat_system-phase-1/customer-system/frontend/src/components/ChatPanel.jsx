import { useState, useEffect, useRef, useCallback } from 'react';
import { createChatWS } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { format } from 'date-fns';
import { Send, ArrowLeft, MessageSquare, Wifi, WifiOff, Check, CheckCheck } from 'lucide-react';

export default function ChatPanel({ ticket, onBack, readOnly = false, onStatusUpdate }) {
  const { user } = useAuth();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  const bottomRef = useRef(null);

  const scrollToBottom = useCallback(() => {
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
  }, []);

  useEffect(() => {
    if (!ticket?.ticket_id) return;

    setMessages([]);
    setConnected(false);

    const ws = createChatWS(ticket.ticket_id);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'history') {
          setMessages(data.messages || []);
        } else if (data.type === 'message') {
          setMessages(prev => [...prev, data.message]);
        } else if (data.type === 'status_update') {
          onStatusUpdate?.(data);
        }
      } catch { /* ignore malformed messages */ }
    };

    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [ticket?.ticket_id]);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const sendMessage = (e) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    wsRef.current.send(JSON.stringify({
      message: text,
      message_type: 'text',
    }));
    setInput('');
  };

  const isClosed = ticket?.status === 'closed';

  if (!ticket) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-400 dark:text-gray-600 gap-3">
        <MessageSquare size={48} strokeWidth={1} />
        <p className="text-sm">Select a ticket to view chat</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col flex-1 min-h-0 bg-gray-50 dark:bg-gray-950">
      {/* Header */}
      <div className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-4 py-3 flex items-center gap-3 shrink-0">
        {onBack && (
          <button onClick={onBack} className="lg:hidden p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg">
            <ArrowLeft size={18} />
          </button>
        )}
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold truncate">{ticket.ticket_number} — {ticket.subject}</h3>
          <p className="text-xs text-gray-500 dark:text-gray-400 capitalize">
            {ticket.status?.replace('_', ' ')} · {ticket.priority} priority
          </p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {connected ? (
            <Wifi size={14} className="text-emerald-500" />
          ) : (
            <WifiOff size={14} className="text-red-400" />
          )}
          <span className={`text-[11px] font-medium ${connected ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-500'}`}>
            {connected ? 'Live' : 'Offline'}
          </span>
        </div>
      </div>

      {/* Ticket description */}
      {ticket.description && (
        <div className="px-4 py-3 bg-indigo-50/50 dark:bg-indigo-950/20 border-b border-gray-200 dark:border-gray-800 shrink-0">
          <p className="text-xs font-medium text-indigo-600 dark:text-indigo-400 mb-0.5">Description</p>
          <p className="text-sm text-gray-700 dark:text-gray-300">{ticket.description}</p>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {messages.length === 0 && (
          <p className="text-center text-sm text-gray-400 py-8">No messages yet. Start the conversation!</p>
        )}
        {messages.map((msg, i) => {
          // Primary: match by sender_id. Fallback: match by sender_type/role
          const isMe = (user?.id != null && msg.sender_id != null)
            ? msg.sender_id === user.id
            : (msg.sender_type === 'customer') === (user?.role === 'customer');
          const label = msg.sender_name || (msg.sender_type === 'customer' ? 'Customer' : 'Support');

          return (
            <div key={msg.message_id || i} className={`flex ${isMe ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[75%] rounded-2xl px-4 py-2.5 ${
                isMe
                  ? 'bg-indigo-600 text-white rounded-br-md'
                  : 'bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 border border-gray-200 dark:border-gray-700 rounded-bl-md'
              }`}>
                <p className="text-[13px] leading-relaxed whitespace-pre-wrap break-words">{msg.message}</p>
                <p className={`text-[10px] mt-1 ${isMe ? 'text-indigo-200' : 'text-gray-400'} flex items-center gap-1`}>
                  {label}
                  {msg.timestamp ? ` · ${format(new Date(msg.timestamp), 'HH:mm')}` : ''}
                  {isMe && (
                    msg.is_read_by_support ? (
                      <CheckCheck size={10} className="text-indigo-300" />
                    ) : (
                      <Check size={10} className="text-indigo-400" />
                    )
                  )}
                </p>
              </div>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      {!readOnly && !isClosed && (
        <form onSubmit={sendMessage} className="bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-800 p-3 flex gap-2 shrink-0">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={connected ? 'Type a message...' : 'Reconnecting...'}
            disabled={!connected}
            className="flex-1 px-4 py-2.5 rounded-full border border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-sm outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!input.trim() || !connected}
            className="p-2.5 rounded-full bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition"
          >
            <Send size={16} />
          </button>
        </form>
      )}
      {isClosed && (
        <div className="bg-gray-100 dark:bg-gray-900 border-t border-gray-200 dark:border-gray-800 p-3 text-center text-sm text-gray-500">
          This ticket is closed.
        </div>
      )}
    </div>
  );
}
