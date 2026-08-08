import type { Step } from '../steps/types'
import type { ToolAction, ToolConfig } from './types'

export function createToolStep(action: ToolAction, type: Step['type'], label: string, config: ToolConfig): Step {
  return {
    id: `action-${action.id}`,
    type,
    label,
    run_mode: 'server',
    stage: 'input',
    auto_run: false,
    status: action.status === 'idle' ? 'pending' : action.status,
    config,
    result: isStepResult(action.data) ? action.data : undefined,
    index: 0,
  }
}

export function buildToolInputs(
  toolType: Step['type'],
  previousData: unknown,
  manualInput: string,
  inputData: Record<string, unknown>,
) {
  const finalInputs: Record<string, unknown> = { ...inputData }

  if (toolType === 'text_input') {
    return finalInputs
  }

  if (previousData !== null && previousData !== undefined) {
    finalInputs.user_input = extractText(previousData)
    finalInputs.prev_output = previousData
    return finalInputs
  }

  if (manualInput.trim()) {
    finalInputs.user_input = manualInput.trim()
  }

  return finalInputs
}

export function extractText(value: unknown): string {
  if (typeof value === 'string') {
    return value
  }

  if (Array.isArray(value)) {
    return JSON.stringify(value)
  }

  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>
    const direct = record.text ?? record.content ?? record.result
    if (typeof direct === 'string') {
      return direct
    }
    return JSON.stringify(record)
  }

  return ''
}

export function readConfigString(config: ToolConfig, key: string): string {
  const value = config[key]
  return typeof value === 'string' ? value : ''
}

function isStepResult(value: unknown): value is Step['result'] {
  return Boolean(value) && typeof value === 'object'
}
