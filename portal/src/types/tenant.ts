export type TenantTier = 'free' | 'standard' | 'enterprise';
export type TenantStatus = 'active' | 'suspended' | 'pending' | 'deactivated';

export interface Organization {
  id: string;
  name: string;
  slug: string;
  tier: TenantTier;
  status: TenantStatus;
  contact_email: string;
  max_agents: number;
  max_teams: number;
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
}

export interface OrganizationCreate {
  name: string;
  slug: string;
  contact_email?: string;
  tier?: TenantTier;
}

export interface Team {
  id: string;
  org_id: string;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
}

export interface Project {
  id: string;
  team_id: string;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
}
