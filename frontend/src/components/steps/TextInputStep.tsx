import { useState, useEffect } from 'react'
import { Loader2, ChevronRight, ChevronDown } from 'lucide-react'
import type { StepComponentProps } from './types'

export default function TextInputStep({ step, onExecute, executing, isPipelineRunning }: StepComponentProps) {
  const [formData, setFormData] = useState<Record<string, string>>({})
  
  // Legacy single input support
  const userInput = formData['user_input'] || ''

  // Initialize default values when step becomes active or has results
  const getCacheKey = () => `inkflow_input_cache_${step.config?.id || step.index}`

  // Initialize default values or restore from cache
  useEffect(() => {
    const initialData: Record<string, string> = {}
    let hasData = false

    if (step.config?.fields) {
      // 1. Restore from Backend Result
      step.config.fields.forEach(field => {
        if (step.result?.[field.id]) {
            initialData[field.id] = step.result[field.id]
            hasData = true
        }
      })

      // 2. Restore from Draft Cache (if no backend result)
      if (!hasData && step.status !== 'completed') {
        try {
            const cached = localStorage.getItem(getCacheKey())
            if (cached) {
                Object.assign(initialData, JSON.parse(cached))
                hasData = true
            }
        } catch (e) {
            console.warn('Failed to restore input cache', e)
        }
      }

      // 3. Apply Global Preferences & Defaults (for missing fields)
      step.config.fields.forEach(field => {
        if (!initialData[field.id]) {
            // Global Preference (Sticky Settings)
            if (field.type === 'select' || field.type === 'multiselect') {
                const pref = localStorage.getItem(`inkflow_pref_${field.id}`)
                if (pref) {
                    initialData[field.id] = pref
                    hasData = true
                }
            }
            
            // Config Default
            if (!initialData[field.id] && field.default) {
                initialData[field.id] = field.default
                hasData = true
            }
        }
      })

    } else if (step.type === 'text_input' && step.result?.text) {
        // Legacy mode restore
        initialData['user_input'] = step.result.text
        hasData = true
    }
      
    if (hasData) {
      setFormData(prev => ({ ...prev, ...initialData }))
    }
  }, [step.config, step.result]) // Dependencies

  const handleInputChange = (id: string, value: string) => {
    const newData = { ...formData, [id]: value }
    setFormData(newData)
    
    // Cache to localStorage (Draft)
    if (step.status !== 'completed') {
        localStorage.setItem(getCacheKey(), JSON.stringify(newData))
        
        // Cache Global Preferences (Sticky Settings)
        const field = step.config?.fields?.find(f => f.id === id)
        if (field && (field.type === 'select' || field.type === 'multiselect')) {
            localStorage.setItem(`inkflow_pref_${id}`, value)
        }
    }
  }

  const handleSubmit = () => {
    if (step.config?.fields) {
        // Multi-field mode
        onExecute(formData)
    } else {
        // Legacy mode
        onExecute({ user_input: userInput })
    }
  }

  const getSubmitLabel = () => {
    if (step.status === 'completed') {
        return '更新并重新生成'
    }
    return step.config?.submit_label || '继续下一步'
  }

  // Multi-field Configuration
  if (step.config?.fields) {
    return (
        <div className="mt-6 space-y-5 animate-in fade-in slide-in-from-top-2">
            {/* 1. Main Text Input (Textarea) - Always Full Width */}
            {step.config.fields.filter(f => f.type === 'textarea').map(field => (
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

            {/* 2. Options and Action Row (Selects & Inputs) */}
            <div className="flex flex-col lg:flex-row gap-4 items-end">
                {/* Render non-textarea/non-multiselect fields (Dropdowns/Inputs) */}
                {step.config.fields.filter(f => f.type !== 'textarea' && f.type !== 'multiselect').map(field => (
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
                                    {field.options?.map(opt => (
                                        <option key={opt} value={opt} className="bg-[var(--bg-card)] text-[var(--text-main)]">
                                            {opt}
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
                
                {/* Submit Button - Aligned with inputs */}
                <div className="w-full lg:w-auto flex-shrink-0">
                    <button
                        onClick={handleSubmit}
                        disabled={executing || isPipelineRunning}
                        className="btn btn-primary w-full lg:w-auto h-[50px] px-8 shadow-lg shadow-[var(--primary)]/20 flex items-center justify-center gap-2"
                        style={{ marginTop: '0' }}
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

            {/* 3. MultiSelect Fields - Full Width Row */}
            {step.config.fields.filter(f => f.type === 'multiselect').map(field => (
                <div key={field.id} className="space-y-2">
                     <label className="text-sm font-medium text-[var(--text-muted)] ml-1">
                        {field.label} {field.required && <span className="text-[var(--error)]">*</span>}
                    </label>
                    <div className="flex flex-wrap gap-2 py-1">
                        {field.options?.map(opt => {
                            const currentVal = formData[field.id] ? JSON.parse(formData[field.id]) : []
                            const isSelected = currentVal.includes(opt)
                            return (
                                <button
                                    key={opt}
                                    onClick={() => {
                                        const newVal = isSelected
                                            ? currentVal.filter((v: string) => v !== opt)
                                            : [...currentVal, opt]
                                        handleInputChange(field.id, JSON.stringify(newVal))
                                    }}
                                    className={`px-4 py-2 rounded-lg text-sm transition-all border ${
                                        isSelected 
                                        ? 'bg-[var(--primary)] text-white border-[var(--primary)] shadow-md shadow-[var(--primary)]/20' 
                                        : 'bg-black/20 text-[var(--text-muted)] border-[var(--border-subtle)] hover:border-[var(--primary)]/50 hover:bg-black/30'
                                    }`}
                                >
                                    {opt}
                                </button>
                            )
                        })}
                    </div>
                </div>
            ))}

        </div>
    )
  }

  // Legacy Single Textarea
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
