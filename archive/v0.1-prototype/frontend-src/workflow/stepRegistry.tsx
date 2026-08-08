import type { ReactNode } from "react";

import HumanSelectStep from "../components/steps/HumanSelectStep";
import LLMGenerateStep from "../components/steps/LLMGenerateStep";
import TextInputStep from "../components/steps/TextInputStep";
import type { Step, StepComponentProps, StepResult, VariantOption } from "../components/steps/types";

interface StepDefinition {
  render: (props: StepComponentProps) => ReactNode;
  executeClient?: (step: Step, steps: Step[], inputs: Record<string, unknown>) => StepResult;
  hydrate?: (step: Step, steps: Step[]) => Step;
}

const STEP_DEFINITIONS: Record<string, StepDefinition> = {
  text_input: {
    render: (props) => <TextInputStep {...props} />,
  },
  llm_generate: {
    render: (props) => <LLMGenerateStep {...props} />,
  },
  human_select: {
    render: (props) => <HumanSelectStep {...props} />,
    executeClient: executeHumanSelectStep,
    hydrate: (step, steps) => ({
      ...step,
      config: {
        ...step.config,
        variants: getReviewVariants(step, steps),
      },
    }),
  },
};

export function renderStep(step: Step, props: StepComponentProps) {
  return getStepDefinition(step.type).render(props);
}

export function executeClientStep(step: Step, steps: Step[], inputs: Record<string, unknown>) {
  const definition = getStepDefinition(step.type);
  if (!definition.executeClient) {
    throw new Error(`Unsupported client step type: ${step.type}`);
  }
  return definition.executeClient(step, steps, inputs);
}

export function hydrateStepForDisplay(step: Step, steps: Step[]) {
  const definition = STEP_DEFINITIONS[step.type];
  return definition?.hydrate ? definition.hydrate(step, steps) : step;
}

function getStepDefinition(stepType: string) {
  const definition = STEP_DEFINITIONS[stepType];
  if (!definition) {
    throw new Error(`Unknown step type: ${stepType}`);
  }
  return definition;
}

function executeHumanSelectStep(step: Step, steps: Step[], inputs: Record<string, unknown>): StepResult {
  const rawVariants = getReviewVariants(step, steps);
  if (rawVariants.length === 0) {
    throw new Error("没有可供选择的生成结果");
  }

  const variants = rawVariants.map(normalizeVariantOption);
  const selectedIndices = Array.isArray(inputs.selected_indices)
    ? inputs.selected_indices
        .map((value) => Number(value))
        .filter((value) => Number.isInteger(value) && value >= 0 && value < variants.length)
    : [];

  if (selectedIndices.length === 0) {
    throw new Error("请至少选择一个结果");
  }

  const selectedVariants = selectedIndices.map((index) => variants[index]);
  const editedContent = typeof inputs.edited_content === "string" ? inputs.edited_content.trim() : "";

  return {
    content: editedContent || selectedVariants.map((variant) => variant.content).join("\n\n"),
    selected: selectedVariants,
    selected_indices: selectedIndices,
  };
}

function getReviewVariants(step: Step, steps: Step[]): Array<string | VariantOption> {
  const sourceStep = steps.find((candidate) => candidate.id === step.source_step);
  return sourceStep?.result?.variants ?? [];
}

function normalizeVariantOption(variant: string | VariantOption): VariantOption {
  if (typeof variant === "string") {
    return { content: variant };
  }
  return {
    label: variant.label,
    content: variant.content,
  };
}
