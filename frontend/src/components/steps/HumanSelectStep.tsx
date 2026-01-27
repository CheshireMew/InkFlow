import { useState } from 'react'
import { Loader2, Copy, Check, Download } from 'lucide-react'
import type { StepComponentProps } from './types'
import { parseVariants } from '../../utils/textParser'

interface VariantObj {
    label: string
    content: string
}

type Variant = string | VariantObj

export default function HumanSelectStep({ step, onExecute, executing }: StepComponentProps) {
  // Support Multi-Select
  const [selectedIndices, setSelectedIndices] = useState<number[]>([])
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null)
  const [batchCopied, setBatchCopied] = useState(false)

  // Get variants from result (if completed) or config (injected by backend)
  // Type assertion to handle potential string[] vs VariantObj[] ambiguity
  const rawVariants = (step.result?.variants || step.config?.variants) as unknown as (string[] | VariantObj[] | undefined)
  
  // Parse variants: If backend sends objects, use them. If strings, try frontend parser.
  let variants: Variant[] | null = null
  if (rawVariants) {
      if (rawVariants.length > 0 && typeof rawVariants[0] === 'object') {
          variants = rawVariants as VariantObj[]
      } else {
          // Legacy string parsing
           const variantsStr = rawVariants as string[]
           const parsed = parseVariants(variantsStr)
           variants = parsed
      }
  }

  const toggleSelection = (idx: number) => {
    setSelectedIndices(prev => {
        if (prev.includes(idx)) return prev.filter(i => i !== idx)
        return [...prev, idx]
    })
  }

  const handleConfirm = () => {
      onExecute({ selected_indices: selectedIndices })
  }

  const handleCopy = async (e: React.MouseEvent, text: string, idx: number) => {
    e.stopPropagation()
    await navigator.clipboard.writeText(text)
    setCopiedIndex(idx)
    setTimeout(() => setCopiedIndex(null), 2000)
  }

  const handleBatchCopy = async () => {
      if (!variants || selectedIndices.length === 0) return
      
      const textToCopy = selectedIndices.slice().sort().map(idx => {
          const v = variants![idx]
          return typeof v === 'object' ? v.content : v
      }).join('\n\n')

      await navigator.clipboard.writeText(textToCopy)
      setBatchCopied(true)
      setTimeout(() => setBatchCopied(false), 2000)
  }

  const handleExportTxt = () => {
      if (!variants || selectedIndices.length === 0) return
      
      const textToExport = selectedIndices.slice().sort().map(idx => {
          const v = variants![idx]
          return typeof v === 'object' ? v.content : v
      }).join('\n\n')

      const blob = new Blob([textToExport], { type: 'text/plain;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `translation_export_${Date.now()}.txt`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
  }

  if (variants && variants.length > 0) {
    const hasSelection = selectedIndices.length > 0

    return (
      <div className="mt-6 space-y-4 animate-in fade-in">
        <div className="flex items-center justify-between mb-3">
            <h4 className="text-sm font-medium text-[var(--text-muted)]">
            AI 为您生成了以下方案（点击选择）：
            </h4>
            
            {/* Batch Actions */}
            <div className="flex items-center gap-2">
                {hasSelection && (
                    <>
                        <button 
                            onClick={handleBatchCopy}
                            className="text-xs flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[var(--bg-card)] border border-[var(--border-subtle)] hover:border-[var(--primary)] text-[var(--text-main)] transition-colors"
                        >
                            {batchCopied ? <Check className="w-3.5 h-3.5 text-[var(--success)]" /> : <Copy className="w-3.5 h-3.5" />}
                            {batchCopied ? "已复制" : `复制选中 (${selectedIndices.length})`}
                        </button>
                        <button 
                            onClick={handleExportTxt}
                            className="text-xs flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[var(--bg-card)] border border-[var(--border-subtle)] hover:border-[var(--primary)] text-[var(--text-main)] transition-colors"
                        >
                            <Download className="w-3.5 h-3.5" />
                            导出选中
                        </button>
                    </>
                )}
            </div>
        </div>

        <div className="space-y-3">
          {variants.map((variant: Variant, idx: number) => {
            const isSelected = selectedIndices.includes(idx)
            const label = typeof variant === 'object' ? variant.label : `方案 ${idx + 1}`
            const content = typeof variant === 'object' ? variant.content : variant
            
            return (
            <button
              key={idx}
              onClick={() => toggleSelection(idx)}
              disabled={executing || step.status === 'completed'}
              className={`w-full text-left p-4 rounded-xl border transition-all duration-300 relative group
                ${isSelected
                  ? 'bg-[var(--primary)]/10 border-[var(--primary)] ring-1 ring-[var(--primary)]' 
                  : 'bg-black/20 border-[var(--border-subtle)] hover:border-[var(--primary)]/50'
                }
              `}
            >
              <div className="flex flex-col gap-2">
                  {/* Label Header */}
                  {typeof variant === 'object' && (
                      <div className={`text-xs font-bold uppercase tracking-wider px-2 py-0.5 rounded w-fit
                          ${isSelected ? 'bg-[var(--primary)] text-black' : 'bg-[var(--bg-highlight)] text-[var(--text-muted)]'}
                      `}>
                          {label}
                      </div>
                  )}

                  {/* Content Body */}
                  <div className={`text-[var(--text-main)] leading-relaxed whitespace-pre-wrap font-serif mr-8 ${typeof variant === 'string' ? 'mt-1' : ''}`}>
                    {content}
                  </div>
              </div>
              
              {/* Checkmark Badge */}
              {isSelected && (
                 <div className="absolute top-4 right-4 text-[var(--primary)]">
                    <Check className="w-5 h-5 bg-[var(--primary)]/20 rounded-full p-1 border border-[var(--primary)]" />
                 </div>
              )}

              {/* Copy Button (Individual) */}
              <div 
                onClick={(e) => handleCopy(e, content, idx)}
                className={`absolute bottom-3 right-3 p-2 rounded-lg bg-[var(--bg-card)] border border-[var(--border-subtle)] hover:border-[var(--primary)] hover:text-[var(--primary)] text-[var(--text-muted)] transition-all
                    ${copiedIndex === idx ? 'border-[var(--success)] text-[var(--success)]' : 'opacity-0 group-hover:opacity-100'}
                `}
                title="复制内容"
              >
                 {copiedIndex === idx ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
              </div>
            </button>
          )})}
        </div>

        {/* Confirm Selection Button */}
        {step.status !== 'completed' && (
            <div className="pt-4 flex justify-end">
                <button
                    onClick={handleConfirm}
                    disabled={!hasSelection || executing}
                    className="btn btn-primary shadow-lg shadow-[var(--primary)]/20 px-8"
                >
                    {executing ? (
                        <>
                            <Loader2 className="w-4 h-4 animate-spin" />
                            处理中...
                        </>
                    ) : (
                        <>
                            确认选择 ({selectedIndices.length})
                            <Check className="w-4 h-4" />
                        </>
                    )}
                </button>
            </div>
        )}
      </div>
    )
  }

  if (step.status === 'pending') {
      return (
        <div className="mt-4 p-4 rounded-lg bg-black/5 border border-dashed border-[var(--border-subtle)] text-center text-[var(--text-muted)]">
            <div className="text-sm">等待上一步完成...</div>
        </div>
      )
  }

  return (
      <div className="mt-4 p-4 rounded-lg bg-[var(--bg-card)] border border-[var(--border-subtle)] text-center text-[var(--text-dim)]">
          <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2 text-[var(--primary)]" />
          <div className="text-sm">{step.config?.loading_label || '正在生成中...'}</div>
      </div>
  )
}
