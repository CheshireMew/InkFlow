import { Trash2 } from 'lucide-react'

import ToolWrapper from './ToolWrapper'
import { AVAILABLE_TOOLS, getToolDefinition } from './toolCatalog'
import type { ToolAction, ToolConfig } from './types'

interface ToolActionCardProps {
  action: ToolAction
  index: number
  showConnector: boolean
  previousData: unknown
  onRemove: (id: number) => void
  onChangeTool: (actionId: number, toolId: string) => void
  onRun: (actionId: number, toolId: string, inputs: Record<string, unknown>, config: ToolConfig) => void
}

export default function ToolActionCard({
  action,
  index,
  showConnector,
  previousData,
  onRemove,
  onChangeTool,
  onRun,
}: ToolActionCardProps) {
  const tool = getToolDefinition(action.toolId)

  return (
    <div className="relative pl-8 group">
      {showConnector && (
        <div className="absolute left-[15px] top-10 bottom-[-24px] w-[2px] bg-[var(--border-subtle)] group-hover:bg-[var(--primary)] transition-colors" />
      )}

      <div className={`absolute left-0 top-6 w-8 h-8 rounded-full border-4 border-[var(--bg-main)] flex items-center justify-center transition-all ${
        action.status === 'completed' ? 'bg-[var(--accent)] text-white' : 'bg-[var(--bg-card)] text-[var(--text-muted)]'
      }`}>
        <span className="text-xs font-bold">{index + 1}</span>
      </div>

      <div className="relative bg-[var(--bg-panel)] border border-[var(--border-base)] rounded-2xl p-6 shadow-sm hover:shadow-md transition-all hover:border-[var(--border-hover)]">
        <div className="flex justify-between items-start mb-4">
          <div className="flex items-center gap-2">
            <select
              value={action.toolId}
              onChange={(event) => onChangeTool(action.id, event.target.value)}
              className="bg-transparent font-semibold text-[var(--text-main)] focus:outline-none cursor-pointer hover:text-[var(--primary)] transition-colors"
            >
              {AVAILABLE_TOOLS.map((candidate) => (
                <option key={candidate.id} value={candidate.id} className="bg-[var(--bg-card)]">
                  {candidate.label}
                </option>
              ))}
            </select>
          </div>
          <button onClick={() => onRemove(action.id)} className="text-[var(--text-dim)] hover:text-[var(--error)] transition-colors p-2 hover:bg-black/10 rounded-lg">
            <Trash2 className="w-4 h-4" />
          </button>
        </div>

        <ToolWrapper
          tool={tool}
          action={action}
          previousData={previousData}
          onRun={(toolId, inputs, config) => onRun(action.id, toolId, inputs, config)}
        />
      </div>
    </div>
  )
}
