import { useCallback, useEffect, useState } from "react";

import type { Step } from "../components/steps/types";
import {
  buildServerInputs,
  createStepState,
  executeClientStep,
  resetFollowingSteps,
} from "./runtime";

type StepDefinition = Omit<Step, "index" | "status" | "result">;

export function usePipelineRunner(recipeId: string) {
  const [steps, setSteps] = useState<Step[]>([]);
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [executing, setExecuting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadRecipe = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`/api/recipes/${recipeId}`);
      if (!res.ok) {
        throw new Error("Recipe not found");
      }

      const data = await res.json();
      setSteps(createStepState(data.steps as StepDefinition[]));
      setCurrentStepIndex(0);
    } catch (err) {
      console.error("Failed to load recipe:", err);
      setError("无法加载配方");
      setSteps([]);
    } finally {
      setLoading(false);
    }
  }, [recipeId]);

  const runServerStep = useCallback(async (
    step: Step,
    stepIndex: number,
    inputs: Record<string, unknown>,
  ) => {
    const res = await fetch("/api/actions/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tool: step.type,
        config: step.config,
        inputs: buildServerInputs(steps, stepIndex, inputs),
      }),
    });

    if (!res.ok) {
      throw new Error("服务调用失败");
    }

    return res.json();
  }, [steps]);

  const executeStep = useCallback(async (stepIndex: number, inputs: Record<string, unknown>) => {
    const step = steps[stepIndex];
    if (!step) {
      return;
    }

    setExecuting(true);
    setError(null);
    setCurrentStepIndex(stepIndex);
    setSteps((prev) =>
      resetFollowingSteps(prev, stepIndex).map((candidate, index) =>
        index === stepIndex ? { ...candidate, status: "running" } : candidate,
      ),
    );

    try {
      const result =
        step.run_mode === "client"
          ? { success: true, data: executeClientStep(step, steps, inputs) }
          : await runServerStep(step, stepIndex, inputs);

      if (!result.success) {
        throw new Error(result.error || "步骤执行失败");
      }

      setSteps((prev) =>
        prev.map((candidate, index) =>
          index === stepIndex
            ? { ...candidate, status: "completed", result: result.data }
            : candidate,
        ),
      );

      if (stepIndex < steps.length - 1) {
        setCurrentStepIndex(stepIndex + 1);
      }
    } catch (err) {
      console.error("Step execution failed:", err);
      const message = err instanceof Error ? err.message : "处理失败";
      setSteps((prev) =>
        prev.map((candidate, index) =>
          index === stepIndex
            ? { ...candidate, status: "failed", result: { error: message } }
            : candidate,
        ),
      );
    } finally {
      setExecuting(false);
    }
  }, [runServerStep, steps]);

  useEffect(() => {
    void loadRecipe();
  }, [loadRecipe]);

  useEffect(() => {
    if (loading || executing || steps.length === 0) {
      return;
    }

    const currentStep = steps[currentStepIndex];
    if (currentStep?.auto_run && currentStep.status === "pending") {
      void executeStep(currentStepIndex, {});
    }
  }, [steps, currentStepIndex, executing, loading, executeStep]);

  return {
    steps,
    currentStepIndex,
    loading,
    executing,
    error,
    executeStep,
    reload: loadRecipe,
    isCompleted: steps.length > 0 && steps.every((step) => step.status === "completed"),
    hasVisibleProgress: steps.some(
      (step) => step.status !== "pending" || step.index === currentStepIndex,
    ),
    failedMessage: getStepErrorMessage(steps.find((step) => step.status === "failed")),
  };
}

function getStepErrorMessage(step?: Step) {
  const error = step?.result?.error;
  return typeof error === "string" && error ? error : "请重试";
}
