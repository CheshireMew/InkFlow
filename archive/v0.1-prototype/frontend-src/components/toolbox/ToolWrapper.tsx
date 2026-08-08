import { useState } from 'react'
import { Play, Settings2 } from 'lucide-react'

import TextInputStep from '../steps/TextInputStep'
import type { ToolAction, ToolConfig, ToolDefinition } from './types'
import { buildToolInputs, createToolStep, readConfigString } from './toolboxUtils'

interface ToolWrapperProps {
  tool: ToolDefinition
  action: ToolAction
  previousData: unknown
  onRun: (toolId: string, inputs: Record<string, unknown>, config: ToolConfig) => void
}

export default function ToolWrapper({ tool, action, previousData, onRun }: ToolWrapperProps) {
  const [config, setConfig] = useState<ToolConfig>(tool.config)
  const [showConfig, setShowConfig] = useState(false)
  const [manualInput, setManualInput] = useState('')

  const mockStep = createToolStep(action, tool.type, tool.label, config)

  const handleExecute = (inputData: Record<string, unknown>) => {
    onRun(
      tool.id,
      buildToolInputs(tool.type, previousData, manualInput, inputData),
      { ...tool.config, ...config },
    )
  }

  if (tool.type === 'text_input') {
    return (
      <TextInputStep
        step={mockStep}
        onExecute={handleExecute}
        executing={action.status === 'running'}
        isPipelineRunning={false}
      />
    )
  }

  const hasInput = previousData !== null && previousData !== undefined

  return (
    <div className="space-y-4 border border-[var(--border-subtle)] p-4 rounded-xl bg-black/20 animate-in fade-in transition-all">
      <div className="flex justify-between items-start">
        <div>
          <h3 className="font-semibold text-[var(--accent)] flex items-center gap-2">
            {tool.label}
          </h3>
          <div className="text-xs text-[var(--text-dim)] mt-1">
            {hasInput ? 'Linked to previous step' : 'Manual Input Mode'}
          </div>
        </div>
        <button
          onClick={() => setShowConfig(!showConfig)}
          className={`p-2 rounded-lg transition-colors ${showConfig ? 'bg-[var(--primary)]/20 text-[var(--primary)]' : 'hover:bg-black/20 text-[var(--text-dim)]'}`}
        >
          <Settings2 className="w-4 h-4" />
        </button>
      </div>

      {showConfig && (
        <div className="p-4 bg-[var(--bg-card)] rounded-lg border border-[var(--border-subtle)] space-y-4 animate-in slide-in-from-top-2">
          <div className="space-y-2">
            <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">Prompt Template</label>
            <textarea
              value={readConfigString(config, 'prompt_template') || readConfigString(tool.config, 'prompt_template')}
              onChange={(event) => setConfig({ ...config, prompt_template: event.target.value })}
              className="w-full h-32 bg-black/30 border border-[var(--border-subtle)] rounded-lg p-3 text-sm font-mono focus:border-[var(--primary)] focus:outline-none"
              placeholder="{{ user_input }} will be replaced..."
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-xs font-medium text-[var(--text-muted)]">Model</label>
              <select
                value={readConfigString(config, 'model') || readConfigString(tool.config, 'model') || 'deepseek-chat'}
                onChange={(event) => setConfig({ ...config, model: event.target.value })}
                className="w-full bg-black/30 border border-[var(--border-subtle)] rounded-lg p-2 text-sm focus:border-[var(--primary)] focus:outline-none"
              >
                <option value="deepseek-chat">DeepSeek V3</option>
                <option value="deepseek-reasoner">DeepSeek R1</option>
                <option value="gpt-4o">GPT-4o</option>
              </select>
            </div>
          </div>
        </div>
      )}

      {!hasInput && (
        <div className="space-y-2">
          <label className="text-xs font-medium text-[var(--text-dim)] ml-1">Input Content</label>
          <textarea
            value={manualInput}
            onChange={(event) => setManualInput(event.target.value)}
            placeholder="Since there is no previous step, please type content here..."
            className="w-full h-24 bg-black/20 border border-[var(--border-subtle)] rounded-xl p-3 text-sm focus:border-[var(--primary)] focus:outline-none transition-all"
          />
        </div>
      )}

      <button
        onClick={() => handleExecute({})}
        disabled={action.status === 'running' || (!hasInput && !manualInput.trim())}
        className="btn btn-primary w-full flex items-center justify-center gap-2 py-3 shadow-lg shadow-[var(--primary)]/10"
      >
        {action.status === 'running' ? (
          <>Processing...</>
        ) : (
          <>
            <Play className="w-4 h-4 fill-current" />
            Run Generator
          </>
        )}
      </button>

      {Boolean(action.data) && (
        <div className="mt-4 animate-in zoom-in-95 duration-300">
          <div className="bg-[var(--bg-card)] border border-[var(--border-subtle)] rounded-xl overflow-hidden shadow-inner">
            <div className="bg-black/20 px-4 py-2 text-xs font-medium text-[var(--text-dim)] border-b border-[var(--border-subtle)] flex justify-between">
              <span>OUTPUT</span>
              <span className={typeof action.data === 'string' && action.data.includes('Error') ? 'text-red-400' : 'text-green-400'}>
                {typeof action.data === 'string' && action.data.includes('Error') ? 'FAILED' : 'SUCCESS'}
              </span>
            </div>
            <div className="p-4 text-sm whitespace-pre-wrap font-mono leading-relaxed max-h-96 overflow-y-auto custom-scrollbar">
              {typeof action.data === 'string' ? action.data : JSON.stringify(action.data, null, 2)}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
