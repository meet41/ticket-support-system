import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { ToastProvider } from './components/Toast';
import LoginPage from './pages/LoginPage';
import SupportDashboard from './pages/support/SupportDashboard';
import AdminDashboard from './pages/admin/AdminDashboard';

function PrivateRoute({ children, allowed }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="flex items-center justify-center h-screen text-gray-400">Loading...</div>;
  if (!user) return <Navigate to="/login" />;
  if (allowed && !allowed.includes(user.role)) {
    if (user.role === 'support') return <Navigate to="/support" />;
    if (user.role === 'admin') return <Navigate to="/admin" />;
    return <Navigate to="/login" />;
  }
  return children;
}

function RoleRedirect() {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" />;
  if (user.role === 'support') return <Navigate to="/support" />;
  if (user.role === 'admin') return <Navigate to="/admin" />;
  return <Navigate to="/login" />;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/support" element={<PrivateRoute allowed={['support']}><SupportDashboard /></PrivateRoute>} />
      <Route path="/admin" element={<PrivateRoute allowed={['admin']}><AdminDashboard /></PrivateRoute>} />
      <Route path="*" element={<RoleRedirect />} />
    </Routes>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <ToastProvider>
          <BrowserRouter>
            <AppRoutes />
          </BrowserRouter>
        </ToastProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}
