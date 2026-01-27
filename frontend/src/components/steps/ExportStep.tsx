import { useState, useEffect } from 'react'
import { Check, Copy } from 'lucide-react'
import type { StepComponentProps } from './types'

export default function ExportStep({ step, onExecute, executing }: StepComponentProps) {
  const [copied, setCopied] = useState(false)

  const { status } = step
  
  // Auto-execute if pending (to fetch/prepare content)
  useEffect(() => {
    if (status === 'pending' && !executing) {
        onExecute({})
    }
  }, [status])

  const handleCopy = async () => {
    const content = step.result?.content || ''
    await navigator.clipboard.writeText(content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // Only render if we have content
  const content = step.result?.content
  if (!content) return null

  return (
    <div className="mt-6 flex gap-3 animate-in fade-in slide-in-from-top-2">
      <button
        onClick={handleCopy}
        className="flex-1 btn bg-[var(--bg-card)] border border-[var(--border-subtle)] hover:border-[var(--primary)] text-[var(--text-main)] transition-all group"
      >
        {copied ? (
          <>
            <Check className="w-4 h-4 text-[var(--success)]" />
            已复制
          </>
        ) : (
          <>
            <Copy className="w-4 h-4 group-hover:scale-110 transition-transform" />
            复制到剪贴板
          </>
        )}
      </button>
    </div>
  )
}
