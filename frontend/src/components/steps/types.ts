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
  selected?: string;
  variants?: string[];
  content?: string;
  awaiting_selection?: boolean;
  [key: string]: any;
}

export interface Step {
  index: number;
  id?: string;
  type: string;
  label: string;
  status: "pending" | "running" | "completed" | "failed";
  result?: StepResult;
  config?: {
    fields?: FieldConfig[];
    submit_label?: string;
    variants?: string[]; // For human_select injected variants
    [key: string]: any;
  };
}

export interface StepComponentProps {
  step: Step;
  onExecute: (inputs: Record<string, any>) => void;
  executing: boolean;
  isPipelineRunning?: boolean;
}
