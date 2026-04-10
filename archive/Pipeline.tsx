import { useState, useEffect } from 'react'
import { Loader2, AlertCircle } from 'lucide-react'
import StepCard from './StepCard.tsx'

interface Step {
  index: number
  type: string
  label: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  result: any
}

interface PipelineState {
  id: string
  status: string
  current_step: number
  steps: Step[]
}

interface PipelineProps {
  pipelineId: string
  onComplete: () => void
}

export default function Pipeline({ pipelineId, onComplete }: PipelineProps) {
  const [pipeline, setPipeline] = useState<PipelineState | null>(null)
  const [loading, setLoading] = useState(true)
  const [executing, setExecuting] = useState(false)

  useEffect(() => {
    fetchPipeline()
  }, [pipelineId])

  const fetchPipeline = async () => {
    try {
      const res = await fetch(`/api/pipelines/${pipelineId}`)
      const data = await res.json()
      setPipeline(data)
    } catch (err) {
      console.error('Failed to fetch pipeline:', err)
    } finally {
      setLoading(false)
    }
  }

  // Auto-execute LLM steps
  useEffect(() => {
    if (!pipeline || executing || loading) return
    
    const currentStep = pipeline.steps[pipeline.current_step]
    if (currentStep && currentStep.type === 'llm_generate' && currentStep.status === 'pending') {
      console.log('Auto-executing LLM step:', currentStep.label)
      executeStep(pipeline.current_step, {})
    }
  }, [pipeline, executing, loading])

  const executeStep = async (stepIndex: number, inputs: Record<string, any>) => {
    setExecuting(true)
    try {
      const res = await fetch('/api/pipelines/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pipeline_id: pipelineId,
          step_index: stepIndex,
          inputs
        })
      })
      const data = await res.json()
      
      if (!data.success) {
        console.error('Execution returned failure:', data)
      }
    } catch (err) {
      console.error('Step execution failed:', err)
    } finally {
      // Always refresh to get latest status (failed/completed)
      await fetchPipeline()
      setExecuting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32">
        <Loader2 className="w-8 h-8 text-[var(--primary)] animate-spin" />
      </div>
    )
  }

  if (!pipeline) {
    return (
      <div className="text-center py-20 opacity-75">
        <div className="text-6xl mb-4 grayscale">❌</div>
        <h2 className="text-xl text-[var(--text-muted)] mb-6">流水线加载失败</h2>
        <p className="text-[var(--text-dim)] mb-8 max-w-md mx-auto">
            任务可能已过期或服务已重启。请重新创建一个任务。
        </p>
        <button 
            onClick={() => window.location.href = '/'}
            className="btn btn-secondary"
        >
            返回首页创建新任务
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Enhanced Progress indicator - HIDDEN as per user request for cleaner UI
      <div className="glass-panel px-4 pt-4 pb-12 rounded-2xl mb-8 flex items-center justify-between relative overflow-hidden">
        ...
      </div>
      */}

      <div className="h-4" /> {/* Spacer for labels */}

      {/* Step cards in 2 Columns - Input (Left) / Output (Right) */}
      {/* Pipeline Steps - Vertical Layout */}
      <div className="space-y-12">
        {/* Section 1: Configuration (Active or Completed) */}
        <div className="space-y-6">
             <div className="flex items-center gap-2 mb-2 text-sm font-medium text-[var(--text-muted)] uppercase tracking-wider">
                <div className="w-1 h-4 bg-[var(--primary)] rounded-full"></div>
                配置任务
             </div>
             {pipeline.steps.filter((_, i) => i === 0).map((step) => (
              <StepCard
                key={step.index} 
                step={step}
                isActive={step.index === pipeline.current_step}
                onExecute={(inputs: Record<string, any>) => executeStep(step.index, inputs)}
                executing={executing && step.index === pipeline.current_step}
                isPipelineRunning={pipeline.status === 'running' || executing}
                isCompleted={step.status === 'completed'}
                defaultExpanded={true}
              />
            ))}
        </div>

        {/* Failure Alert (Inserted between config and results if failed) */}
        {pipeline.steps.some(s => s.status === 'failed' && (s.type === 'llm_generate' || s.type === 'export')) && (
            <div className="bg-[var(--error)]/10 border border-[var(--error)]/20 p-4 rounded-xl flex items-center gap-3 text-[var(--error)] animate-in slide-in-from-top-2">
                <AlertCircle className="w-5 h-5 shrink-0" />
                <div className="text-sm">
                    <strong>生成过程中断</strong>
                    <div className="opacity-80 text-xs mt-1">
                        {(() => {
                            const failedStep = pipeline.steps.find(s => s.status === 'failed');
                            if (failedStep?.result?.error) return failedStep.result.error;
                            if (failedStep?.result) return `未知错误: ${JSON.stringify(failedStep.result)}`;
                            return '后台服务连接失败或超时，请重试。';
                        })()}
                    </div>
                </div>
            </div>
        )}

        {/* Section 2: Results (Only show if we have results or are processing them) */}
        {(pipeline.current_step > 0 || pipeline.steps.some((s, i) => i > 0 && s.status !== 'pending')) && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-700">
                <div className="flex items-center gap-2 mb-2 text-sm font-medium text-[var(--text-muted)] uppercase tracking-wider">
                    <div className="w-1 h-4 bg-[var(--success)] rounded-full"></div>
                    生成结果
                </div>
                {pipeline.steps.filter((step) => 
                    step.index > 0 && 
                    step.type !== 'llm_generate' && 
                    step.type !== 'export'
                ).map((step) => (
                <StepCard
                    key={step.index}
                    step={step}
                    isActive={step.index === pipeline.current_step}
                    onExecute={(inputs: Record<string, any>) => executeStep(step.index, inputs)}
                    executing={executing && step.index === pipeline.current_step}
                    isCompleted={step.status === 'completed'}
                />
                ))}
            </div>
        )}
      </div>

      {/* Completion */}
      {pipeline.status === 'completed' && (
        <div className="text-center py-8 opacity-50 text-sm hover:opacity-100 transition-opacity">
          <button onClick={onComplete} className="text-[var(--primary)] text-sm underline underline-offset-4">
            开始新的创作
          </button>
        </div>
      )}
    </div>
  )
}
