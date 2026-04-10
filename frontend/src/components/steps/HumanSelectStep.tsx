import { useMemo, useState } from 'react'
import { Check, Copy, Download, Loader2 } from 'lucide-react'
import type { StepComponentProps, VariantOption } from './types'
import { parseVariants } from '../../utils/textParser'

export default function HumanSelectStep({ step, onExecute, executing }: StepComponentProps) {
  const loadingLabel = typeof step.config?.loading_label === 'string' ? step.config.loading_label : '正在生成中...'
  const variants = normalizeVariants(step.result?.variants || step.config?.variants)

  if (variants.length > 0) {
    const reviewKey = JSON.stringify(variants) + String(step.result?.content || '')
    return (
      <ReviewEditor
        key={reviewKey}
        step={step}
        variants={variants}
        onExecute={onExecute}
        executing={executing}
      />
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
      <div className="text-sm">{loadingLabel}</div>
    </div>
  )
}

interface ReviewEditorProps {
  step: StepComponentProps['step']
  variants: VariantOption[]
  onExecute: StepComponentProps['onExecute']
  executing: boolean
}

function ReviewEditor({ step, variants, onExecute, executing }: ReviewEditorProps) {
  const initialSelectedIndices = useMemo(
    () => normalizeSelectedIndices(step.result?.selected_indices, step.result?.selected, variants),
    [step.result?.selected, step.result?.selected_indices, variants],
  )
  const initialGeneratedContent = buildSelectedContent(variants, initialSelectedIndices)
  const initialEditedContent = typeof step.result?.content === 'string' ? step.result.content : initialGeneratedContent

  const [selectedIndices, setSelectedIndices] = useState<number[]>(initialSelectedIndices)
  const [editedContent, setEditedContent] = useState(initialEditedContent)
  const [copied, setCopied] = useState(false)
  const [copiedVariantIndex, setCopiedVariantIndex] = useState<number | null>(null)

  const hasSelection = selectedIndices.length > 0
  const finalizedContent = editedContent.trim()

  const handleToggleSelection = (index: number) => {
    const nextIndices = selectedIndices.includes(index)
      ? selectedIndices.filter((current) => current !== index)
      : [...selectedIndices, index].sort((left, right) => left - right)

    const previousGenerated = buildSelectedContent(variants, selectedIndices)
    const nextGenerated = buildSelectedContent(variants, nextIndices)

    setSelectedIndices(nextIndices)
    if (!editedContent.trim() || editedContent === previousGenerated) {
      setEditedContent(nextGenerated)
    }
  }

  const handleConfirm = () => {
    onExecute({
      selected_indices: selectedIndices,
      edited_content: finalizedContent,
    })
  }

  const handleCopyVariant = async (event: React.MouseEvent, content: string, index: number) => {
    event.stopPropagation()
    await navigator.clipboard.writeText(content)
    setCopiedVariantIndex(index)
    setTimeout(() => setCopiedVariantIndex(null), 2000)
  }

  const handleCopyFinal = async () => {
    if (!finalizedContent) {
      return
    }
    await navigator.clipboard.writeText(finalizedContent)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleExportFinal = () => {
    if (!finalizedContent) {
      return
    }

    const blob = new Blob([finalizedContent], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `inkflow_export_${Date.now()}.txt`
    document.body.appendChild(anchor)
    anchor.click()
    document.body.removeChild(anchor)
    URL.revokeObjectURL(url)
  }

  return (
    <div className="mt-6 space-y-5 animate-in fade-in">
      <div className="space-y-3">
        {variants.map((variant, index) => {
          const isSelected = selectedIndices.includes(index)

          return (
            <button
              key={`${variant.label || 'variant'}-${index}`}
              onClick={() => handleToggleSelection(index)}
              disabled={executing}
              className={`w-full text-left p-4 rounded-xl border transition-all duration-300 relative group ${
                isSelected
                  ? 'bg-[var(--primary)]/10 border-[var(--primary)] ring-1 ring-[var(--primary)]'
                  : 'bg-black/20 border-[var(--border-subtle)] hover:border-[var(--primary)]/50'
              }`}
            >
              <div className="flex flex-col gap-2">
                {variant.label && (
                  <div className={`text-xs font-bold uppercase tracking-wider px-2 py-0.5 rounded w-fit ${
                    isSelected ? 'bg-[var(--primary)] text-black' : 'bg-[var(--bg-highlight)] text-[var(--text-muted)]'
                  }`}>
                    {variant.label}
                  </div>
                )}

                <div className="text-[var(--text-main)] leading-relaxed whitespace-pre-wrap font-serif mr-8">
                  {variant.content}
                </div>
              </div>

              {isSelected && (
                <div className="absolute top-4 right-4 text-[var(--primary)]">
                  <Check className="w-5 h-5 bg-[var(--primary)]/20 rounded-full p-1 border border-[var(--primary)]" />
                </div>
              )}

              <div
                onClick={(event) => handleCopyVariant(event, variant.content, index)}
                className={`absolute bottom-3 right-3 p-2 rounded-lg bg-[var(--bg-card)] border border-[var(--border-subtle)] hover:border-[var(--primary)] hover:text-[var(--primary)] text-[var(--text-muted)] transition-all ${
                  copiedVariantIndex === index ? 'border-[var(--success)] text-[var(--success)]' : 'opacity-0 group-hover:opacity-100'
                }`}
                title="复制内容"
              >
                {copiedVariantIndex === index ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
              </div>
            </button>
          )
        })}
      </div>

      <div className="space-y-3">
        <textarea
          value={editedContent}
          onChange={(event) => setEditedContent(event.target.value)}
          placeholder={hasSelection ? '可以直接修改最终内容' : '先选择一个结果'}
          disabled={!hasSelection || executing}
          className="w-full min-h-40 bg-black/20 border border-[var(--border-subtle)] rounded-xl p-4 text-[var(--text-main)] placeholder-[var(--text-dim)] focus:outline-none focus:border-[var(--primary)] focus:ring-1 focus:ring-[var(--primary)] transition-all resize-y"
        />

        <div className="flex flex-wrap gap-2 justify-end">
          <button
            onClick={handleCopyFinal}
            disabled={!finalizedContent}
            className="text-xs flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[var(--bg-card)] border border-[var(--border-subtle)] hover:border-[var(--primary)] text-[var(--text-main)] transition-colors disabled:opacity-40"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-[var(--success)]" /> : <Copy className="w-3.5 h-3.5" />}
            {copied ? '已复制' : '复制最终内容'}
          </button>
          <button
            onClick={handleExportFinal}
            disabled={!finalizedContent}
            className="text-xs flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[var(--bg-card)] border border-[var(--border-subtle)] hover:border-[var(--primary)] text-[var(--text-main)] transition-colors disabled:opacity-40"
          >
            <Download className="w-3.5 h-3.5" />
            导出最终内容
          </button>
          <button
            onClick={handleConfirm}
            disabled={!hasSelection || !finalizedContent || executing}
            className="btn btn-primary shadow-lg shadow-[var(--primary)]/20 px-8"
          >
            {executing ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                保存中...
              </>
            ) : (
              <>
                保存结果
                <Check className="w-4 h-4" />
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}

function normalizeVariants(rawVariants: unknown): VariantOption[] {
  if (!Array.isArray(rawVariants) || rawVariants.length === 0) {
    return []
  }

  if (typeof rawVariants[0] === 'object' && rawVariants[0] !== null) {
    return rawVariants.map((variant) => {
      const value = variant as VariantOption
      return {
        label: value.label,
        content: value.content,
      }
    })
  }

  return parseVariants(rawVariants as string[]).map((variant) => ({ content: variant }))
}

function normalizeSelectedIndices(
  rawIndices: unknown,
  selected: unknown,
  variants: VariantOption[],
) {
  if (Array.isArray(rawIndices)) {
    return rawIndices
      .map((value) => Number(value))
      .filter((value) => Number.isInteger(value) && value >= 0 && value < variants.length)
  }

  if (!Array.isArray(selected)) {
    return []
  }

  return selected.flatMap((value) => {
    const content = typeof value === 'string' ? value : (value as VariantOption).content
    const index = variants.findIndex((variant) => variant.content === content)
    return index >= 0 ? [index] : []
  })
}

function buildSelectedContent(variants: VariantOption[], selectedIndices: number[]) {
  return selectedIndices.map((index) => variants[index]?.content || '').filter(Boolean).join('\n\n')
}
