import { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '../../context/AuthContext';
import { api, createNotificationWS } from '../../services/api';
import { useToast } from '../../components/Toast';
import Layout from '../../components/Layout';
import KPICard from '../../components/KPICard';
import { StatusBadge, PriorityBadge } from '../../components/StatusBadge';
import ChatPanel from '../../components/ChatPanel';
import {
  Ticket, Inbox, UserCheck, CheckCircle, Search,
  Check, XCircle, Bell, MessageSquare, Users,
} from 'lucide-react';
import { format } from 'date-fns';

const MAX_OPEN_CHATS = 4;

export default function SupportDashboard() {
  const { user } = useAuth();
  const { addToast } = useToast();
  const [tab, setTab] = useState('open');
  const [openTickets, setOpenTickets] = useState([]);
  const [myTickets, setMyTickets] = useState([]);
  const [teamTickets, setTeamTickets] = useState([]);

  // Up to MAX_OPEN_CHATS simultaneous chat widgets
  const [openChats, setOpenChats] = useState([]);

  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [notifications, setNotifications] = useState([]);
  const [unreadNotifs, setUnreadNotifs] = useState(0);
  const [showNotifPanel, setShowNotifPanel] = useState(false);
  const [actionLoading, setActionLoading] = useState('');
  const wsRef = useRef(null);

  // ── Data fetching ──────────────────────────────────────────────────────────
  const fetchTickets = useCallback(async () => {
    try {
      const [open, mine, team] = await Promise.all([
        api.getOpenTickets(),
        api.getAllTickets({ assigned_engineer_id: user.id }),
        api.getAllTickets(),
      ]);
      setOpenTickets(open || []);
      setMyTickets(mine || []);
      setTeamTickets(team || []);
    } catch { /* ignore */ }
    setLoading(false);
  }, [user.id]);

  useEffect(() => { fetchTickets(); }, [fetchTickets]);


  // ── Notification WebSocket ─────────────────────────────────────────────────
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
            setOpenTickets(prev => {
              if (prev.some(t => t.ticket_id === data.ticket_id)) return prev;
              return [{
                ticket_id: data.ticket_id, ticket_number: data.ticket_number,
                subject: data.subject, priority: data.priority,
                status: 'open', created_at: data.created_at, assigned_engineer_id: null,
              }, ...prev];
            });
            setNotifications(prev => [data, ...prev]);
            setUnreadNotifs(c => c + 1);
            setShowNotifPanel(true);
            addToast(`🎫 New ticket: ${data.ticket_number} — ${data.subject}`, 'info');
           
              new Notification(`New Ticket: ${data.ticket_number}`, {
                body: `${data.subject} (Priority: ${data.priority})`,
                tag: `ticket-${data.ticket_id}`,
              });

          } else if (data.event === 'ticket_taken') {
            setOpenTickets(prev => prev.filter(t => t.ticket_id !== data.ticket_id));
            if (data.engineer_id === user.id) {
              addToast(`✅ You took ticket ${data.ticket_number}`, 'success');
              try {
                const takenTicket = await api.getTicket(data.ticket_number);
                setMyTickets(prev => prev.some(t => t.ticket_id === data.ticket_id) ? prev : [takenTicket, ...prev]);
                openChatWidget(takenTicket);
                setTab('mine');
              } catch { /* ignore */ }
            } else {
              fetchTickets();
            }

          } else if (data.event === 'ticket_resolved') {
            setMyTickets(prev => prev.map(t => t.ticket_id === data.ticket_id ? { ...t, status: 'resolved' } : t));
            setOpenChats(prev => prev.map(t => t.ticket_id === data.ticket_id ? { ...t, status: 'resolved' } : t));

          } else if (data.event === 'ticket_closed') {
            setMyTickets(prev => prev.map(t => t.ticket_id === data.ticket_id ? { ...t, status: 'closed' } : t));
            setOpenChats(prev => prev.map(t => t.ticket_id === data.ticket_id ? { ...t, status: 'closed' } : t));

          } else if (data.event === 'ticket_reopened') {
            setMyTickets(prev => prev.map(t => t.ticket_id === data.ticket_id ? { ...t, status: 'in_progress' } : t));
            setOpenChats(prev => prev.map(t => t.ticket_id === data.ticket_id ? { ...t, status: 'in_progress' } : t));
            addToast(`↩️ Ticket ${data.ticket_number} was reopened`, 'warning');
          }
        } catch { /* ignore */ }
      };

      ws.onclose = () => { reconnectTimer = setTimeout(connect, 3000); };
      ws.onerror = () => ws.close();
    };

    connect();
    return () => { clearTimeout(reconnectTimer); ws?.close(); };
  }, [addToast, fetchTickets, user.id]);

  // ── Widget management ──────────────────────────────────────────────────────
  const openChatWidget = useCallback((ticket) => {
    setOpenChats(prev => {
      if (prev.some(t => t.ticket_id === ticket.ticket_id)) return prev;
      if (prev.length >= MAX_OPEN_CHATS) {
        // Drop the oldest (leftmost) widget to make room
        return [...prev.slice(1), ticket];
      }
      return [...prev, ticket];
    });
  }, []);

  const closeChatWidget = useCallback((ticketId) => {
    setOpenChats(prev => prev.filter(t => t.ticket_id !== ticketId));
  }, []);

  // ── Ticket actions ─────────────────────────────────────────────────────────
  const handleTake = async (ticket, e) => {
    e?.stopPropagation();
    setActionLoading(ticket.ticket_number);
    try {
      await api.takeTicket(ticket.ticket_number);
      addToast(`Assigned ${ticket.ticket_number} to you`, 'success');
      setOpenTickets(prev => prev.filter(t => t.ticket_number !== ticket.ticket_number));
      const updated = await api.getTicket(ticket.ticket_number);
      setMyTickets(prev => prev.some(t => t.ticket_number === ticket.ticket_number) ? prev : [updated, ...prev]);
      openChatWidget(updated);
      setTab('mine');
    } catch (err) {
      addToast(err.message, 'error');
    }
    setActionLoading('');
  };

  const handleAction = async (ticket, action, e) => {
    e?.stopPropagation();
    if (!ticket) return;
    setActionLoading(`${action}-${ticket.ticket_id}`);
    try {
      if (action === 'resolve') await api.resolveTicket(ticket.ticket_number);
      else if (action === 'close') await api.closeTicket(ticket.ticket_number);
      const newStatus = action === 'resolve' ? 'resolved' : 'closed';
      addToast(`${ticket.ticket_number} ${newStatus}`, 'success');
      setOpenChats(prev => prev.map(t => t.ticket_id === ticket.ticket_id ? { ...t, status: newStatus } : t));
      setMyTickets(prev => prev.map(t => t.ticket_number === ticket.ticket_number ? { ...t, status: newStatus } : t));
    } catch (err) {
      addToast(err.message, 'error');
    }
    setActionLoading('');
  };

  const handleStatusUpdate = useCallback((data) => {
    setMyTickets(prev => prev.map(t => t.ticket_id === data.ticket_id ? { ...t, status: data.status } : t));
    setOpenChats(prev => prev.map(t => t.ticket_id === data.ticket_id ? { ...t, status: data.status } : t));
  }, []);

  const handleSelectTicket = async (ticket) => {
    try {
      const detail = await api.getTicket(ticket.ticket_number);
      openChatWidget(detail);
    } catch {
      openChatWidget(ticket);
    }
  };

  const handleNotifClick = async (n) => {
    setShowNotifPanel(false);
    try {
      const detail = await api.getTicket(n.ticket_number || `TCK-${n.ticket_id}`);
      openChatWidget(detail);
    } catch { /* ignore */ }
  };

  // ── Filtered list ──────────────────────────────────────────────────────────
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
    teamTotal: teamTickets.length,
  };

  // ── Sidebar ticket list (injected into Layout) ─────────────────────────────
  const SidebarTicketList = (
    <div className="flex flex-col flex-1 min-h-0">
      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-800 ">
        <div className="flex">
          {[
            { key: 'open',  label: 'Open',  count: openTickets.length,  icon: Inbox },
            { key: 'mine',  label: 'Mine',  count: myTickets.length,    icon: Ticket },
            { key: 'team',  label: 'All',   count: teamTickets.length,  icon: Users },
          ].map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex-1 py-2.5 text-xs font-medium transition flex flex-col items-center gap-0.5 ${
                tab === t.key
                  ? 'text-indigo-600 dark:text-indigo-400 border-b-2 border-indigo-600 dark:border-indigo-400'
                  : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'
              }`}
            >
              <t.icon size={13} />
              {t.label}
              <span className="text-[10px] font-bold">{t.count}</span>
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="p-2">
          <div className="relative">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="Search…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full pl-7 pr-2 py-1.5 rounded-lg border border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-xs outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <p className="p-4 text-center text-gray-400 text-xs">Loading…</p>
        ) : filtered.length === 0 ? (
          <p className="p-4 text-center text-gray-400 text-xs">No tickets</p>
        ) : (
          filtered.map(t => {
            const isOpen = openChats.some(c => c.ticket_id === t.ticket_id);
            return (
              <div
                key={t.ticket_number}
                onClick={() => handleSelectTicket(t)}
                className={`p-3 border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50 cursor-pointer transition ${
                  isOpen ? 'bg-indigo-50/70 dark:bg-indigo-950/20 border-l-2 border-l-indigo-500' : ''
                }`}
              >
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-xs font-semibold truncate mr-1">{t.ticket_number}</span>
                  <StatusBadge status={t.status} />
                </div>
                <p className="text-[11px] text-gray-500 dark:text-gray-400 truncate mb-1.5">{t.subject}</p>

                <div className="flex items-center justify-between">
                  <PriorityBadge priority={t.priority} />
                  <div className="flex gap-1" onClick={e => e.stopPropagation()}>
                    {t.assigned_engineer_id === user.id && t.status === 'in_progress' && (
                      <>
                        <button
                          onClick={(e) => handleAction(t, 'resolve', e)}
                          disabled={actionLoading === `resolve-${t.ticket_id}`}
                          className="px-1.5 py-0.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-[9px] font-medium transition disabled:opacity-50"
                        >Resolve</button>
                        <button
                          onClick={(e) => handleAction(t, 'close', e)}
                          disabled={actionLoading === `close-${t.ticket_id}`}
                          className="px-1.5 py-0.5 bg-gray-600 hover:bg-gray-700 text-white rounded text-[9px] font-medium transition disabled:opacity-50"
                        >Close</button>
                      </>
                    )}
                    {t.assigned_engineer_id === user.id && t.status === 'resolved' && (
                      <button
                        onClick={(e) => handleAction(t, 'close', e)}
                        disabled={actionLoading === `close-${t.ticket_id}`}
                        className="px-1.5 py-0.5 bg-gray-600 hover:bg-gray-700 text-white rounded text-[9px] font-medium transition disabled:opacity-50"
                      >Close</button>
                    )}
                    {tab === 'open' && t.status === 'open' && (
                      <button
                        onClick={(e) => handleTake(t, e)}
                        disabled={actionLoading === t.ticket_number}
                        className="px-2 py-0.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded text-[9px] font-medium transition disabled:opacity-50"
                      >
                        {actionLoading === t.ticket_number ? '…' : 'Take'}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );

return (
    <Layout sidebarExtra={SidebarTicketList}>
      {/* Main area — KPIs + wide chat canvas */}
      <div className="h-full flex flex-col bg-gray-50 dark:bg-gray-950">

        {/* Top bar: KPIs + notification bell */}
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 shrink-0">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-base font-bold text-gray-800 dark:text-gray-100">Support Dashboard</h2>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Click a ticket in the sidebar to open a chat window
                {openChats.length > 0 && (
                  <span className="ml-2 px-2 py-0.5 bg-indigo-100 dark:bg-indigo-900 text-indigo-700 dark:text-indigo-300 rounded-full text-[10px] font-semibold">
                    {openChats.length}/{MAX_OPEN_CHATS} chats open
                  </span>
                )}
              </p>
            </div>

            {/* Notification bell */}
            <div className="relative">
              <button
                onClick={() => { setShowNotifPanel(v => !v); setUnreadNotifs(0); }}
                className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition relative"
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

          {/* KPI cards */}
          <div className="grid grid-cols-4 gap-3">
            <KPICard label="Open Pool"   value={kpis.openPool}   icon={Inbox}        color="blue"   />
            <KPICard label="My Active"   value={kpis.myActive}   icon={Ticket}       color="amber"  />
            <KPICard label="My Resolved" value={kpis.myResolved} icon={CheckCircle}  color="green"  />
            <KPICard label="Team Total"  value={kpis.teamTotal}  icon={UserCheck}    color="indigo" />
          </div>
        </div>

        {/* Chat canvas — dynamically tiles the open chat panels */}
        <div className="flex-1 flex p-4 gap-4 overflow-hidden">
          {openChats.length === 0 ? (
            <div className="m-auto text-center text-gray-400 dark:text-gray-600">
              <MessageSquare size={52} strokeWidth={1} className="mx-auto mb-3 opacity-40" />
              <p className="text-sm font-medium">No chats open</p>
              <p className="text-xs mt-1 opacity-70">Select a ticket from the sidebar, or take an open ticket to start chatting</p>
            </div>
          ) : (
            openChats.map((ticket, index) => (
              <ChatPanel
                key={ticket.ticket_id}
                ticket={ticket}
                isWidget={true}
                widgetIndex={index}
                onClose={() => closeChatWidget(ticket.ticket_id)}
                onStatusUpdate={handleStatusUpdate}
              />
            ))
          )}
        </div>
      </div>
    </Layout>
  );}
