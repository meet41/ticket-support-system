import { useState, useRef, useEffect } from 'react';
import { Bell, Ticket } from 'lucide-react';

export default function NotificationPanel({ notifications = [], onClear, onTicketClick }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const handleClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const count = notifications.length;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="relative p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition"
      >
        <Bell size={20} />
        {count > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] bg-red-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center px-1">
            {count > 99 ? '99+' : count}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-11 w-80 bg-white dark:bg-gray-900 rounded-xl shadow-2xl border border-gray-200 dark:border-gray-800 z-50 max-h-96 overflow-hidden flex flex-col animate-fade-in">
          <div className="p-3 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between">
            <span className="font-semibold text-sm">Notifications ({count})</span>
            {count > 0 && (
              <button onClick={onClear} className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline">
                Clear all
              </button>
            )}
          </div>
          <div className="overflow-y-auto flex-1">
            {count === 0 ? (
              <p className="p-6 text-sm text-gray-400 text-center">No new notifications</p>
            ) : (
              notifications.map((n, i) => (
                <button
                  key={i}
                  onClick={() => { onTicketClick?.(n); setOpen(false); }}
                  className="w-full text-left p-3 hover:bg-gray-50 dark:hover:bg-gray-800 border-b border-gray-100 dark:border-gray-800 last:border-0 transition"
                >
                  <div className="flex items-start gap-2.5">
                    <Ticket size={15} className="text-indigo-500 mt-0.5 shrink-0" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">
                        {n.ticket_number || `TCK-${n.ticket_id}`}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                        {n.subject || n.event?.replace('_', ' ')}
                      </p>
                      {n.priority && (
                        <p className="text-xs text-gray-400 mt-0.5 capitalize">{n.priority} priority</p>
                      )}
                    </div>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
