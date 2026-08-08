export type ToolType = 'text_input' | 'llm_generate'
export type ActionStatus = 'idle' | 'running' | 'completed' | 'failed'
export type ToolConfig = Record<string, unknown>

export interface ToolDefinition {
  id: string
  type: ToolType
  label: string
  config: ToolConfig
}

export interface ToolAction {
  id: number
  toolId: string
  status: ActionStatus
  data: unknown
}
