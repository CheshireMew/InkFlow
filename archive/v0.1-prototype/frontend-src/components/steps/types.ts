export interface VariantOption {
  label?: string;
  content: string;
}

export interface FieldConfig {
  id: string;
  type: "text" | "textarea" | "select" | "multiselect";
  label: string;
  placeholder?: string;
  options?: string[];
  default?: string;
  required?: boolean;
}

export interface StepResult {
  text?: string;
  user_input?: string;
  selected?: string | VariantOption[];
  selected_indices?: number[];
  variants?: Array<string | VariantOption>;
  content?: string;
  awaiting_selection?: boolean;
  [key: string]: unknown;
}

export interface Step {
  index: number;
  id: string;
  type: string;
  label: string;
  run_mode: "client" | "server";
  stage: "input" | "generate" | "review";
  auto_run: boolean;
  source_step?: string | null;
  status: "pending" | "running" | "completed" | "failed";
  result?: StepResult;
  config?: {
    fields?: FieldConfig[];
    submit_label?: string;
    [key: string]: unknown;
  };
}

export interface StepComponentProps {
  step: Step;
  onExecute: (inputs: Record<string, unknown>) => void;
  executing: boolean;
  isPipelineRunning?: boolean;
}
