import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../../context/AuthContext';
import { api, createNotificationWS } from '../../services/api';
import { useToast } from '../../components/Toast';
import Layout from '../../components/Layout';
import KPICard from '../../components/KPICard';
import { StatusBadge, PriorityBadge } from '../../components/StatusBadge';
import ChatPanel from '../../components/ChatPanel';
import NotificationPanel from '../../components/NotificationPanel';
import Modal from '../../components/Modal';
import { Ticket, Users, Inbox, CheckCircle, XCircle, Clock, UserPlus, RefreshCw, Search, Wifi, WifiOff, Eye } from 'lucide-react';
import { format } from 'date-fns';

export default function AdminDashboard() {
  const { user } = useAuth(); // Added to identify current logged in user
  const { addToast } = useToast();
  const [tab, setTab] = useState('tickets');
  const [tickets, setTickets] = useState([]);
  const [engineers, setEngineers] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ search: '', status: '' });
  const [notifications, setNotifications] = useState([]);

  // Add engineer
  const [addOpen, setAddOpen] = useState(false);
  const [engForm, setEngForm] = useState({ name: '', email: '', password: '', department: '', team: 'team1' });
  const [engLoading, setEngLoading] = useState(false);
  const [engError, setEngError] = useState('');

  const fetchAll = useCallback(async () => {
    try {
      const [t, e, c] = await Promise.all([api.getAllTickets(), api.getEngineers(), api.getCustomers()]);
      setTickets(t || []);
      setEngineers(e || []);
      setCustomers(c || []);
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  // Request notification permission
  useEffect(() => {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }
  }, []);

  // Notification WS — real-time, no manual refresh needed
  useEffect(() => {
    let ws;
    let reconnectTimer;
    const connect = () => {
      ws = createNotificationWS();
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.event === 'ticket_created') {
            addToast(`New ticket: ${data.ticket_number}`, 'info');
            setNotifications(prev => [data, ...prev]);
            // Add to tickets list immediately
            setTickets(prev => {
              const exists = prev.some(t => t.ticket_id === data.ticket_id);
              if (exists) return prev;
              return [{ ticket_id: data.ticket_id, ticket_number: data.ticket_number, subject: data.subject, priority: data.priority, status: 'open', created_at: data.created_at, assigned_engineer_id: null }, ...prev];
            });

            // Browser notification
            
              new Notification(`New Ticket: ${data.ticket_number}`, {
                body: `${data.subject} (Priority: ${data.priority})`,
                icon: '/favicon.ico',
                tag: `ticket-${data.ticket_id}`,
              });
          } else if (data.event === 'ticket_taken') {
            setTickets(prev => prev.map(t =>
              t.ticket_id === data.ticket_id ? { ...t, status: 'in_progress', assigned_engineer_id: data.engineer_id } : t
            ));
          } else if (data.event === 'ticket_resolved') {
            setTickets(prev => prev.map(t =>
              t.ticket_id === data.ticket_id ? { ...t, status: 'resolved' } : t
            ));
          } else if (data.event === 'ticket_closed') {
            setTickets(prev => prev.map(t =>
              t.ticket_id === data.ticket_id ? { ...t, status: 'closed' } : t
            ));
          } else if (data.event === 'ticket_reopened') {
            setTickets(prev => prev.map(t =>
              t.ticket_id === data.ticket_id ? { ...t, status: 'in_progress' } : t
            ));
          }
        } catch {}
      };
      ws.onclose = () => { reconnectTimer = setTimeout(connect, 3000); };
      ws.onerror = () => ws.close();
    };
    connect();
    return () => { clearTimeout(reconnectTimer); ws?.close(); };
  }, [addToast]);

  const engMap = Object.fromEntries(engineers.map(e => [String(e.support_id), e]));
  const custMap = Object.fromEntries(customers.map(c => [String(c.customer_id), c]));

  const filtered = tickets.filter(t => {
    if (filters.status && t.status !== filters.status) return false;
    if (filters.search) {
      const s = filters.search.toLowerCase();
      const eng = engMap[String(t.assigned_engineer_id)];
      const cust = custMap[String(t.customer_id)];
      if (
        !t.ticket_number.toLowerCase().includes(s) &&
        !t.subject.toLowerCase().includes(s) &&
        !(eng?.name || '').toLowerCase().includes(s) &&
        !(cust?.name || '').toLowerCase().includes(s)
      ) return false;
    }
    return true;
  });

  const kpis = {
    total: tickets.length,
    open: tickets.filter(t => t.status === 'open').length,
    inProgress: tickets.filter(t => t.status === 'in_progress').length,
    resolved: tickets.filter(t => t.status === 'resolved').length,
    engineers: engineers.length,
    // Fix: Count current user as online as well
    online: engineers.filter(e => e.is_online || (user && e.email === user.email)).length,
  };

  const handleSelect = async (ticket) => {
    try {
      const detail = await api.getTicket(ticket.ticket_number);
      setSelected(detail);
    } catch {
      setSelected(ticket);
    }
  };

  const handleAddEngineer = async (e) => {
    e.preventDefault();
    setEngError('');
    setEngLoading(true);
    try {
      await api.createStaff({ ...engForm, role_id: 2 });
      addToast('Engineer created successfully', 'success');
      setAddOpen(false);
      setEngForm({ name: '', email: '', password: '', department: '', team: 'team1' });
      fetchAll();
    } catch (err) {
      setEngError(err.message);
    }
    setEngLoading(false);
  };

  const inputCls = 'w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-sm outline-none focus:ring-2 focus:ring-indigo-500';
  const selectCls = 'px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-sm outline-none focus:ring-2 focus:ring-indigo-500';

  return (
    <Layout>
      <div className="h-full flex flex-col">
        {/* Header + KPIs */}
        <div className="p-5 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 shrink-0">
          <div className="flex items-center justify-between mb-5">
            <div>
              <h2 className="text-lg font-bold">Admin Dashboard</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">System overview & management</p>
            </div>
            <div className="flex items-center gap-2">
              <NotificationPanel notifications={notifications} onClear={() => setNotifications([])} onTicketClick={(n) => { setTab('tickets'); handleSelect({ ticket_number: n.ticket_number || `TCK-${n.ticket_id}`, ticket_id: n.ticket_id }); }} />
              <button onClick={fetchAll} className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition" title="Refresh">
                <RefreshCw size={16} />
              </button>
            </div>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <KPICard label="Total Tickets" value={kpis.total} icon={Ticket} color="indigo" />
            <KPICard label="Open" value={kpis.open} icon={Inbox} color="blue" />
            <KPICard label="In Progress" value={kpis.inProgress} icon={Clock} color="amber" />
            <KPICard label="Resolved" value={kpis.resolved} icon={CheckCircle} color="green" />
            <KPICard label="Engineers" value={kpis.engineers} icon={Users} color="purple" />
            <KPICard label="Online Now" value={kpis.online} icon={Wifi} color="green" />
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 px-5 shrink-0">
          {[
            { key: 'tickets', label: 'Ticket Assignments' },
            { key: 'engineers', label: 'Engineers' },
          ].map(t => (
            <button
              key={t.key}
              onClick={() => { setTab(t.key); setSelected(null); }}
              className={`px-4 py-3 text-sm font-medium transition border-b-2 ${
                tab === t.key ? 'text-indigo-600 dark:text-indigo-400 border-indigo-600 dark:border-indigo-400' : 'text-gray-400 border-transparent hover:text-gray-600'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 flex overflow-hidden">
          {tab === 'tickets' && (
            <>
              {/* Ticket table */}
              <div className={`${selected ? 'hidden lg:flex' : 'flex'} flex-col w-full lg:w-1/2 xl:w-[55%] border-r border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900`}>
                <div className="p-3 border-b border-gray-200 dark:border-gray-800 flex gap-2">
                  <div className="relative flex-1">
                    <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                    <input type="text" placeholder="Search tickets, customers, engineers..." value={filters.search} onChange={(e) => setFilters(f => ({ ...f, search: e.target.value }))} className="w-full pl-9 pr-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-sm outline-none focus:ring-2 focus:ring-indigo-500" />
                  </div>
                  <select value={filters.status} onChange={(e) => setFilters(f => ({ ...f, status: e.target.value }))} className={selectCls}>
                    <option value="">All Status</option>
                    <option value="open">Open</option>
                    <option value="in_progress">In Progress</option>
                    <option value="resolved">Resolved</option>
                    <option value="closed">Closed</option>
                  </select>
                </div>

                <div className="flex-1 overflow-y-auto">
                  {loading ? (
                    <p className="p-6 text-center text-gray-400 text-sm">Loading...</p>
                  ) : (
                    <table className="w-full text-sm">
                      <thead className="sticky top-0 bg-gray-50 dark:bg-gray-800 text-xs text-gray-500 dark:text-gray-400 uppercase">
                        <tr>
                          <th className="text-left px-4 py-2.5 font-medium">Ticket</th>
                          <th className="text-left px-4 py-2.5 font-medium">Customer</th>
                          <th className="text-left px-4 py-2.5 font-medium">Engineer</th>
                          <th className="text-left px-4 py-2.5 font-medium">Status</th>
                          <th className="text-left px-4 py-2.5 font-medium">Priority</th>
                          <th className="px-4 py-2.5 font-medium"></th>
                        </tr>
                      </thead>
                      <tbody>
                        {filtered.length === 0 ? (
                          <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-400">No tickets found</td></tr>
                        ) : (
                          filtered.map(t => {
                            const eng = engMap[String(t.assigned_engineer_id)];
                            const cust = custMap[String(t.customer_id)];
                            
                            // Fix: Ensure correct online check in assignment table
                            const isEngOnline = eng && (eng.is_online || (user && eng.email === user.email));
                            
                            return (
                              <tr
                                key={t.ticket_number}
                                onClick={() => handleSelect(t)}
                                className={`cursor-pointer border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition ${
                                  selected?.ticket_number === t.ticket_number ? 'bg-indigo-50/70 dark:bg-indigo-950/20' : ''
                                }`}
                              >
                                <td className="px-4 py-3">
                                  <p className="font-medium">{t.ticket_number}</p>
                                  <p className="text-xs text-gray-400 truncate max-w-[180px]">{t.subject}</p>
                                </td>
                                <td className="px-4 py-3 text-gray-600 dark:text-gray-400">
                                  {cust?.name || `#${t.customer_id}`}
                                </td>
                                <td className="px-4 py-3">
                                  {eng ? (
                                    <div className="flex items-center gap-1.5">
                                      <span className={`w-2 h-2 rounded-full shrink-0 ${isEngOnline ? 'bg-emerald-500' : 'bg-gray-400'}`} />
                                      <span className="text-gray-600 dark:text-gray-400">{eng.name}</span>
                                    </div>
                                  ) : (
                                    <span className="text-gray-400 italic">Unassigned</span>
                                  )}
                                </td>
                                <td className="px-4 py-3"><StatusBadge status={t.status} /></td>
                                <td className="px-4 py-3"><PriorityBadge priority={t.priority} /></td>
                                <td className="px-4 py-3">
                                  <Eye size={15} className="text-gray-400" />
                                </td>
                              </tr>
                            );
                          })
                        )}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>

              {/* Chat (read-only) */}
              <div className={`${selected ? 'flex' : 'hidden lg:flex'} flex-1 flex-col`}>
                <ChatPanel ticket={selected} onBack={() => setSelected(null)} readOnly />
              </div>
            </>
          )}

          {tab === 'engineers' && (
            <div className="flex-1 bg-white dark:bg-gray-900 overflow-auto">
              <div className="p-4 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between">
                <p className="text-sm text-gray-500">{engineers.length} engineers registered</p>
                <button onClick={() => setAddOpen(true)} className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium transition">
                  <UserPlus size={15} /> Add Engineer
                </button>
              </div>
              <table className="w-full text-sm">
                <thead className="bg-gray-50 dark:bg-gray-800 text-xs text-gray-500 dark:text-gray-400 uppercase">
                  <tr>
                    <th className="text-left px-5 py-3 font-medium">Name</th>
                    <th className="text-left px-5 py-3 font-medium">Email</th>
                    <th className="text-left px-5 py-3 font-medium">Department</th>
                    <th className="text-left px-5 py-3 font-medium">Team</th>
                    <th className="text-left px-5 py-3 font-medium">Role</th>
                    <th className="text-left px-5 py-3 font-medium">Status</th>
                    <th className="text-left px-5 py-3 font-medium">Active Tickets</th>
                  </tr>
                </thead>
                <tbody>
                  {engineers.map(eng => {
                    const activeCount = tickets.filter(t => t.assigned_engineer_id === eng.support_id && t.status === 'in_progress').length;
                    
                    // Fix: Ensure we flag the logged in user as online
                    const isOnline = eng.is_online || (user && eng.email === user.email);

                    return (
                      <tr key={eng.support_id} className="border-b border-gray-100 dark:border-gray-800">
                        <td className="px-5 py-3.5 font-medium">{eng.name}</td>
                        <td className="px-5 py-3.5 text-gray-500">{eng.email}</td>
                        <td className="px-5 py-3.5 text-gray-500 capitalize">{eng.department}</td>
                        <td className="px-5 py-3.5">
                          <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-700 dark:bg-indigo-900/50 dark:text-indigo-300 capitalize">
                            {eng.team || '—'}
                          </span>
                        </td>
                        <td className="px-5 py-3.5">
                          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                            eng.role_name === 'admin' ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/50 dark:text-purple-300' : 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300'
                          }`}>
                            {eng.role_name}
                          </span>
                        </td>
                        <td className="px-5 py-3.5">
                          <div className="flex items-center gap-1.5">
                            {isOnline ? <Wifi size={14} className="text-emerald-500" /> : <WifiOff size={14} className="text-gray-400" />}
                            <span className={`text-xs font-medium ${isOnline ? 'text-emerald-600 dark:text-emerald-400' : 'text-gray-400'}`}>
                              {isOnline ? 'Online' : 'Offline'}
                            </span>
                          </div>
                        </td>
                        <td className="px-5 py-3.5">
                          <span className={`text-sm font-semibold ${activeCount > 0 ? 'text-amber-600' : 'text-gray-400'}`}>
                            {activeCount}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Add Engineer Modal */}
      <Modal open={addOpen} onClose={() => setAddOpen(false)} title="Add Support Engineer">
        <form onSubmit={handleAddEngineer} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1.5">Full Name</label>
            <input required value={engForm.name} onChange={(e) => setEngForm(f => ({ ...f, name: e.target.value }))} placeholder="John Doe" className={inputCls} />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1.5">Email</label>
            <input required type="email" value={engForm.email} onChange={(e) => setEngForm(f => ({ ...f, email: e.target.value }))} placeholder="engineer@company.com" className={inputCls} />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1.5">Password</label>
            <input required type="password" minLength={6} value={engForm.password} onChange={(e) => setEngForm(f => ({ ...f, password: e.target.value }))} placeholder="Minimum 6 characters" className={inputCls} />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1.5">Department</label>
            <input required value={engForm.department} onChange={(e) => setEngForm(f => ({ ...f, department: e.target.value }))} placeholder="e.g. Technical, Billing" className={inputCls} />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Team</label>
            <select required value={engForm.team} onChange={(e) => setEngForm(f => ({ ...f, team: e.target.value }))} className={inputCls}>
              <option value="team1">Team 1</option>
              <option value="team2">Team 2</option>
              <option value="team3">Team 3</option>
            </select>
          </div>
          {engError && <p className="text-sm text-red-500">{engError}</p>}
          <button type="submit" disabled={engLoading} className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-medium text-sm transition disabled:opacity-50">
            {engLoading ? 'Creating...' : 'Create Engineer'}
          </button>
        </form>
      </Modal>
    </Layout>
  );
}