import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Check, Clock, Loader2, X, ChevronDown } from 'lucide-react'
import type { Step } from './steps/types'
import { renderStep } from '../workflow/stepRegistry'

// Re-export type for compatibility with Pipeline.tsx
export type { Step } from './steps/types'

interface StepCardProps {
  step: Step
  isActive: boolean
  isCompleted: boolean
  onExecute: (inputs: Record<string, unknown>) => void
  executing: boolean
  isPipelineRunning?: boolean
  defaultExpanded?: boolean
}

export default function StepCard({ step, isActive, isCompleted, onExecute, executing, isPipelineRunning, defaultExpanded = false }: StepCardProps) {
  const [isManuallyExpanded, setIsManuallyExpanded] = useState(defaultExpanded)
  const isExpanded = isActive || isManuallyExpanded

  const statusIcons = {
    pending: <Clock className="w-5 h-5 text-[var(--text-muted)]" />,
    running: <Loader2 className="w-5 h-5 text-[var(--primary)] animate-spin" />,
    completed: <Check className="w-5 h-5 text-[var(--success)]" />,
    failed: <X className="w-5 h-5 text-[var(--error)]" />
  }

  const renderStepContent = () => {
    // Basic guard: don't render pending steps if not active (unless expanded manually)
    // Actually, allowing manual inspection of pending steps is fine if expanded
    if (step.status === 'pending' && !isActive && !isExpanded) return null

    const props = {
        step,
        onExecute,
        executing: executing && isActive, // Only show executing state if this step is active
        isCompleted,
        isPipelineRunning
    }

    try {
      return renderStep(step, props)
    } catch {
      return (
          <div className="p-4 rounded-lg bg-[var(--bg-card)] border border-[var(--border-subtle)] text-[var(--error)]">
              Unknown Step Type: {step.type}
          </div>
      )
    }
  }

  // Header styles based on status
  const headerClass = `
    relative flex items-center justify-between p-5 cursor-pointer select-none transition-all duration-300
    ${isActive ? 'bg-[var(--primary)]/5' : 'hover:bg-white/5'}
    ${isCompleted ? 'opacity-75 hover:opacity-100' : ''}
  `

  return (
    <div 
      className={`
        relative overflow-hidden rounded-2xl transition-all duration-500
        ${isActive 
          ? 'bg-[var(--bg-panel)] shadow-[0_0_30px_-5px_var(--primary)] ring-1 ring-[var(--primary)]/30 backdrop-blur-xl' 
          : 'bg-[var(--bg-card)] border border-[var(--border-subtle)] hover:border-[var(--border-hover)]'
        }
      `}
    >
      {/* Active Indicator Line */}
      {isActive && (
        <div className="absolute left-0 top-0 bottom-0 w-1 bg-[var(--primary)] shadow-[0_0_10px_var(--primary)] animate-pulse" />
      )}

      {/* Header */}
      <div 
        className={headerClass}
        onClick={() => setIsManuallyExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-4">
          <div className="flex items-center justify-center w-8 h-8 rounded-full bg-black/20 border border-[var(--border-subtle)]">
            {statusIcons[step.status] || statusIcons.pending}
          </div>
          <h3 className={`text-lg font-medium tracking-wide font-serif ${isActive ? 'text-[var(--primary)]' : 'text-[var(--text-main)]'}`}>
            {step.label}
          </h3>
        </div>

        <ChevronDown 
          className={`w-5 h-5 text-[var(--text-dim)] transition-transform duration-300 ${isExpanded ? 'rotate-180' : ''}`}
        />
      </div>

      {/* Content Body */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            <div className="p-5 pt-0 border-t border-[var(--border-subtle)]/50">
                {renderStepContent()}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
