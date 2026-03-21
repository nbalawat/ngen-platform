export interface TenantUsage {
  tenant_id: string;
  total_cost: number;
  total_tokens: number;
  total_requests: number;
  models: Record<string, number>;
  hourly_cost?: Record<string, number>;
  daily_cost?: Record<string, number>;
  last_request_at?: number;
}

export interface UsageSummary {
  tenant_count: number;
  total_cost: number;
  total_tokens: number;
  total_requests: number;
}
