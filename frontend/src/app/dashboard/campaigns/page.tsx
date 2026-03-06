'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { Campaign, LinkedInAccount } from '@/types';

const TYPE_LABELS: Record<string, string> = {
  post_generator: 'Post Generator',
  connection_growth: 'Connection Growth',
  sales_outreach: 'Sales Outreach',
};

const STATUS_BADGE: Record<string, string> = {
  draft: 'badge-gray',
  active: 'badge-green',
  paused: 'badge-yellow',
  completed: 'badge-blue',
  failed: 'badge-red',
};

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [accounts, setAccounts] = useState<LinkedInAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);

  // Create form state
  const [form, setForm] = useState({
    name: '',
    campaign_type: 'connection_growth',
    linkedin_account_id: '',
    topic: '',
    tone: 'professional',
    target_audience: '',
    icp_description: '',
    target_industry: '',
    target_geography: '',
  });

  const load = () => {
    Promise.all([api.getCampaigns(), api.getLinkedInAccounts()])
      .then(([c, a]) => { setCampaigns(c); setAccounts(a); })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.createCampaign(form);
      setShowCreate(false);
      setForm({ ...form, name: '', topic: '', icp_description: '' });
      load();
    } catch {}
  };

  const handleStart = async (id: string) => {
    await api.startCampaign(id);
    load();
  };

  const handlePause = async (id: string) => {
    await api.pauseCampaign(id);
    load();
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this campaign?')) return;
    await api.deleteCampaign(id);
    load();
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
        <h1 className="text-2xl font-bold text-gray-900">Campaigns</h1>
        <button className="btn-primary" onClick={() => setShowCreate(!showCreate)}>
          {showCreate ? 'Cancel' : '+ New Campaign'}
        </button>
      </div>

      {/* Create form */}
      {showCreate && (
        <form onSubmit={handleCreate} className="card space-y-4">
          <h2 className="text-lg font-semibold">Create Campaign</h2>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">Name</label>
              <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">Type</label>
              <select className="input" value={form.campaign_type} onChange={(e) => setForm({ ...form, campaign_type: e.target.value })}>
                <option value="connection_growth">Connection Growth</option>
                <option value="sales_outreach">Sales Outreach</option>
                <option value="post_generator">Post Generator</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">LinkedIn Account</label>
              <select className="input" value={form.linkedin_account_id} onChange={(e) => setForm({ ...form, linkedin_account_id: e.target.value })} required>
                <option value="">Select account</option>
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>{a.linkedin_email} ({a.status})</option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">Target Industry</label>
              <input className="input" value={form.target_industry} onChange={(e) => setForm({ ...form, target_industry: e.target.value })} />
            </div>
          </div>

          {form.campaign_type === 'post_generator' && (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">Topic</label>
                <input className="input" value={form.topic} onChange={(e) => setForm({ ...form, topic: e.target.value })} />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">Tone</label>
                <select className="input" value={form.tone} onChange={(e) => setForm({ ...form, tone: e.target.value })}>
                  <option value="professional">Professional</option>
                  <option value="casual">Casual</option>
                  <option value="thought_leader">Thought Leader</option>
                  <option value="storytelling">Storytelling</option>
                </select>
              </div>
            </div>
          )}

          {(form.campaign_type === 'connection_growth' || form.campaign_type === 'sales_outreach') && (
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">ICP Description</label>
              <textarea className="input" rows={3} value={form.icp_description} onChange={(e) => setForm({ ...form, icp_description: e.target.value })} placeholder="Describe your ideal customer profile..." />
            </div>
          )}

          <button type="submit" className="btn-primary">Create Campaign</button>
        </form>
      )}

      {/* Campaigns list */}
      {campaigns.length === 0 ? (
        <div className="card py-12 text-center text-gray-500">
          No campaigns yet. Create your first campaign above.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
          {campaigns.map((c) => (
            <div key={c.id} className="card">
              <div className="mb-3 flex items-start justify-between">
                <div>
                  <h3 className="font-semibold text-gray-900">{c.name}</h3>
                  <p className="text-xs text-gray-500">{TYPE_LABELS[c.campaign_type] || c.campaign_type}</p>
                </div>
                <span className={STATUS_BADGE[c.status] || 'badge-gray'}>{c.status}</span>
              </div>

              <div className="mb-4 grid grid-cols-2 gap-2 text-center text-xs">
                <div className="rounded-lg bg-gray-50 p-2">
                  <p className="font-bold text-gray-900">{c.total_leads}</p>
                  <p className="text-gray-500">Leads</p>
                </div>
                <div className="rounded-lg bg-gray-50 p-2">
                  <p className="font-bold text-gray-900">{c.total_sent}</p>
                  <p className="text-gray-500">Sent</p>
                </div>
                <div className="rounded-lg bg-gray-50 p-2">
                  <p className="font-bold text-gray-900">{c.total_replies}</p>
                  <p className="text-gray-500">Replies</p>
                </div>
                <div className="rounded-lg bg-gray-50 p-2">
                  <p className="font-bold text-gray-900">{c.total_meetings}</p>
                  <p className="text-gray-500">Meetings</p>
                </div>
              </div>

              <div className="mb-3">
                <div className="mb-1 flex justify-between text-xs text-gray-500">
                  <span>Conversion</span>
                  <span>{c.conversion_rate}%</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-gray-200">
                  <div className="h-full rounded-full bg-primary-500" style={{ width: `${Math.min(100, c.conversion_rate)}%` }} />
                </div>
              </div>

              <div className="flex gap-2">
                {c.status === 'draft' || c.status === 'paused' ? (
                  <button className="btn-primary flex-1 text-xs" onClick={() => handleStart(c.id)}>Start</button>
                ) : c.status === 'active' ? (
                  <button className="btn-secondary flex-1 text-xs" onClick={() => handlePause(c.id)}>Pause</button>
                ) : null}
                <button className="btn-danger text-xs" onClick={() => handleDelete(c.id)}>Delete</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
