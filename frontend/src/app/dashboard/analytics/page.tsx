'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { DashboardSummary, LinkedInAccount, AnalyticsEntry } from '@/types';

export default function AnalyticsPage() {
  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null);
  const [accounts, setAccounts] = useState<LinkedInAccount[]>([]);
  const [selectedAccount, setSelectedAccount] = useState('');
  const [daily, setDaily] = useState<AnalyticsEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.getDashboard(), api.getLinkedInAccounts()])
      .then(([d, a]) => {
        setDashboard(d);
        setAccounts(a);
        if (a.length > 0) setSelectedAccount(a[0].id);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (selectedAccount) {
      api.getDailyAnalytics(selectedAccount, 30).then(setDaily).catch(() => {});
    }
  }, [selectedAccount]);

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
        <h1 className="text-2xl font-bold text-gray-900">Analytics</h1>
        {accounts.length > 0 && (
          <select
            className="input w-64"
            value={selectedAccount}
            onChange={(e) => setSelectedAccount(e.target.value)}
          >
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>{a.linkedin_email}</option>
            ))}
          </select>
        )}
      </div>

      {/* Overview Cards */}
      {dashboard && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
          <div className="card text-center">
            <p className="text-xs font-medium text-gray-500">Connection Rate</p>
            <p className="mt-1 text-3xl font-bold text-green-600">{dashboard.overall_connection_rate}%</p>
          </div>
          <div className="card text-center">
            <p className="text-xs font-medium text-gray-500">Reply Rate</p>
            <p className="mt-1 text-3xl font-bold text-blue-600">{dashboard.overall_reply_rate}%</p>
          </div>
          <div className="card text-center">
            <p className="text-xs font-medium text-gray-500">Meeting Rate</p>
            <p className="mt-1 text-3xl font-bold text-purple-600">{dashboard.overall_meeting_rate}%</p>
          </div>
          <div className="card text-center">
            <p className="text-xs font-medium text-gray-500">Conversion Rate</p>
            <p className="mt-1 text-3xl font-bold text-emerald-600">{dashboard.overall_conversion_rate}%</p>
          </div>
          <div className="card text-center">
            <p className="text-xs font-medium text-gray-500">Risk Score</p>
            <p className={`mt-1 text-3xl font-bold ${dashboard.risk_score < 30 ? 'text-green-600' : dashboard.risk_score < 60 ? 'text-yellow-600' : 'text-red-600'}`}>
              {dashboard.risk_score}
            </p>
          </div>
        </div>
      )}

      {/* Daily Analytics Table */}
      {daily.length > 0 ? (
        <div className="card overflow-x-auto">
          <h2 className="mb-4 text-lg font-semibold text-gray-900">Daily Activity (Last 30 days)</h2>
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-3 py-2 text-left text-xs font-semibold uppercase text-gray-500">Date</th>
                <th className="px-3 py-2 text-right text-xs font-semibold uppercase text-gray-500">Conn. Sent</th>
                <th className="px-3 py-2 text-right text-xs font-semibold uppercase text-gray-500">Accepted</th>
                <th className="px-3 py-2 text-right text-xs font-semibold uppercase text-gray-500">Msgs Sent</th>
                <th className="px-3 py-2 text-right text-xs font-semibold uppercase text-gray-500">Msgs Received</th>
                <th className="px-3 py-2 text-right text-xs font-semibold uppercase text-gray-500">Profile Views</th>
                <th className="px-3 py-2 text-right text-xs font-semibold uppercase text-gray-500">Posts</th>
                <th className="px-3 py-2 text-right text-xs font-semibold uppercase text-gray-500">Accept %</th>
                <th className="px-3 py-2 text-right text-xs font-semibold uppercase text-gray-500">Reply %</th>
                <th className="px-3 py-2 text-right text-xs font-semibold uppercase text-gray-500">Risk</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {daily.map((d) => (
                <tr key={d.id} className="hover:bg-gray-50">
                  <td className="px-3 py-2 font-medium text-gray-900">{d.date}</td>
                  <td className="px-3 py-2 text-right">{d.connections_sent}</td>
                  <td className="px-3 py-2 text-right">{d.connections_accepted}</td>
                  <td className="px-3 py-2 text-right">{d.messages_sent}</td>
                  <td className="px-3 py-2 text-right">{d.messages_received}</td>
                  <td className="px-3 py-2 text-right">{d.profile_views}</td>
                  <td className="px-3 py-2 text-right">{d.posts_created}</td>
                  <td className="px-3 py-2 text-right text-green-600">{d.connection_acceptance_rate}%</td>
                  <td className="px-3 py-2 text-right text-blue-600">{d.reply_rate}%</td>
                  <td className="px-3 py-2 text-right">
                    <span className={`badge ${d.risk_score < 30 ? 'badge-green' : d.risk_score < 60 ? 'badge-yellow' : 'badge-red'}`}>
                      {d.risk_score}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="card py-12 text-center text-gray-500">
          No analytics data yet. Data will appear after campaigns run.
        </div>
      )}
    </div>
  );
}
