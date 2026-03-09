'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { LinkedInAccount } from '@/types';

const STATUS_BADGE: Record<string, string> = {
  active: 'badge-green',
  session_expired: 'badge-red',
  verification_required: 'badge-yellow',
  suspended: 'badge-red',
  cooldown: 'badge-yellow',
  warmup: 'badge-blue',
};

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<LinkedInAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [vncSession, setVncSession] = useState<any>(null);
  const [checkingStatus, setCheckingStatus] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = () => {
    api.getLinkedInAccounts().then(setAccounts).catch(() => {}).finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const startVncSession = async () => {
    setError('');
    try {
      const response = await api.startVncSession();
      setVncSession(response);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to start VNC session');
    }
  };

  const checkSessionStatus = async () => {
    if (!vncSession) return;
    setCheckingStatus(true);
    try {
      const response = await api.getVncSessionStatus(vncSession.session_id);
      setVncSession({ ...vncSession, ...response });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to check session status');
    } finally {
      setCheckingStatus(false);
    }
  };

  const saveAccountFromSession = async () => {
    if (!vncSession) return;
    setSaving(true);
    setError('');
    try {
      const response = await api.saveAccountFromVncSession(vncSession.session_id);
      setVncSession(null);
      load(); // Reload accounts list
      alert(`Account saved: ${response.linkedin_email}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to save account');
    } finally {
      setSaving(false);
    }
  };

  const cleanupSession = async () => {
    if (!vncSession) return;
    try {
      await api.cleanupVncSession(vncSession.session_id);
      setVncSession(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to cleanup session');
    }
  };

  const handleDelete = async (id: string) => {
    setError('');
    if (!window.confirm('Delete this LinkedIn account?')) return;

    try {
      await api.deleteLinkedInAccount(id);
      load();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to delete account';
      if (msg.includes('associated with') && window.confirm(`${msg}\n\nForce delete anyway?`)) {
        try {
          await api.deleteLinkedInAccount(id, { force: true });
          load();
          return;
        } catch (err2: unknown) {
          setError(err2 instanceof Error ? err2.message : 'Failed to delete account');
          return;
        }
      }
      setError(msg);
    }
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary-600 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">LinkedIn Accounts</h1>
        <button className="btn-primary" onClick={startVncSession} disabled={vncSession !== null}>
          {vncSession ? 'VNC Session Active' : '+ Add Account via VNC'}
        </button>
      </div>

      {error && <div className="rounded-lg bg-red-50 p-3 text-sm text-red-600">{error}</div>}

      {/* VNC Session Card */}
      {vncSession && (
        <div className="card border-2 border-blue-200 bg-blue-50">
          <h2 className="mb-4 text-lg font-semibold text-blue-900">VNC Session Active</h2>
          
          <div className="mb-4 grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <h3 className="mb-2 font-medium text-blue-800">Connect via Browser (Recommended)</h3>
              <a 
                href={vncSession.novnc_url} 
                target="_blank" 
                rel="noopener noreferrer"
                className="btn-primary w-full"
              >
                Open VNC in Browser
              </a>
              <p className="mt-1 text-xs text-blue-600">Password: vncpassword</p>
            </div>
            
            <div>
              <h3 className="mb-2 font-medium text-blue-800">VNC Client Connection</h3>
              <div className="rounded bg-blue-100 p-2 font-mono text-xs">
                Server: {vncSession.vnc_url}<br />
                Password: vncpassword
              </div>
            </div>
          </div>

          <div className="mb-4 rounded-lg bg-white p-3">
            <h3 className="mb-2 font-medium text-gray-800">Instructions:</h3>
            <ol className="list-decimal space-y-1 pl-4 text-sm text-gray-600">
              <li>Click "Open VNC in Browser" above</li>
              <li>Log into LinkedIn manually in the VNC browser</li>
              <li>After successful login, click "Check Status" below</li>
              <li>Once status shows "logged_in", click "Save Account"</li>
            </ol>
          </div>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <span className={`badge ${vncSession.status === 'logged_in' ? 'badge-green' : 'badge-yellow'}`}>
                {vncSession.status}
              </span>
              {vncSession.status !== 'logged_in' && (
                <button 
                  className="btn-secondary text-sm"
                  onClick={checkSessionStatus}
                  disabled={checkingStatus}
                >
                  {checkingStatus ? 'Checking...' : 'Check Status'}
                </button>
              )}
            </div>
            
            <div className="flex gap-2">
              {vncSession.status === 'logged_in' && (
                <button 
                  className="btn-primary"
                  onClick={saveAccountFromSession}
                  disabled={saving}
                >
                  {saving ? 'Saving...' : 'Save Account'}
                </button>
              )}
              <button 
                className="btn-danger"
                onClick={cleanupSession}
                disabled={saving}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Accounts List */}
      {accounts.length === 0 ? (
        <div className="card py-12 text-center text-gray-500">
          No LinkedIn accounts yet. Click "Add Account via VNC" to get started.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {accounts.map((a) => (
            <div key={a.id} className="card">
              <div className="mb-3 flex items-start justify-between">
                <div>
                  <h3 className="font-semibold text-gray-900">{a.linkedin_name || a.linkedin_email}</h3>
                  <p className="text-xs text-gray-500">{a.linkedin_email}</p>
                </div>
                <span className={STATUS_BADGE[a.status] || 'badge-gray'}>{a.status.replace(/_/g, ' ')}</span>
              </div>

              <div className="mb-4 grid grid-cols-3 gap-2 text-center text-xs">
                <div className="rounded-lg bg-gray-50 p-2">
                  <p className="font-bold text-gray-900 capitalize">{a.account_type}</p>
                  <p className="text-gray-500">Type</p>
                </div>
                <div className="rounded-lg bg-gray-50 p-2">
                  <p className="font-bold text-gray-900">{a.warmup_day}/7</p>
                  <p className="text-gray-500">Warmup</p>
                </div>
                <div className="rounded-lg bg-gray-50 p-2">
                  <p className={`font-bold ${a.risk_score < 30 ? 'text-green-600' : a.risk_score < 60 ? 'text-yellow-600' : 'text-red-600'}`}>
                    {a.risk_score}
                  </p>
                  <p className="text-gray-500">Risk</p>
                </div>
              </div>

              {a.is_warming_up && (
                <div className="mb-3">
                  <div className="mb-1 flex justify-between text-xs text-gray-500">
                    <span>Warmup Progress</span>
                    <span>{Math.round((a.warmup_day / 7) * 100)}%</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-gray-200">
                    <div className="h-full rounded-full bg-blue-500" style={{ width: `${(a.warmup_day / 7) * 100}%` }} />
                  </div>
                </div>
              )}

              {a.last_active_at && (
                <p className="mb-3 text-xs text-gray-400">
                  Last active: {new Date(a.last_active_at).toLocaleString()}
                </p>
              )}

              <div className="flex gap-2">
                <button className="btn-danger text-xs flex-1" onClick={() => handleDelete(a.id)}>Delete</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
