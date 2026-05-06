import { useState, useEffect, useCallback } from 'react';
import { api } from '../services/api';
import { BarChart2, TrendingUp, ThumbsUp, ThumbsDown, Minus, Loader2, RefreshCw, Clock, Zap, Search, ChevronDown, ChevronUp } from 'lucide-react';

export default function AIAnalytics() {
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [trends, setTrends] = useState(null);
  const [trendsLoading, setTrendsLoading] = useState(false);
  const [groupBy, setGroupBy] = useState('subject');
  const [days, setDays] = useState(30);
  const [expandedLog, setExpandedLog] = useState(null);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.aiLogs();
      setLogs(data?.logs || []);
      setTotal(data?.total || 0);
    } catch {}
    setLoading(false);
  }, []);

  const fetchTrends = useCallback(async () => {
    setTrendsLoading(true);
    try {
      const data = await api.aiAnalyzeTrends({ days, group_by: groupBy });
      setTrends(data);
    } catch {}
    setTrendsLoading(false);
  }, [days, groupBy]);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);
  useEffect(() => { fetchTrends(); }, [fetchTrends]);

  const avgLatency = logs.length
    ? (logs.reduce((a, l) => a + (l.latency_ms || 0), 0) / logs.length).toFixed(0)
    : 0;
  const avgTokens = logs.length
    ? Math.round(logs.reduce((a, l) => a + (l.tokens_used || 0), 0) / logs.length)
    : 0;
  const helpfulCount = logs.filter(l => l.helpful === true).length;
  const notHelpfulCount = logs.filter(l => l.helpful === false).length;
  const ratedCount = helpfulCount + notHelpfulCount;
  const satisfactionRate = ratedCount > 0 ? Math.round((helpfulCount / ratedCount) * 100) : null;

  return (
    <div className="flex flex-col h-full overflow-y-auto bg-white dark:bg-gray-900">
      {/* Header */}
      <div className="p-5 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between shrink-0">
        <div>
          <h3 className="text-sm font-semibold flex items-center gap-2">
            <BarChart2 size={16} className="text-indigo-500" />
            AI Analytics
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            Performance metrics for AI queries
          </p>
        </div>
        <button
          onClick={() => { fetchLogs(); fetchTrends(); }}
          className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition"
          title="Refresh"
        >
          <RefreshCw size={15} />
        </button>
      </div>

      <div className="p-5 space-y-6">
        {/* KPI row */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatCard label="Total Queries" value={total} icon={Search} color="indigo" />
          <StatCard label="Avg Latency" value={avgLatency ? `${avgLatency}ms` : '—'} icon={Clock} color="amber" />
          <StatCard label="Avg Tokens" value={avgTokens || '—'} icon={Zap} color="blue" />
          <StatCard
            label="Satisfaction"
            value={satisfactionRate !== null ? `${satisfactionRate}%` : '—'}
            icon={satisfactionRate !== null && satisfactionRate >= 70 ? ThumbsUp : satisfactionRate !== null ? ThumbsDown : Minus}
            color={satisfactionRate !== null && satisfactionRate >= 70 ? 'green' : 'red'}
          />
        </div>

        {/* Trend Analysis */}
        <div className="rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
          <div className="p-4 border-b border-gray-200 dark:border-gray-800 flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <TrendingUp size={15} className="text-indigo-500" />
              <span className="text-sm font-medium">Ticket Trends</span>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <select
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
                className="px-2 py-1 text-xs rounded-lg border border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value={7}>Last 7 days</option>
                <option value={30}>Last 30 days</option>
                <option value={90}>Last 90 days</option>
                <option value={365}>Last year</option>
              </select>
              <select
                value={groupBy}
                onChange={(e) => setGroupBy(e.target.value)}
                className="px-2 py-1 text-xs rounded-lg border border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="subject">By Subject</option>
                <option value="status">By Status</option>
                <option value="priority">By Priority</option>
              </select>
            </div>
          </div>
          <div className="p-4">
            {trendsLoading ? (
              <div className="flex items-center gap-2 text-sm text-gray-400">
                <Loader2 size={15} className="animate-spin" /> Loading trends…
              </div>
            ) : trends ? (
              <div className="space-y-3">
                <p className="text-xs text-gray-500 dark:text-gray-400 italic">{trends.summary}</p>
                <div className="space-y-2">
                  {trends.trends.slice(0, 8).map((item) => (
                    <div key={item.label} className="flex items-center gap-3">
                      <span className="text-xs text-gray-600 dark:text-gray-300 w-32 shrink-0 truncate" title={item.label}>
                        {item.label}
                      </span>
                      <div className="flex-1 bg-gray-100 dark:bg-gray-800 rounded-full h-2 overflow-hidden">
                        <div
                          className="h-2 rounded-full bg-indigo-500 transition-all duration-500"
                          style={{ width: `${item.percentage}%` }}
                        />
                      </div>
                      <span className="text-xs text-gray-500 tabular-nums w-14 text-right">
                        {item.count} ({item.percentage}%)
                      </span>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-gray-400 text-right">
                  Total: {trends.total_tickets} ticket(s) in {trends.period_days} days
                </p>
              </div>
            ) : (
              <p className="text-sm text-gray-400">No trend data available.</p>
            )}
          </div>
        </div>

        {/* Recent AI Logs */}
        <div className="rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
          <div className="p-4 border-b border-gray-200 dark:border-gray-800">
            <h4 className="text-sm font-medium">Recent AI Queries</h4>
          </div>
          {loading ? (
            <div className="p-4 flex items-center gap-2 text-sm text-gray-400">
              <Loader2 size={15} className="animate-spin" /> Loading logs…
            </div>
          ) : logs.length === 0 ? (
            <p className="p-4 text-sm text-gray-400">No AI queries logged yet.</p>
          ) : (
            <div className="divide-y divide-gray-100 dark:divide-gray-800">
              {logs.slice(0, 20).map((log) => (
                <div key={log.id} className="p-4">
                  <div
                    className="flex items-start gap-3 cursor-pointer"
                    onClick={() => setExpandedLog(expandedLog === log.id ? null : log.id)}
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{log.query}</p>
                      <div className="flex items-center gap-3 mt-1 text-xs text-gray-400">
                        <span>{new Date(log.created_at).toLocaleString()}</span>
                        <span>{log.latency_ms}ms</span>
                        <span>{log.tokens_used} tokens</span>
                        {log.retrieved_ticket_ids?.length > 0 && (
                          <span>{log.retrieved_ticket_ids.length} ticket(s)</span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {log.helpful === true && (
                        <span className="text-emerald-500"><ThumbsUp size={13} /></span>
                      )}
                      {log.helpful === false && (
                        <span className="text-red-400"><ThumbsDown size={13} /></span>
                      )}
                      {expandedLog === log.id ? (
                        <ChevronUp size={14} className="text-gray-400" />
                      ) : (
                        <ChevronDown size={14} className="text-gray-400" />
                      )}
                    </div>
                  </div>
                  {expandedLog === log.id && (
                    <div className="mt-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-800 text-xs text-gray-600 dark:text-gray-300 leading-relaxed">
                      <strong>Response preview:</strong> {log.response_preview}
                      {log.retrieved_ticket_ids?.length > 0 && (
                        <div className="mt-2">
                          <strong>Ticket IDs used:</strong> {log.retrieved_ticket_ids.join(', ')}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, icon: Icon, color }) {
  const colorMap = {
    indigo: 'bg-indigo-50 text-indigo-600 dark:bg-indigo-950/50 dark:text-indigo-400',
    green: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-950/50 dark:text-emerald-400',
    amber: 'bg-amber-50 text-amber-600 dark:bg-amber-950/50 dark:text-amber-400',
    red: 'bg-red-50 text-red-600 dark:bg-red-950/50 dark:text-red-400',
    blue: 'bg-blue-50 text-blue-600 dark:bg-blue-950/50 dark:text-blue-400',
  };
  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl p-4 border border-gray-200 dark:border-gray-800">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">{label}</p>
          <p className="text-xl font-bold mt-1">{value}</p>
        </div>
        {Icon && (
          <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${colorMap[color] || colorMap.indigo}`}>
            <Icon size={17} />
          </div>
        )}
      </div>
    </div>
  );
}
