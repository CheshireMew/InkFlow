import type { Step, StepResult } from "../components/steps/types";
import { executeClientStep as executeClientStepByType, hydrateStepForDisplay as hydrateStepByType } from "./stepRegistry";

export function createStepState(stepDefs: Array<Omit<Step, "index" | "status" | "result">>): Step[] {
  return stepDefs.map((step, index) => ({
    ...step,
    index,
    status: "pending",
    result: undefined,
  }));
}

export function resetFollowingSteps(steps: Step[], stepIndex: number): Step[] {
  return steps.map((step, index) => {
    if (index <= stepIndex) {
      return step;
    }
    return {
      ...step,
      status: "pending",
      result: undefined,
    };
  });
}

export function buildServerInputs(
  steps: Step[],
  stepIndex: number,
  currentInputs: Record<string, unknown>,
): Record<string, unknown> {
  const history = steps.slice(0, stepIndex).reduce<Record<string, unknown>>((acc, step) => {
    if (step.result) {
      acc[step.id] = step.result;
    }
    return acc;
  }, {});

  return {
    ...history,
    ...currentInputs,
  };
}

export function executeClientStep(step: Step, steps: Step[], inputs: Record<string, unknown>): StepResult {
  return executeClientStepByType(step, steps, inputs);
}

export function hydrateStepForDisplay(step: Step, steps: Step[]): Step {
  return hydrateStepByType(step, steps);
}
