'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { Lead } from '@/types';

const STATUS_BADGE: Record<string, string> = {
  discovered: 'badge-gray',
  profile_scraped: 'badge-gray',
  invite_sent: 'badge-blue',
  connected: 'badge-green',
  message_sent: 'badge-blue',
  replied: 'badge-green',
  interested: 'badge-green',
  not_interested: 'badge-red',
  meeting_booked: 'badge-green',
  converted: 'badge-green',
  objection: 'badge-yellow',
  do_not_contact: 'badge-red',
};

export default function LeadsPage() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('');

  useEffect(() => {
    const params: Record<string, string> = {};
    if (statusFilter) params.status_filter = statusFilter;
    api.getLeads(params).then(setLeads).catch(() => {}).finally(() => setLoading(false));
  }, [statusFilter]);

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
        <h1 className="text-2xl font-bold text-gray-900">Leads</h1>
        <div className="flex items-center gap-3">
          <select
            className="input w-48"
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setLoading(true); }}
          >
            <option value="">All statuses</option>
            <option value="discovered">Discovered</option>
            <option value="invite_sent">Invite Sent</option>
            <option value="connected">Connected</option>
            <option value="message_sent">Message Sent</option>
            <option value="replied">Replied</option>
            <option value="interested">Interested</option>
            <option value="meeting_booked">Meeting Booked</option>
            <option value="not_interested">Not Interested</option>
            <option value="objection">Objection</option>
          </select>
          <span className="text-sm text-gray-500">{leads.length} leads</span>
        </div>
      </div>

      {leads.length === 0 ? (
        <div className="card py-12 text-center text-gray-500">
          No leads found. Start a campaign to discover leads.
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">Name</th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">Company</th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">Title</th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">Status</th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">Sentiment</th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">Conv. Prob.</th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">Follow-ups</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {leads.map((lead) => {
                const sentimentColor = lead.sentiment_score > 0.3 ? 'text-green-600' : lead.sentiment_score < -0.3 ? 'text-red-600' : 'text-gray-600';
                const probColor = lead.conversion_probability > 0.5 ? 'text-green-600' : lead.conversion_probability > 0.2 ? 'text-yellow-600' : 'text-gray-500';
                return (
                  <tr key={lead.id} className="transition hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <div>
                        <a
                          href={lead.linkedin_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-medium text-primary-600 hover:underline"
                        >
                          {lead.linkedin_name || 'Unknown'}
                        </a>
                        {lead.location && <p className="text-xs text-gray-400">{lead.location}</p>}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-700">{lead.company || '—'}</td>
                    <td className="px-4 py-3 text-sm text-gray-700">{lead.job_title || '—'}</td>
                    <td className="px-4 py-3">
                      <span className={STATUS_BADGE[lead.status] || 'badge-gray'}>
                        {lead.status.replace(/_/g, ' ')}
                      </span>
                    </td>
                    <td className={`px-4 py-3 text-sm font-medium ${sentimentColor}`}>
                      {lead.sentiment_score.toFixed(2)}
                    </td>
                    <td className={`px-4 py-3 text-sm font-medium ${probColor}`}>
                      {(lead.conversion_probability * 100).toFixed(0)}%
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-700">
                      {lead.followup_count}
                      {lead.next_followup_at && (
                        <p className="text-xs text-gray-400">
                          Next: {new Date(lead.next_followup_at).toLocaleDateString()}
                        </p>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
