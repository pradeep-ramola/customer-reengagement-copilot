const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type PurchaseSummary = {
  purchase_count: number;
  total_spend: number;
  last_purchase_date: string | null;
  latest_products: string[];
};

export type Customer = {
  id: number;
  first_name: string;
  last_name: string;
  email: string;
  phone: string | null;
  email_opt_in: boolean;
  sms_opt_in: boolean;
  unsubscribed: boolean;
  lifetime_value: number;
  engagement_score: number;
  purchase_summary: PurchaseSummary;
};

export type Campaign = {
  id: number;
  name: string;
  product_name: string;
  product_description: string;
  product_category: string;
  launch_offer: string | null;
  status: string;
  error_message: string | null;
  created_at: string;
};

export type Draft = {
  id: number;
  campaign_result_id: number;
  email_subject: string | null;
  email_body: string | null;
  sms_body: string | null;
  status: string;
  created_at: string;
  updated_at: string;
};

export type CampaignResult = {
  id: number;
  campaign_id: number;
  customer: {
    id: number;
    first_name: string;
    last_name: string;
    email: string;
    phone: string | null;
    email_opt_in: boolean;
    sms_opt_in: boolean;
    unsubscribed: boolean;
    lifetime_value: number;
    engagement_score: number;
  };
  buyer_score: number;
  score_breakdown_json: Record<string, number>;
  ranking_reason: string;
  recommended_channel: string;
  compliance_status: string;
  created_at: string;
  draft: Draft | null;
};

export type CampaignRun = {
  campaign_id: number;
  status: string;
  error_message: string | null;
  results: Array<{
    result_id: number;
    customer_id: number;
    customer_name: string;
    buyer_score: number;
    recommended_channel: string;
    compliance_status: string;
    draft_status: string | null;
    ranking_reason: string;
  }>;
};

export type CampaignCreate = {
  name: string;
  product_name: string;
  product_description: string;
  product_category: string;
  launch_offer?: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...init?.headers
    }
  });
  if (!response.ok) {
    let message = `Request failed with ${response.status}`;
    try {
      const body = await response.json();
      message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail || body);
    } catch {
      message = await response.text();
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export function exportUrl(campaignId: string | number) {
  return `${API_URL}/campaigns/${campaignId}/export`;
}

export const api = {
  seedDemo: () => request<{ inserted_customers: number; skipped_existing_customers: number; demo_customers_total: number }>("/demo/seed", { method: "POST" }),
  getCustomers: () => request<Customer[]>("/customers"),
  uploadCustomers: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return request<{ customers_created: number; purchases_created: number }>("/customers/upload", {
      method: "POST",
      body: formData
    });
  },
  createCampaign: (payload: CampaignCreate) =>
    request<CampaignRun>("/campaigns", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  getCampaign: (campaignId: string | number) => request<Campaign>(`/campaigns/${campaignId}`),
  getCampaignResults: (campaignId: string | number) => request<CampaignResult[]>(`/campaigns/${campaignId}/results`),
  updateDraft: (draftId: number, payload: Partial<Pick<Draft, "email_subject" | "email_body" | "sms_body">>) =>
    request<Draft>(`/drafts/${draftId}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  regenerateDraft: (draftId: number, payload: { tone: string; instruction?: string }) =>
    request<Draft>(`/drafts/${draftId}/regenerate`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  approveDraft: (draftId: number) =>
    request<{ draft: Draft; message: string }>(`/drafts/${draftId}/approve`, { method: "POST" }),
  rejectDraft: (draftId: number) =>
    request<{ draft: Draft; message: string }>(`/drafts/${draftId}/reject`, { method: "POST" }),
  sendMock: (draftId: number) =>
    request<{ draft: Draft; message: string }>(`/drafts/${draftId}/send-mock`, { method: "POST" })
};
