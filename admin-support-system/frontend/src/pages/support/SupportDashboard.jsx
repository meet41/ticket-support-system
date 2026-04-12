import { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '../../context/AuthContext';
import { api, createNotificationWS } from '../../services/api';
import { useToast } from '../../components/Toast';
import Layout from '../../components/Layout';
import KPICard from '../../components/KPICard';
import { StatusBadge, PriorityBadge } from '../../components/StatusBadge';
import ChatPanel from '../../components/ChatPanel';
import NotificationPanel from '../../components/NotificationPanel';
import { Ticket, Inbox, UserCheck, CheckCircle, Search, Check, XCircle, Bell } from 'lucide-react';
import { format } from 'date-fns';

export default function SupportDashboard() {
  const { user } = useAuth();
  const { addToast } = useToast();
  const [tab, setTab] = useState('open');
  const [openTickets, setOpenTickets] = useState([]);
  const [myTickets, setMyTickets] = useState([]);
  const [teamTickets, setTeamTickets] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [notifications, setNotifications] = useState([]);
  const [unreadNotifs, setUnreadNotifs] = useState(0);
  const [showNotifPanel, setShowNotifPanel] = useState(false);
  const [actionLoading, setActionLoading] = useState('');
  const wsRef = useRef(null);
  const selectedRef = useRef(null);
  selectedRef.current = selected;

  const fetchTickets = useCallback(async () => {
    try {
      const [open, mine, team] = await Promise.all([
        api.getOpenTickets(),
        api.getAllTickets({ assigned_engineer_id: user.id }),
        api.getAllTickets(), // all team tickets
      ]);
      setOpenTickets(open || []);
      setMyTickets(mine || []);
      setTeamTickets(team || []);
    } catch { /* ignore */ }
    setLoading(false);
  }, [user.id]);

  useEffect(() => { fetchTickets(); }, [fetchTickets]);

  // Request notification permission
  useEffect(() => {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }
  }, []);

  // Notification WebSocket — fully real-time, no manual refresh needed
  useEffect(() => {
    let ws;
    let reconnectTimer;

    const connect = () => {
      ws = createNotificationWS();
      wsRef.current = ws;

      ws.onmessage = async (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.event === 'ticket_created') {
            // New ticket: add to open pool immediately
            setOpenTickets(prev => {
              const exists = prev.some(t => t.ticket_id === data.ticket_id);
              if (exists) return prev;
              return [{ ticket_id: data.ticket_id, ticket_number: data.ticket_number, subject: data.subject, priority: data.priority, status: 'open', created_at: data.created_at, assigned_engineer_id: null }, ...prev];
            });
            setNotifications(prev => [data, ...prev]);
            setUnreadNotifs(c => c + 1);
            setShowNotifPanel(true); // Auto-show notification panel
            addToast(`🎫 New ticket: ${data.ticket_number} — ${data.subject}`, 'info');

            // Browser notification
            if ('Notification' in window && Notification.permission === 'granted') {
              new Notification(`New Ticket: ${data.ticket_number}`, {
                body: `${data.subject} (Priority: ${data.priority})`,
                icon: '/favicon.ico', // or some icon
                tag: `ticket-${data.ticket_id}`, // to avoid duplicates
              });
            }

          } else if (data.event === 'ticket_taken') {
            // Remove from open pool immediately
            setOpenTickets(prev => prev.filter(t => t.ticket_id !== data.ticket_id));

            if (data.engineer_id === user.id) {
              addToast(`✅ You took ticket ${data.ticket_number} — Chat opened`, 'success');
              // Auto-open chat for the ticket this engineer just took
              try {
                const takenTicket = await api.getTicket(data.ticket_number);
                setMyTickets(prev => {
                  const exists = prev.some(t => t.ticket_id === data.ticket_id);
                  return exists ? prev : [takenTicket, ...prev];
                });
                setSelected(takenTicket);
                setTab('mine');
              } catch { /* ignore */ }
            } else {
              // Another engineer took it — just refresh my tickets (it won't affect mine)
              fetchTickets();
            }

          } else if (data.event === 'ticket_resolved') {
            setMyTickets(prev => prev.map(t =>
              t.ticket_id === data.ticket_id ? { ...t, status: 'resolved' } : t
            ));
            if (selectedRef.current?.ticket_id === data.ticket_id) {
              setSelected(prev => prev ? { ...prev, status: 'resolved' } : prev);
            }

          } else if (data.event === 'ticket_closed') {
            setMyTickets(prev => prev.map(t =>
              t.ticket_id === data.ticket_id ? { ...t, status: 'closed' } : t
            ));
            if (selectedRef.current?.ticket_id === data.ticket_id) {
              setSelected(prev => prev ? { ...prev, status: 'closed' } : prev);
            }

          } else if (data.event === 'ticket_reopened') {
            setMyTickets(prev => prev.map(t =>
              t.ticket_id === data.ticket_id ? { ...t, status: 'in_progress' } : t
            ));
            if (selectedRef.current?.ticket_id === data.ticket_id) {
              setSelected(prev => prev ? { ...prev, status: 'in_progress' } : prev);
            }
            addToast(`↩️ Ticket ${data.ticket_number} was reopened`, 'warning');
          }
        } catch { /* ignore */ }
      };

      ws.onclose = () => {
        // Auto-reconnect after 3s
        reconnectTimer = setTimeout(connect, 3000);
      };
      ws.onerror = () => ws.close();
    };

    connect();
    return () => {
      clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [addToast, fetchTickets, user.id]);

  const handleTake = async (ticket) => {
    setActionLoading(ticket.ticket_number);
    try {
      await api.takeTicket(ticket.ticket_number);
      addToast(`Assigned ${ticket.ticket_number} to you`, 'success');
      // Optimistic: remove from open list, the WS will auto-open chat
      setOpenTickets(prev => prev.filter(t => t.ticket_number !== ticket.ticket_number));
      const updated = await api.getTicket(ticket.ticket_number);
      setMyTickets(prev => {
        const exists = prev.some(t => t.ticket_number === ticket.ticket_number);
        return exists ? prev : [updated, ...prev];
      });
      setSelected(updated);
      setTab('mine');
    } catch (err) {
      addToast(err.message, 'error');
    }
    setActionLoading('');
  };

  const handleAction = async (action) => {
    if (!selected) return;
    setActionLoading(action);
    try {
      if (action === 'resolve') {
        await api.resolveTicket(selected.ticket_number);
        addToast(`${selected.ticket_number} resolved`, 'success');
      } else if (action === 'close') {
        await api.closeTicket(selected.ticket_number);
        addToast(`${selected.ticket_number} closed`, 'success');
      }
      // WS status_update will update state — also do optimistic update
      const newStatus = action === 'resolve' ? 'resolved' : 'closed';
      setSelected(prev => prev ? { ...prev, status: newStatus } : prev);
      setMyTickets(prev => prev.map(t =>
        t.ticket_number === selected.ticket_number ? { ...t, status: newStatus } : t
      ));
    } catch (err) {
      addToast(err.message, 'error');
    }
    setActionLoading('');
  };

  const handleStatusUpdate = useCallback((data) => {
    // Called by ChatPanel when a status_update WS event arrives
    setMyTickets(prev => prev.map(t =>
      t.ticket_id === data.ticket_id ? { ...t, status: data.status } : t
    ));
    if (selectedRef.current?.ticket_id === data.ticket_id) {
      setSelected(prev => prev ? { ...prev, status: data.status } : prev);
    }
  }, []);

  const handleSelect = async (ticket) => {
    try {
      const detail = await api.getTicket(ticket.ticket_number);
      setSelected(detail);
    } catch {
      setSelected(ticket);
    }
  };

  const handleNotifClick = (n) => {
    setShowNotifPanel(false);
    handleSelect({ ticket_number: n.ticket_number || `TCK-${n.ticket_id}`, ticket_id: n.ticket_id });
  };

  const currentTickets = tab === 'open' ? openTickets : tab === 'mine' ? myTickets : teamTickets;
  const filtered = currentTickets.filter(t => {
    if (!search) return true;
    const s = search.toLowerCase();
    return t.ticket_number?.toLowerCase().includes(s) || t.subject?.toLowerCase().includes(s);
  });

  const kpis = {
    openPool: openTickets.length,
    myActive: myTickets.filter(t => t.status === 'in_progress').length,
    myResolved: myTickets.filter(t => t.status === 'resolved').length,
    myTotal: myTickets.length,
    teamActive: teamTickets.filter(t => t.status === 'in_progress').length,
    teamResolved: teamTickets.filter(t => t.status === 'resolved').length,
    teamTotal: teamTickets.length,
  };

  const showActions = selected && selected.assigned_engineer_id === user.id &&
    (selected.status === 'in_progress' || selected.status === 'resolved');
  const showTakeButton = selected && selected.status === 'open' && !selected.assigned_engineer_id;

  return (
    <Layout>
      <div className="h-full flex flex-col">
        {/* Header + KPIs */}
        <div className="p-5 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 shrink-0">
          <div className="flex items-center justify-between mb-5">
            <div>
              <h2 className="text-lg font-bold">Support Dashboard</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Handle customer tickets
                {user.team ? <span className="ml-2 px-2 py-0.5 bg-indigo-100 dark:bg-indigo-900 text-indigo-700 dark:text-indigo-300 text-xs rounded-full font-medium">{user.team}</span> : null}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {/* Real-time notification bell */}
              <div className="relative">
                <button
                  onClick={() => { setShowNotifPanel(v => !v); setUnreadNotifs(0); }}
                  className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition relative"
                  title="Notifications"
                >
                  <Bell size={18} />
                  {unreadNotifs > 0 && (
                    <span className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 text-white text-[10px] rounded-full flex items-center justify-center font-bold">
                      {unreadNotifs > 9 ? '9+' : unreadNotifs}
                    </span>
                  )}
                </button>
                {showNotifPanel && (
                  <div className="absolute right-0 top-10 z-50 w-80 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl shadow-xl overflow-hidden">
                    <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
                      <span className="text-sm font-semibold">Notifications</span>
                      <button onClick={() => { setNotifications([]); setShowNotifPanel(false); }} className="text-xs text-gray-400 hover:text-gray-600">Clear all</button>
                    </div>
                    <div className="max-h-72 overflow-y-auto">
                      {notifications.length === 0 ? (
                        <p className="p-4 text-sm text-gray-400 text-center">No notifications</p>
                      ) : notifications.map((n, i) => (
                        <button key={i} onClick={() => handleNotifClick(n)} className="w-full text-left p-3 hover:bg-gray-50 dark:hover:bg-gray-800 border-b border-gray-100 dark:border-gray-800 last:border-0">
                          <p className="text-xs font-semibold text-gray-700 dark:text-gray-200">{n.ticket_number} — {n.subject}</p>
                          <p className="text-[11px] text-gray-400">New ticket · Priority: {n.priority}</p>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <KPICard label="Open Pool" value={kpis.openPool} icon={Inbox} color="blue" />
            <KPICard label="My Active" value={kpis.myActive} icon={Ticket} color="amber" />
            <KPICard label="My Resolved" value={kpis.myResolved} icon={CheckCircle} color="green" />
            <KPICard label="Team Total" value={kpis.teamTotal} icon={UserCheck} color="indigo" />
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 flex overflow-hidden">
          {/* Ticket list */}
          <div className={`${selected ? 'hidden lg:flex' : 'flex'} flex-col w-full lg:w-[400px] lg:shrink-0 border-r border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900`}>
            <div className="border-b border-gray-200 dark:border-gray-800">
              <div className="flex">
                {[
                  { key: 'open', label: `Open Pool (${openTickets.length})` },
                  { key: 'mine', label: `My Tickets (${myTickets.length})` },
                  { key: 'team', label: `All Tickets (${teamTickets.length})` },
                ].map(t => (
                  <button
                    key={t.key}
                    onClick={() => setTab(t.key)}
                    className={`flex-1 py-3 text-sm font-medium transition ${
                      tab === t.key ? 'text-indigo-600 dark:text-indigo-400 border-b-2 border-indigo-600 dark:border-indigo-400' : 'text-gray-400 hover:text-gray-600'
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
              <div className="p-3">
                <div className="relative">
                  <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                  <input
                    type="text"
                    placeholder="Search..."
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    className="w-full pl-9 pr-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto">
              {loading ? (
                <p className="p-6 text-center text-gray-400 text-sm">Loading...</p>
              ) : filtered.length === 0 ? (
                <p className="p-6 text-center text-gray-400 text-sm">No tickets</p>
              ) : (
                filtered.map(t => (
                  <div
                    key={t.ticket_number}
                    onClick={() => handleSelect(t)}
                    className={`p-4 border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition cursor-pointer ${
                      selected?.ticket_number === t.ticket_number ? 'bg-indigo-50/70 dark:bg-indigo-950/20 border-l-[3px] border-l-indigo-600' : ''
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-semibold">{t.ticket_number}</span>
                      <StatusBadge status={t.status} />
                    </div>
                    <p className="text-sm text-gray-600 dark:text-gray-400 truncate">{t.subject}</p>
                    <div className="flex items-center justify-between mt-2">
                      <div className="flex items-center gap-2">
                        <PriorityBadge priority={t.priority} />
                        {t.created_at && <span className="text-xs text-gray-400">{format(new Date(t.created_at), 'MMM dd, HH:mm')}</span>}
                      </div>
                      {tab === 'open' && t.status === 'open' && (
                        <button
                          onClick={(e) => { e.stopPropagation(); handleTake(t); }}
                          disabled={actionLoading === t.ticket_number}
                          className="px-3 py-1 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-medium transition disabled:opacity-50"
                        >
                          {actionLoading === t.ticket_number ? '...' : 'Take'}
                        </button>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Chat + Actions */}
          <div className={`${selected ? 'flex' : 'hidden lg:flex'} flex-1 flex-col min-h-0`}>
            {showTakeButton && (
              <div className="flex gap-2 px-4 py-2.5 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 shrink-0">
                <button
                  onClick={() => handleTake(selected)}
                  disabled={actionLoading === selected.ticket_number}
                  className="flex items-center gap-1.5 px-4 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-medium transition disabled:opacity-50"
                >
                  <UserCheck size={13} /> {actionLoading === selected.ticket_number ? 'Taking...' : 'Take Ticket'}
                </button>
              </div>
            )}
            {showActions && (
              <div className="flex gap-2 px-4 py-2.5 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 shrink-0">
                {selected.status === 'in_progress' && (
                  <>
                    <button
                      onClick={() => handleAction('resolve')}
                      disabled={actionLoading === 'resolve'}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-medium transition disabled:opacity-50"
                    >
                      <Check size={13} /> Resolve
                    </button>
                    <button
                      onClick={() => handleAction('close')}
                      disabled={actionLoading === 'close'}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-600 hover:bg-gray-700 text-white rounded-lg text-xs font-medium transition disabled:opacity-50"
                    >
                      <XCircle size={13} /> Close
                    </button>
                  </>
                )}
                {selected.status === 'resolved' && (
                  <button
                    onClick={() => handleAction('close')}
                    disabled={actionLoading === 'close'}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-600 hover:bg-gray-700 text-white rounded-lg text-xs font-medium transition disabled:opacity-50"
                  >
                    <XCircle size={13} /> Close Ticket
                  </button>
                )}
              </div>
            )}
            <ChatPanel ticket={selected} onBack={() => setSelected(null)} onStatusUpdate={handleStatusUpdate} />
          </div>
        </div>
      </div>
    </Layout>
  );
}
