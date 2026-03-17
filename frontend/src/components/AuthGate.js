import React, { useEffect, useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';
import api from '../api';
import { clearSession, getStoredSession, sessionAuthRequired, storeSession, subscribeSession } from '../utils/sessionAuth';

function AuthGate({ children }) {
  const required = sessionAuthRequired();
  const [checking, setChecking] = useState(required);
  const [session, setSession] = useState(() => getStoredSession());
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (!required) return;
    const existing = getStoredSession();
    if (!existing?.token) {
      setChecking(false);
      return;
    }
    api.get('/api/auth/me')
      .then((res) => {
        if (res.data?.success) {
          const next = { ...existing, ...(res.data.session || {}) };
          storeSession(next);
          setSession(next);
        } else {
          clearSession();
          setSession(null);
        }
      })
      .catch(() => {
        clearSession();
        setSession(null);
      })
      .finally(() => setChecking(false));
  }, [required]);

  useEffect(() => {
    if (!required) return undefined;
    return subscribeSession((nextSession) => {
      setSession(nextSession || null);
      setChecking(false);
    });
  }, [required]);

  const handleLogin = async (event) => {
    event.preventDefault();
    setPending(true);
    setError('');
    try {
      const res = await api.post('/api/auth/login', { username, password });
      if (res.data?.success) {
        const next = { token: res.data.token, ...(res.data.session || {}) };
        storeSession(next);
        setSession(next);
      } else {
        setError(res.data?.error || 'Login failed');
      }
    } catch (err) {
      setError(err.message || 'Login failed');
    } finally {
      setPending(false);
    }
  };

  if (!required) return children;
  if (checking) {
    return <div className="min-h-screen bg-navy-black text-white flex items-center justify-center font-mono text-xs uppercase tracking-widest">Verifying session...</div>;
  }
  if (session?.token) return children;

  return (
    <div className="min-h-screen bg-navy-black text-white flex items-center justify-center p-8">
      <form onSubmit={handleLogin} className="w-full max-w-md glass-dark border border-white/10 rounded-3xl p-8 space-y-6">
        <div>
          <h1 className="text-2xl font-black uppercase tracking-widest text-white">Secure Operator Sign-In</h1>
          <p className="text-[10px] font-mono uppercase tracking-widest text-gray-400 mt-2">Session token required for this deployment.</p>
        </div>
        <div className="space-y-2">
          <label className="text-[10px] font-mono uppercase tracking-widest text-gray-400">Username</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-sm font-mono text-white" />
        </div>
        <div className="space-y-2">
          <label className="text-[10px] font-mono uppercase tracking-widest text-gray-400">Password</label>
          <div className="relative">
            <input type={showPassword ? 'text' : 'password'} value={password} onChange={(e) => setPassword(e.target.value)} className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-3 pr-12 text-sm font-mono text-white" />
            <button
              type="button"
              onClick={() => setShowPassword((prev) => !prev)}
              className="absolute inset-y-0 right-0 flex items-center justify-center px-4 text-gray-500 hover:text-white transition-colors"
              aria-label={showPassword ? 'Hide password' : 'Show password'}
              aria-pressed={showPassword}
            >
              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {error && <div className="rounded-xl border border-lesnar-danger/30 bg-lesnar-danger/10 px-4 py-3 text-[10px] font-mono uppercase tracking-widest text-lesnar-danger">{error}</div>}
        <button disabled={pending} className="w-full btn-primary py-3 disabled:opacity-40">{pending ? 'AUTHENTICATING...' : 'LOGIN'}</button>
      </form>
    </div>
  );
}

export default AuthGate;
