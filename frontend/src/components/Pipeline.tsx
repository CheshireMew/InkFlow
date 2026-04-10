import { type ReactNode } from "react";
import { AlertCircle, Loader2 } from "lucide-react";

import StepCard from "./StepCard";
import type { Step } from "./steps/types";
import { hydrateStepForDisplay } from "../workflow/runtime";
import { usePipelineRunner } from "../workflow/usePipelineRunner";

interface PipelineProps {
  recipeId: string;
  onComplete: () => void;
}

export default function Pipeline({ recipeId, onComplete }: PipelineProps) {
  const {
    steps,
    currentStepIndex,
    loading,
    executing,
    error,
    executeStep,
    reload,
    isCompleted,
    hasVisibleProgress,
    failedMessage,
  } = usePipelineRunner(recipeId);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32">
        <Loader2 className="w-8 h-8 text-[var(--primary)] animate-spin" />
      </div>
    );
  }

  if (error || steps.length === 0) {
    return (
      <div className="text-center py-20 opacity-75">
        <div className="text-6xl mb-4 grayscale">❌</div>
        <h2 className="text-xl text-[var(--text-muted)] mb-6">配方加载失败</h2>
        <p className="text-[var(--text-dim)] mb-8 max-w-md mx-auto">
          {error || "配方不存在或格式错误"}
        </p>
        <button onClick={() => void reload()} className="btn btn-secondary">
          重新加载
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="h-4" />

      <div className="space-y-12">
        <StepSection title="配置任务" accent="var(--primary)" steps={steps.filter((step) => step.stage === "input")}>
          {(step) => (
            <StepCard
              key={step.id}
              step={hydrateStepForDisplay(step, steps)}
              isActive={step.index === currentStepIndex}
              onExecute={(inputs) => executeStep(step.index, inputs)}
              executing={executing && step.index === currentStepIndex}
              isPipelineRunning={executing}
              isCompleted={step.status === "completed"}
              defaultExpanded={true}
            />
          )}
        </StepSection>

        {steps.some((step) => step.status === "failed") && (
          <div className="bg-[var(--error)]/10 border border-[var(--error)]/20 p-4 rounded-xl flex items-center gap-3 text-[var(--error)] animate-in slide-in-from-top-2">
            <AlertCircle className="w-5 h-5 shrink-0" />
            <div className="text-sm">
              <strong>处理过程中断</strong>
              <div className="opacity-80 text-xs mt-1">
                {failedMessage}
              </div>
            </div>
          </div>
        )}

        {hasVisibleProgress && (
          <StepSection
            title="生成结果"
            accent="var(--success)"
            steps={steps.filter((step) => step.stage !== "input")}
          >
            {(step) => (
              <StepCard
                key={step.id}
                step={hydrateStepForDisplay(step, steps)}
                isActive={step.index === currentStepIndex}
                onExecute={(inputs) => executeStep(step.index, inputs)}
                executing={executing && step.index === currentStepIndex}
                isCompleted={step.status === "completed"}
                isPipelineRunning={executing}
              />
            )}
          </StepSection>
        )}
      </div>

      {isCompleted && (
        <div className="text-center py-8 opacity-50 text-sm hover:opacity-100 transition-opacity">
          <button
            onClick={onComplete}
            className="text-[var(--primary)] text-sm underline underline-offset-4"
          >
            开始新的创作
          </button>
        </div>
      )}
    </div>
  );
}

interface StepSectionProps {
  title: string;
  accent: string;
  steps: Step[];
  children: (step: Step) => ReactNode;
}

function StepSection({ title, accent, steps, children }: StepSectionProps) {
  if (steps.length === 0) {
    return null;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 mb-2 text-sm font-medium text-[var(--text-muted)] uppercase tracking-wider">
        <div className="w-1 h-4 rounded-full" style={{ backgroundColor: accent }} />
        {title}
      </div>
      {steps.map((step) => children(step))}
    </div>
  );
}
