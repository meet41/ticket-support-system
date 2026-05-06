import { ThemeProvider } from './context/ThemeContext';
import { AuthProvider } from './context/AuthContext';
import { ToastProvider } from './components/Toast';
import ChatWidget from './components/ChatWidget';
import './styles/global.css';

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <ToastProvider>
          <ChatWidget />
        </ToastProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}
