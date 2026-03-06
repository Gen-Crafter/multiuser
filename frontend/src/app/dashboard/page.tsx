'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { DashboardSummary } from '@/types';
import RealTimeLogs from '@/components/RealTimeLogs';

export default function DashboardPage() {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getDashboard().then(setData).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary-600 border-t-transparent" />
      </div>
    );
  }

  if (!data) {
    return <p className="text-gray-500">Failed to load dashboard data.</p>;
  }

  const stats = [
    { label: 'Active Campaigns', value: data.active_campaigns, total: data.total_campaigns, color: 'text-blue-600' },
    { label: 'Total Leads', value: data.total_leads, color: 'text-indigo-600' },
    { label: 'Connections Accepted', value: data.total_connections_accepted, rate: `${data.overall_connection_rate}%`, color: 'text-green-600' },
    { label: 'Messages Sent', value: data.total_messages_sent, color: 'text-purple-600' },
    { label: 'Replies', value: data.total_replies, rate: `${data.overall_reply_rate}%`, color: 'text-cyan-600' },
    { label: 'Meetings Booked', value: data.total_meetings, rate: `${data.overall_meeting_rate}%`, color: 'text-emerald-600' },
  ];

  const riskColor = data.risk_score < 30 ? 'text-green-600' : data.risk_score < 60 ? 'text-yellow-600' : 'text-red-600';
  const riskBg = data.risk_score < 30 ? 'bg-green-100' : data.risk_score < 60 ? 'bg-yellow-100' : 'bg-red-100';

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {stats.map((s) => (
          <div key={s.label} className="card">
            <p className="text-xs font-medium text-gray-500">{s.label}</p>
            <p className={`mt-1 text-2xl font-bold ${s.color}`}>{s.value.toLocaleString()}</p>
            {s.rate && <p className="mt-0.5 text-xs text-gray-400">Rate: {s.rate}</p>}
            {s.total !== undefined && <p className="mt-0.5 text-xs text-gray-400">of {s.total} total</p>}
          </div>
        ))}
      </div>

      {/* Risk Score + Usage */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Risk Gauge */}
        <div className="card">
          <h3 className="mb-4 text-sm font-semibold text-gray-900">Risk Score</h3>
          <div className="flex items-center gap-6">
            <div className={`flex h-24 w-24 items-center justify-center rounded-full ${riskBg}`}>
              <span className={`text-3xl font-bold ${riskColor}`}>{data.risk_score}</span>
            </div>
            <div className="text-sm text-gray-600">
              <p>{data.risk_score < 30 ? 'Low risk — operating safely.' : data.risk_score < 60 ? 'Moderate risk — consider slowing down.' : 'High risk — cooldown recommended!'}</p>
              <div className="mt-3 h-2 w-48 overflow-hidden rounded-full bg-gray-200">
                <div
                  className={`h-full rounded-full ${data.risk_score < 30 ? 'bg-green-500' : data.risk_score < 60 ? 'bg-yellow-500' : 'bg-red-500'}`}
                  style={{ width: `${data.risk_score}%` }}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Daily Usage vs Limits */}
        <div className="card">
          <h3 className="mb-4 text-sm font-semibold text-gray-900">Daily Usage vs Limits</h3>
          <div className="space-y-4">
            {Object.entries(data.daily_usage).map(([key, used]) => {
              const limit = data.daily_limits[key] || 100;
              const pct = Math.min(100, Math.round((used / limit) * 100));
              const barColor = pct > 80 ? 'bg-red-500' : pct > 50 ? 'bg-yellow-500' : 'bg-green-500';
              return (
                <div key={key}>
                  <div className="mb-1 flex justify-between text-xs">
                    <span className="capitalize text-gray-600">{key.replace('_', ' ')}</span>
                    <span className="text-gray-500">{used}/{limit}</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-gray-200">
                    <div className={`h-full rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Conversion Rate */}
      <div className="card">
        <h3 className="mb-2 text-sm font-semibold text-gray-900">Overall Conversion Rate</h3>
        <p className="text-4xl font-bold text-primary-600">{data.overall_conversion_rate}%</p>
        <p className="mt-1 text-xs text-gray-400">Leads to meetings</p>
      </div>

      {/* Real-time logs */}
      <RealTimeLogs />
    </div>
  );
}
