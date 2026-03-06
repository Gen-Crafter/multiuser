const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

class ApiClient {
  private token: string | null = null;

  setToken(token: string) {
    this.token = token;
    if (typeof window !== 'undefined') {
      localStorage.setItem('access_token', token);
    }
  }

  getToken(): string | null {
    if (this.token) return this.token;
    if (typeof window !== 'undefined') {
      this.token = localStorage.getItem('access_token');
    }
    return this.token;
  }

  clearToken() {
    this.token = null;
    if (typeof window !== 'undefined') {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
    }
  }

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string>),
    };

    const token = this.getToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
    });

    if (res.status === 401) {
      this.clearToken();
      if (typeof window !== 'undefined') {
        window.location.href = '/login';
      }
      throw new Error('Unauthorized');
    }

    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `API error: ${res.status}`);
    }

    if (res.status === 204) return undefined as T;
    return res.json();
  }

  // Auth
  async login(email: string, password: string) {
    const data = await this.request<{ access_token: string; refresh_token: string }>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    this.setToken(data.access_token);
    if (typeof window !== 'undefined') {
      localStorage.setItem('refresh_token', data.refresh_token);
    }
    return data;
  }

  async register(email: string, password: string, full_name: string) {
    return this.request('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, full_name }),
    });
  }

  // Users
  async getMe() {
    return this.request<import('@/types').User>('/api/v1/users/me');
  }

  // LinkedIn Accounts
  async getLinkedInAccounts() {
    return this.request<import('@/types').LinkedInAccount[]>('/api/v1/linkedin-accounts/');
  }

  async addLinkedInAccount(data: { linkedin_email: string; linkedin_password: string; account_type: string; proxy_url?: string }) {
    return this.request<import('@/types').LinkedInAccount>('/api/v1/linkedin-accounts/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async triggerLogin(accountId: string) {
    return this.request(`/api/v1/linkedin-accounts/${accountId}/login`, { method: 'POST' });
  }

  // Campaigns
  async getCampaigns(params?: { campaign_type?: string; status?: string }) {
    const query = new URLSearchParams(params as Record<string, string>).toString();
    return this.request<import('@/types').Campaign[]>(`/api/v1/campaigns/?${query}`);
  }

  async createCampaign(data: Record<string, unknown>) {
    return this.request<import('@/types').Campaign>('/api/v1/campaigns/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async startCampaign(id: string) {
    return this.request<import('@/types').Campaign>(`/api/v1/campaigns/${id}/start`, { method: 'POST' });
  }

  async pauseCampaign(id: string) {
    return this.request<import('@/types').Campaign>(`/api/v1/campaigns/${id}/pause`, { method: 'POST' });
  }

  async deleteCampaign(id: string) {
    return this.request(`/api/v1/campaigns/${id}`, { method: 'DELETE' });
  }

  // Leads
  async getLeads(params?: { campaign_id?: string; status_filter?: string }) {
    const query = new URLSearchParams(params as Record<string, string>).toString();
    return this.request<import('@/types').Lead[]>(`/api/v1/leads/?${query}`);
  }

  // Analytics
  async getDashboard() {
    return this.request<import('@/types').DashboardSummary>('/api/v1/analytics/dashboard');
  }

  async getDailyAnalytics(accountId: string, days = 30) {
    return this.request<import('@/types').AnalyticsEntry[]>(`/api/v1/analytics/daily?linkedin_account_id=${accountId}&days=${days}`);
  }
}

export const api = new ApiClient();
