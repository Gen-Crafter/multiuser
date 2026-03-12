'use client';

import Link from 'next/link';
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

  const load = () => {
    api.getLinkedInAccounts().then(setAccounts).catch(() => {}).finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

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
        <Link href="/dashboard/linkedin-keeper" className="btn-primary">
          Open LinkedIn Session Keeper
        </Link>
      </div>

      {error && <div className="rounded-lg bg-red-50 p-3 text-sm text-red-600">{error}</div>}

      {/* Accounts List */}
      {accounts.length === 0 ? (
        <div className="card py-12 text-center text-gray-500">
          No LinkedIn accounts yet. Use the LinkedIn Session Keeper to log in and save your first account.
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
