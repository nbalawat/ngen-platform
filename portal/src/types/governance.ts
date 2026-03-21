export type PolicyType = 'content_filter' | 'cost_limit' | 'tool_restriction' | 'rate_limit';
export type PolicyAction = 'block' | 'warn' | 'log' | 'escalate';
export type Severity = 'low' | 'medium' | 'high' | 'critical';

export interface Policy {
  id: string;
  name: string;
  description: string;
  policy_type: PolicyType;
  namespace: string;
  action: PolicyAction;
  severity: Severity;
  rules: Record<string, unknown>;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface Violation {
  policy_id: string;
  policy_name: string;
  policy_type: PolicyType;
  action: PolicyAction;
  severity: Severity;
  message: string;
  details: Record<string, unknown>;
}

export interface EvalResult {
  allowed: boolean;
  violations: Violation[];
  warnings: Violation[];
  evaluated_policies: number;
}
