import { useState } from 'react'
import { ChevronDown, ChevronRight, Loader2 } from 'lucide-react'
import type { Step, StepComponentProps } from './types'

export default function TextInputStep({ step, onExecute, executing, isPipelineRunning }: StepComponentProps) {
  const [formData, setFormData] = useState<Record<string, string>>(() => buildInitialFormData(step))
  const userInput = formData.user_input || ''

  const handleInputChange = (id: string, value: string) => {
    const newData = { ...formData, [id]: value }
    setFormData(newData)

    if (step.status !== 'completed') {
      localStorage.setItem(getCacheKey(step.id), JSON.stringify(newData))

      const field = step.config?.fields?.find((candidate) => candidate.id === id)
      if (field && (field.type === 'select' || field.type === 'multiselect')) {
        localStorage.setItem(`inkflow_pref_${id}`, value)
      }
    }
  }

  const handleSubmit = () => {
    if (step.config?.fields) {
      onExecute(formData)
      return
    }

    onExecute({ user_input: userInput })
  }

  const getSubmitLabel = () => {
    if (step.status === 'completed') {
      return '更新并重新生成'
    }
    return step.config?.submit_label || '继续下一步'
  }

  if (step.config?.fields) {
    return (
      <div className="mt-6 space-y-5 animate-in fade-in slide-in-from-top-2">
        {step.config.fields.filter((field) => field.type === 'textarea').map((field) => (
          <div key={field.id} className="space-y-2">
            <label className="text-sm font-medium text-[var(--text-muted)] ml-1">
              {field.label} {field.required && <span className="text-[var(--error)]">*</span>}
            </label>
            <textarea
              value={formData[field.id] || ''}
              onChange={(e) => handleInputChange(field.id, e.target.value)}
              placeholder={field.placeholder}
              className="w-full h-32 bg-black/20 border border-[var(--border-subtle)] rounded-xl p-4 text-[var(--text-main)] placeholder-[var(--text-dim)] focus:outline-none focus:border-[var(--primary)] focus:ring-1 focus:ring-[var(--primary)] transition-all resize-none"
            />
          </div>
        ))}

        <div className="flex flex-col lg:flex-row gap-4 items-end">
          {step.config.fields.filter((field) => field.type !== 'textarea' && field.type !== 'multiselect').map((field) => (
            <div key={field.id} className="space-y-2 flex-1 w-full lg:w-auto min-w-[200px]">
              <label className="text-sm font-medium text-[var(--text-muted)] ml-1">
                {field.label} {field.required && <span className="text-[var(--error)]">*</span>}
              </label>

              {field.type === 'select' ? (
                <div className="relative">
                  <select
                    value={formData[field.id] || ''}
                    onChange={(e) => handleInputChange(field.id, e.target.value)}
                    className="w-full appearance-none bg-black/20 border border-[var(--border-subtle)] rounded-xl px-4 py-3 text-[var(--text-main)] focus:outline-none focus:border-[var(--primary)] transition-all cursor-pointer"
                  >
                    <option value="" disabled>请选择...</option>
                    {field.options?.map((option) => (
                      <option key={option} value={option} className="bg-[var(--bg-card)] text-[var(--text-main)]">
                        {option}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-4 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-dim)] pointer-events-none" />
                </div>
              ) : (
                <input
                  type="text"
                  value={formData[field.id] || ''}
                  onChange={(e) => handleInputChange(field.id, e.target.value)}
                  placeholder={field.placeholder}
                  className="w-full bg-black/20 border border-[var(--border-subtle)] rounded-xl px-4 py-3 text-[var(--text-main)] placeholder-[var(--text-dim)] focus:outline-none focus:border-[var(--primary)] transition-all"
                />
              )}
            </div>
          ))}

          <div className="w-full lg:w-auto flex-shrink-0">
            <button
              onClick={handleSubmit}
              disabled={executing || isPipelineRunning}
              className="btn btn-primary w-full lg:w-auto h-[50px] px-8 shadow-lg shadow-[var(--primary)]/20 flex items-center justify-center gap-2"
            >
              {executing || isPipelineRunning ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  {step.config?.loading_label || '处理中...'}
                </>
              ) : (
                <>
                  {getSubmitLabel()}
                  <ChevronRight className="w-4 h-4" />
                </>
              )}
            </button>
          </div>
        </div>

        {step.config.fields.filter((field) => field.type === 'multiselect').map((field) => (
          <div key={field.id} className="space-y-2">
            <label className="text-sm font-medium text-[var(--text-muted)] ml-1">
              {field.label} {field.required && <span className="text-[var(--error)]">*</span>}
            </label>
            <div className="flex flex-wrap gap-2 py-1">
              {field.options?.map((option) => {
                const currentValues = parseMultiSelectValue(formData[field.id])
                const isSelected = currentValues.includes(option)

                return (
                  <button
                    key={option}
                    onClick={() => {
                      const nextValues = isSelected
                        ? currentValues.filter((value) => value !== option)
                        : [...currentValues, option]
                      handleInputChange(field.id, JSON.stringify(nextValues))
                    }}
                    className={`px-4 py-2 rounded-lg text-sm transition-all border ${
                      isSelected
                        ? 'bg-[var(--primary)] text-white border-[var(--primary)] shadow-md shadow-[var(--primary)]/20'
                        : 'bg-black/20 text-[var(--text-muted)] border-[var(--border-subtle)] hover:border-[var(--primary)]/50 hover:bg-black/30'
                    }`}
                  >
                    {option}
                  </button>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="mt-6 space-y-4 animate-in fade-in slide-in-from-top-2">
      <div className="relative">
        <textarea
          value={userInput}
          onChange={(e) => handleInputChange('user_input', e.target.value)}
          placeholder="在这输入你的核心想法..."
          className="w-full h-32 bg-black/20 border border-[var(--border-subtle)] rounded-xl p-4 text-[var(--text-main)] placeholder-[var(--text-dim)] focus:outline-none focus:border-[var(--primary)] focus:ring-1 focus:ring-[var(--primary)] transition-all resize-none"
        />
        <div className="absolute bottom-3 right-3 text-xs text-[var(--text-dim)]">
          {userInput.length} chars
        </div>
      </div>
      <button
        onClick={handleSubmit}
        disabled={!userInput.trim() || executing || isPipelineRunning}
        className="btn btn-primary w-full shadow-lg shadow-[var(--primary)]/20"
      >
        {executing || isPipelineRunning ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            {step.config?.loading_label || '处理中...'}
          </>
        ) : (
          <>
            {getSubmitLabel()}
            <ChevronRight className="w-4 h-4" />
          </>
        )}
      </button>
    </div>
  )
}

function buildInitialFormData(step: Step): Record<string, string> {
  const initialData: Record<string, string> = {}

  if (step.config?.fields) {
    for (const field of step.config.fields) {
      const resultValue = step.result?.[field.id]
      if (typeof resultValue === 'string' && resultValue) {
        initialData[field.id] = resultValue
      }
    }

    if (Object.keys(initialData).length === 0 && step.status !== 'completed') {
      const cached = restoreCachedDraft(step.id)
      Object.assign(initialData, cached)
    }

    for (const field of step.config.fields) {
      if (initialData[field.id]) {
        continue
      }

      if (field.type === 'select' || field.type === 'multiselect') {
        const preference = localStorage.getItem(`inkflow_pref_${field.id}`)
        if (preference) {
          initialData[field.id] = preference
          continue
        }
      }

      if (field.default) {
        initialData[field.id] = field.default
      }
    }

    return initialData
  }

  if (typeof step.result?.text === 'string' && step.result.text) {
    initialData.user_input = step.result.text
  }

  return initialData
}

function restoreCachedDraft(stepId: string): Record<string, string> {
  try {
    const cached = localStorage.getItem(getCacheKey(stepId))
    return cached ? JSON.parse(cached) as Record<string, string> : {}
  } catch (error) {
    console.warn('Failed to restore input cache', error)
    return {}
  }
}

function parseMultiSelectValue(rawValue?: string): string[] {
  if (!rawValue) {
    return []
  }

  try {
    const parsed = JSON.parse(rawValue)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function getCacheKey(stepId: string) {
  return `inkflow_input_cache_${stepId}`
}
