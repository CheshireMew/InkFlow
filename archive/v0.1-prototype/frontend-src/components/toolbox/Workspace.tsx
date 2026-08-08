import { useState } from 'react'
import { LayoutGrid, Plus } from 'lucide-react'

import ToolActionCard from './ToolActionCard'
import { AVAILABLE_TOOLS } from './toolCatalog'
import type { ToolAction, ToolConfig } from './types'
import { executeAction } from '../../api/actionClient'

export default function ToolboxWorkspace() {
  const [actions, setActions] = useState<ToolAction[]>([
    { id: 1, toolId: 'input', status: 'idle', data: null },
  ])

  const addAction = (toolId: string) => {
    setActions((prev) => [...prev, { id: Date.now(), toolId, status: 'idle', data: null }])
  }

  const removeAction = (id: number) => {
    setActions((prev) => prev.filter((action) => action.id !== id))
  }

  const changeTool = (actionId: number, toolId: string) => {
    setActions((prev) => prev.map((action) => (
      action.id === actionId
        ? { ...action, toolId, data: null, status: 'idle' }
        : action
    )))
  }

  const handleRun = async (
    actionId: number,
    toolId: string,
    inputs: Record<string, unknown>,
    config: ToolConfig,
  ) => {
    setActions((prev) => prev.map((action) => action.id === actionId ? { ...action, status: 'running' } : action))

    const result = await executeAction(
      AVAILABLE_TOOLS.find((tool) => tool.id === toolId)?.type || 'text_input',
      inputs,
      config,
    )

    setActions((prev) => prev.map((action) => (
      action.id === actionId
        ? {
            ...action,
            status: result.success ? 'completed' : 'failed',
            data: result.data || result.error,
          }
        : action
    )))
  }

  return (
    <div className="max-w-3xl mx-auto p-4 space-y-8 pb-32">
      <div className="flex items-center gap-3 mb-8">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[var(--primary)] to-[var(--accent)] flex items-center justify-center text-white shadow-lg shadow-[var(--primary)]/20">
          <LayoutGrid className="w-5 h-5" />
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Toolbox Playground</h1>
          <p className="text-[var(--text-dim)]">Dynamic Action Composition</p>
        </div>
      </div>

      <div className="space-y-6">
        {actions.map((action, index) => (
          <ToolActionCard
            key={action.id}
            action={action}
            index={index}
            showConnector={index < actions.length - 1}
            previousData={index > 0 ? actions[index - 1]?.data : null}
            onRemove={removeAction}
            onChangeTool={changeTool}
            onRun={handleRun}
          />
        ))}
      </div>

      <div className="flex justify-center pt-4">
        <div className="flex gap-2 bg-[var(--bg-panel)] p-2 rounded-xl border border-[var(--border-subtle)] shadow-lg">
          {AVAILABLE_TOOLS.map((tool) => (
            <button
              key={tool.id}
              onClick={() => addAction(tool.id)}
              className="flex items-center gap-2 px-4 py-2 rounded-lg hover:bg-[var(--bg-hover)] text-sm font-medium transition-colors"
            >
              <Plus className="w-4 h-4" />
              {tool.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
