import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { useNavigate } from 'react-router-dom';
import { api, getRefreshToken } from '../services/api';
import { Ticket, LogOut, Sun, Moon, Shield, Headphones, User, LayoutDashboard } from 'lucide-react';

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const { dark, toggle } = useTheme();
  const navigate = useNavigate();

  const handleLogout = async () => {
    const rt = getRefreshToken();
    try {
      if (user.role === 'customer') await api.customerLogout(rt);
      else await api.staffLogout(rt);
    } catch { /* ignore */ }
    logout();
    navigate('/login');
  };

  const RoleIcon = user?.role === 'admin' ? Shield : user?.role === 'support' ? Headphones : User;

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50 dark:bg-gray-950">
      {/* Sidebar */}
      <aside className="w-60 bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 flex flex-col shrink-0">
        <div className="p-5 border-b border-gray-200 dark:border-gray-800">
          <h1 className="text-lg font-bold text-indigo-600 dark:text-indigo-400 flex items-center gap-2">
            <Ticket size={22} /> TicketDesk
          </h1>
        </div>

        <div className="p-4 border-b border-gray-200 dark:border-gray-800">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-indigo-100 dark:bg-indigo-900/50 flex items-center justify-center">
              <RoleIcon size={16} className="text-indigo-600 dark:text-indigo-400" />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-medium truncate">{user?.name}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400 capitalize">{user?.role}</p>
            </div>
          </div>
        </div>

        <nav className="flex-1 p-3">
          <div className="flex items-center gap-2 px-3 py-2.5 rounded-lg bg-indigo-50 dark:bg-indigo-950/50 text-indigo-700 dark:text-indigo-300 text-sm font-medium">
            <LayoutDashboard size={16} /> Dashboard
          </div>
        </nav>

        <div className="p-3 space-y-1 border-t border-gray-200 dark:border-gray-800">
          <button onClick={toggle} className="w-full flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-sm text-gray-600 dark:text-gray-400 transition">
            {dark ? <Sun size={16} /> : <Moon size={16} />}
            {dark ? 'Light Mode' : 'Dark Mode'}
          </button>
          <button onClick={handleLogout} className="w-full flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-950/50 text-sm text-red-600 dark:text-red-400 transition">
            <LogOut size={16} /> Logout
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-hidden">
        {children}
      </main>
    </div>
  );
}
