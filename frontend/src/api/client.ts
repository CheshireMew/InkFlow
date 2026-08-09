import type {
  Executor,
  ExperimentDetail,
  Generation,
  Handoff,
  HandoffCore,
  Project,
  ProjectActivity,
  ProjectDetail,
  Prompt,
  PromptStage,
  ProviderProfile,
  ReferenceItem,
  WritingRule,
} from '../types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(payload.detail ?? '请求失败')
  }
  return response.json() as Promise<T>
}

const post = <T>(path: string, payload?: unknown) =>
  request<T>(path, {
    method: 'POST',
    body: payload === undefined ? undefined : JSON.stringify(payload),
  })

const put = <T>(path: string, payload: unknown) =>
  request<T>(path, { method: 'PUT', body: JSON.stringify(payload) })

export const api = {
  health: () => request<Record<string, unknown>>('/api/health'),
  projects: () => request<Project[]>('/api/projects'),
  project: (id: string) => request<ProjectDetail>(`/api/projects/${id}`),
  projectActivity: (id: string) => request<ProjectActivity>(`/api/projects/${id}/activity`),
  createProject: (payload: { title: string; user_request: string; materials: string[] }) =>
    post<{ project_id: string }>('/api/projects', payload),
  updateProject: (id: string, user_request: string) =>
    put<{ project_id: string }>(`/api/projects/${id}`, { user_request }),
  addSource: (id: string, payload: { content?: string; url?: string }) =>
    post<{ source_id: string }>(`/api/projects/${id}/sources`, payload),
  updateSource: (projectId: string, sourceId: string, content: string) =>
    put<{ source_id: string }>(`/api/projects/${projectId}/sources/${sourceId}`, { content }),
  import100x: (library_root: string) =>
    post<Record<string, unknown>>('/api/references/import-100x', { library_root }),
  references: (includeInactive = true) =>
    request<ReferenceItem[]>(`/api/references?include_inactive=${includeInactive}`),
  reference: (id: string) => request<ReferenceItem>(`/api/references/${id}`),
  addReference: (payload: Omit<ReferenceItem, 'id' | 'body_preview' | 'formats_json' | 'techniques_json'> & { body: string; formats: string[]; techniques: string[] }) =>
    post<ReferenceItem>('/api/references', payload),
  updateReference: (id: string, payload: { kind: 'case' | 'hook'; title: string; body: string; formats: string[]; techniques: string[]; active: boolean }) =>
    put<ReferenceItem>(`/api/references/${id}`, payload),
  prepare: (id: string, payload: { executor: Executor; provider_profile_id?: string }) =>
    post<{ job_id: string }>(`/api/projects/${id}/prepare`, payload),
  retryJob: (id: string) => post<{ job_id: string; status: string }>(`/api/jobs/${id}/retry`),
  handoff: (id: string) => request<Handoff>(`/api/projects/${id}/handoff`),
  handoffs: (id: string) => request<Handoff[]>(`/api/projects/${id}/handoffs`),
  reviseHandoff: (id: string, core: HandoffCore) => put<Record<string, unknown>>(`/api/projects/${id}/handoff`, core),
  approveHandoff: (id: string) => post<Record<string, unknown>>(`/api/projects/${id}/handoff/approve`),
  rules: () => request<WritingRule[]>('/api/rules'),
  addRule: (payload: { name: string; body: string; activate: boolean }) => post<WritingRule>('/api/rules', payload),
  activateRule: (id: string) => post<WritingRule>(`/api/rules/${id}/activate`),
  prompts: (stage?: PromptStage) => request<Prompt[]>(`/api/prompts${stage ? `?stage=${stage}` : ''}`),
  savePrompt: (stage: PromptStage, payload: { name: string; system_prompt: string; user_template: string }) => put<Prompt>(`/api/prompts/${stage}`, payload),
  providers: () => request<ProviderProfile[]>('/api/providers'),
  configureProvider: (payload: { name: string; adapter: ProviderProfile['adapter']; base_url: string; model: string; api_key: string; parameters: Record<string, unknown>; activate: boolean }) => post<{ provider_profile_id: string }>('/api/providers', payload),
  activateProvider: (id: string) => post<ProviderProfile>(`/api/providers/${id}/activate`),
  testProvider: (id: string) => post<Record<string, unknown>>(`/api/providers/${id}/test`),
  generate: (id: string, payload: { executor: Executor; rule_id?: string; provider_profile_id?: string }) => post<{ experiment_id: string }>(`/api/projects/${id}/generate`, payload),
  batchFive: (id: string, payload: { executor: Executor; rule_id?: string; provider_profile_id?: string }) => post<{ experiment_id: string }>(`/api/projects/${id}/batch-five`, payload),
  compareRules: (id: string, payload: { rule_ids: string[]; provider_profile_id: string }) => post<{ experiment_id: string }>(`/api/projects/${id}/compare-rules`, payload),
  experiment: (id: string) => request<ExperimentDetail>(`/api/experiments/${id}`),
  results: (id: string) => request<Generation[]>(`/api/projects/${id}/results`),
  reviewResult: (id: string, state: Generation['review_state']) => put<Generation>(`/api/results/${id}/review`, { state }),
  editResult: (id: string, content: string) => post<Record<string, unknown>>(`/api/results/${id}/revisions`, { content }),
  exportUrl: (id: string) => `/api/results/${id}/export`,
}
