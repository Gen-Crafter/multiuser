export interface User {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  is_verified: boolean;
  avatar_url?: string;
  created_at: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface LinkedInAccount {
  id: string;
  linkedin_email: string;
  linkedin_name?: string;
  linkedin_profile_url?: string;
  account_type: 'normal' | 'premium';
  status: 'active' | 'session_expired' | 'verification_required' | 'suspended' | 'cooldown' | 'warmup';
  checkpoint_url?: string;
  is_warming_up: boolean;
  warmup_day: number;
  risk_score: number;
  last_active_at?: string;
  created_at: string;
}

export interface Campaign {
  id: string;
  user_id: string;
  linkedin_account_id: string;
  name: string;
  campaign_type: 'post_generator' | 'connection_growth' | 'sales_outreach';
  status: 'draft' | 'active' | 'paused' | 'completed' | 'failed';
  topic?: string;
  tone?: string;
  target_audience?: string;
  icp_description?: string;
  target_industry?: string;
  target_job_titles?: string[];
  target_geography?: string;
  total_leads: number;
  total_sent: number;
  total_replies: number;
  total_meetings: number;
  conversion_rate: number;
  created_at: string;
  updated_at: string;
}

export interface Lead {
  id: string;
  campaign_id: string;
  linkedin_account_id: string;
  linkedin_url: string;
  linkedin_name?: string;
  headline?: string;
  company?: string;
  job_title?: string;
  location?: string;
  industry?: string;
  status: string;
  followup_count: number;
  next_followup_at?: string;
  sentiment_score: number;
  conversion_probability: number;
  created_at: string;
  updated_at: string;
}

export interface DashboardSummary {
  total_campaigns: number;
  active_campaigns: number;
  total_leads: number;
  total_connections_sent: number;
  total_connections_accepted: number;
  total_messages_sent: number;
  total_replies: number;
  total_meetings: number;
  overall_connection_rate: number;
  overall_reply_rate: number;
  overall_meeting_rate: number;
  overall_conversion_rate: number;
  risk_score: number;
  daily_usage: Record<string, number>;
  daily_limits: Record<string, number>;
}

export interface AnalyticsEntry {
  id: string;
  linkedin_account_id: string;
  date: string;
  connections_sent: number;
  connections_accepted: number;
  messages_sent: number;
  messages_received: number;
  profile_views: number;
  posts_created: number;
  connection_acceptance_rate: number;
  reply_rate: number;
  meeting_rate: number;
  risk_score: number;
}

export interface WSMessage {
  type: 'log' | 'campaign_update' | 'alert' | 'metric';
  payload: Record<string, unknown>;
  timestamp: string;
}
