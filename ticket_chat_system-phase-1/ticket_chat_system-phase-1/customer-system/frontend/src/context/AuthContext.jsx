import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { getUser, getAccessToken, setTokens, clearTokens, api } from '../services/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const stored = getUser();
    const token = getAccessToken();
    if (stored && token) setUser(stored);
    setLoading(false);
  }, []);

  const login = useCallback(async (tokens) => {
    const basic = { role: 'customer', name: tokens.name };
    setTokens(tokens.access_token, tokens.refresh_token, basic);
    setUser(basic);
    try {
      const profile = await api.getMe();
      const fullUser = { role: 'customer', name: tokens.name, id: profile.customer_id, email: profile.email };
      setTokens(tokens.access_token, tokens.refresh_token, fullUser);
      setUser(fullUser);
    } catch { /* basic user already set */ }
  }, []);

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, login, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
