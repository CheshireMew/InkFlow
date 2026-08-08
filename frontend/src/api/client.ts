export type Project = {
  id: string
  title: string
  user_request: string
  created_at: string
  updated_at: string
}

export type Source = {
  id: string
  content: string
  kind: string
  created_at: string
}

export type Job = {
  id: string
  kind: string
  executor: string
  status: string
  error?: string | null
}

export type ProjectDetail = {
  project: Project
  sources: Source[]
  jobs: Job[]
  experiments: Record<string, unknown>[]
}

export type HandoffCore = {
  user_request: string
  purified_material: string
  reference_cases: string[]
  reference_hooks: string[]
  other_inputs: string
}

export type Handoff = {
  handoff: { id: string; revision: number; status: string; core_hash: string }
  core: HandoffCore
}

export type WritingRule = {
  id: string
  name: string
  revision: number
  body: string
  body_hash: string
  active: boolean
}

export type Generation = {
  id: string
  content: string
  writing_rule_id: string
  output_index: number
  selected: boolean
  created_at: string
}

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

export const api = {
  projects: () => request<Project[]>('/api/projects'),
  project: (id: string) => request<ProjectDetail>(`/api/projects/${id}`),
  createProject: (payload: { title: string; user_request: string; materials: string[] }) =>
    request<{ project_id: string }>('/api/projects', { method: 'POST', body: JSON.stringify(payload) }),
  addSource: (id: string, content: string) =>
    request<{ source_id: string }>(`/api/projects/${id}/sources`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    }),
  import100x: (library_root: string) =>
    request<Record<string, unknown>>('/api/references/import-100x', {
      method: 'POST',
      body: JSON.stringify({ library_root }),
    }),
  prepare: (id: string, executor: 'external' | 'api', run: boolean) =>
    request<{ job_id: string }>(`/api/projects/${id}/prepare`, {
      method: 'POST',
      body: JSON.stringify({ executor, run }),
    }),
  handoff: (id: string) => request<Handoff>(`/api/projects/${id}/handoff`),
  reviseHandoff: (id: string, core: HandoffCore) =>
    request<Record<string, unknown>>(`/api/projects/${id}/handoff`, {
      method: 'PUT',
      body: JSON.stringify(core),
    }),
  approveHandoff: (id: string) =>
    request<Record<string, unknown>>(`/api/projects/${id}/handoff/approve`, { method: 'POST' }),
  rules: () => request<WritingRule[]>('/api/rules'),
  addRule: (payload: { name: string; body: string; activate: boolean }) =>
    request<WritingRule>('/api/rules', { method: 'POST', body: JSON.stringify(payload) }),
  activateRule: (id: string) => request<WritingRule>(`/api/rules/${id}/activate`, { method: 'POST' }),
  configureProvider: (payload: {
    name: string
    adapter: 'openai-compatible-chat' | 'openai-responses'
    base_url: string
    model: string
    api_key: string
    parameters: Record<string, unknown>
    activate: boolean
  }) => request<{ provider_profile_id: string }>('/api/providers', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  generate: (
    id: string,
    payload: {
      executor: 'external' | 'api'
      run: boolean
      rule_id?: string
      batch_five: boolean
    },
  ) => request<{ experiment_id: string }>(`/api/projects/${id}/generate`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  compareRules: (id: string, rule_ids: string[], executor: 'external' | 'api', run: boolean) =>
    request<{ experiment_id: string }>(`/api/projects/${id}/compare-rules`, {
      method: 'POST',
      body: JSON.stringify({ rule_ids, executor, run }),
    }),
  results: (id: string) => request<Generation[]>(`/api/projects/${id}/results`),
  selectResult: (id: string) => request<Generation>(`/api/results/${id}/select`, { method: 'POST' }),
}
