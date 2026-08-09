export type Executor = 'external' | 'api'
export type PromptStage = 'prepare_material' | 'select_references' | 'generate'

export type Project = {
  id: string
  title: string
  user_request: string
  input_revision: number
  created_at: string
  updated_at: string
}

export type Source = {
  id: string
  kind: string
  content: string
  provenance_json: Record<string, unknown>
  created_at: string
}

export type JobAttempt = {
  id: string
  attempt: number
  status: string
  error?: string | null
  format_error?: string | null
  raw_response?: string | null
  completed_at?: string | null
}

export type Job = {
  id: string
  kind: PromptStage
  executor: Executor
  status: string
  payload_json: Record<string, unknown>
  attempts: JobAttempt[]
  created_at: string
}

export type Experiment = {
  id: string
  project_id: string
  handoff_id: string
  kind: 'single' | 'batch_five' | 'compare_rules'
  executor: Executor
  input_package_hash: string
  status: string
  created_at: string
  completed_at?: string | null
}

export type ProjectDetail = {
  project: Project
  sources: Source[]
  jobs: Job[]
  experiments: Experiment[]
}

export type HandoffCore = {
  user_request: string
  purified_material: string
  reference_cases: string[]
  reference_hooks: string[]
  other_inputs: string
}

export type Handoff = {
  handoff: {
    id: string
    revision: number
    status: 'draft' | 'approved' | 'superseded'
    core_hash: string
    created_at: string
  }
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

export type Prompt = {
  stage: PromptStage
  name: string
  system_prompt: string
  user_template: string
  prompt_hash: string
  current_file: string
  current_path: string
  origin: 'bundled' | 'user'
  updated_at: string
}

export type ProjectActivity = {
  active: boolean
  state_token: string
}

export type ProviderProfile = {
  id: string
  name: string
  revision: number
  adapter: 'openai-compatible-chat' | 'openai-responses'
  base_url: string
  model: string
  capabilities_json: Record<string, boolean>
  parameters_json: Record<string, unknown>
  config_hash: string
  active: boolean
  created_at: string
}

export type ReferenceItem = {
  id: string
  kind: 'case' | 'hook'
  title: string
  body?: string
  body_preview?: string
  formats_json: string[]
  techniques_json: string[]
  active: boolean
}

export type Generation = {
  id: string
  project_id: string
  job_id: string
  handoff_id: string
  experiment_id: string
  writing_rule_id: string
  writing_rule: { name: string; revision: number; body: string; body_hash: string }
  output_index: number
  model_content: string
  current_content: string
  edit_revision: number
  review_state: 'unreviewed' | 'accepted' | 'rejected'
  executor: Executor
  controlled: boolean
  runtime_fingerprint: string
  runtime_label: string
  executor_metadata: Record<string, unknown>
  prompt_snapshot: Record<string, unknown>
  provider_snapshot: Record<string, unknown>
  generation_settings: Record<string, unknown>
  created_at: string
}

export type ExperimentDetail = {
  experiment: Experiment & {
    prompt_snapshot: Record<string, unknown>
    provider_snapshot: Record<string, unknown>
    generation_settings: Record<string, unknown>
  }
  arms: Array<{
    id: string
    ordinal: number
    status: string
    writing_rule_id: string
    writing_rule_hash: string
    results: Generation[]
  }>
}

export type ViewId = 'projects' | 'prompts' | 'library' | 'providers' | 'project'
export type ProjectStage = 'inputs' | 'prepare' | 'handoff' | 'experiments' | 'results'
