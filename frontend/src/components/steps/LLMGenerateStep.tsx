import { Loader2, Bot, Check } from 'lucide-react'
import type { StepComponentProps } from './types'

export default function LLMGenerateStep({ step, onExecute, executing }: StepComponentProps) {
  const handleSubmit = () => {
      onExecute({})
  }

  if (step.status === 'completed' && step.result) {
      if (step.result.variants) {
        return (
            <div className="mt-5 animate-in fade-in slide-in-from-top-2 duration-300">
                <p className="text-sm text-[var(--text-muted)] mt-2 flex items-center gap-2">
                    <Check className="w-4 h-4 text-[var(--success)]" />
                    已生成 {step.result.variants.length} 个优质变体
                </p>
            </div>
        )
      }
      return null
  }

  return (
    <div className="mt-6">
    <button
        onClick={handleSubmit}
        disabled={executing}
        className="btn btn-primary w-full h-14 text-lg shadow-xl shadow-[var(--primary)]/20 relative overflow-hidden group"
    >
        <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-[100%] group-hover:translate-x-[100%] transition-transform duration-1000" />
        {executing ? (
        <>
            <Loader2 className="w-5 h-5 animate-spin" />
            正在生成...
        </>
        ) : (
        <>
            <Bot className="w-5 h-5" />
            开始生成
        </>
        )}
    </button>
    </div>
  )
}
