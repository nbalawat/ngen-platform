import { apiFetch } from './client';
import { API } from '../lib/constants';
import type { Organization, OrganizationCreate, Team, Project } from '../types/tenant';

export const tenantApi = {
  listOrgs: () => apiFetch<Organization[]>(`${API.tenant}/api/v1/orgs`),
  getOrg: (id: string) => apiFetch<Organization>(`${API.tenant}/api/v1/orgs/${id}`),
  createOrg: (data: OrganizationCreate) => apiFetch<Organization>(`${API.tenant}/api/v1/orgs`, { method: 'POST', body: JSON.stringify(data) }),
  updateOrg: (id: string, data: Partial<OrganizationCreate>) => apiFetch<Organization>(`${API.tenant}/api/v1/orgs/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteOrg: (id: string) => apiFetch<void>(`${API.tenant}/api/v1/orgs/${id}`, { method: 'DELETE' }),

  listTeams: (orgId: string) => apiFetch<Team[]>(`${API.tenant}/api/v1/orgs/${orgId}/teams`),
  createTeam: (orgId: string, data: { name: string; slug: string }) => apiFetch<Team>(`${API.tenant}/api/v1/orgs/${orgId}/teams`, { method: 'POST', body: JSON.stringify(data) }),
  deleteTeam: (orgId: string, teamId: string) => apiFetch<void>(`${API.tenant}/api/v1/orgs/${orgId}/teams/${teamId}`, { method: 'DELETE' }),

  listProjects: (orgId: string, teamId: string) => apiFetch<Project[]>(`${API.tenant}/api/v1/orgs/${orgId}/teams/${teamId}/projects`),
  createProject: (orgId: string, teamId: string, data: { name: string; slug: string }) => apiFetch<Project>(`${API.tenant}/api/v1/orgs/${orgId}/teams/${teamId}/projects`, { method: 'POST', body: JSON.stringify(data) }),
};
