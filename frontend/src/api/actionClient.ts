import { API_BASE } from "../config";

export interface ActionResponse {
  success: boolean;
  data: any;
  error?: string;
}

export const executeAction = async (
  tool: string,
  inputs: any,
  config: any = {},
): Promise<ActionResponse> => {
  try {
    const response = await fetch(`${API_BASE}/actions/run`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        tool,
        inputs,
        config,
      }),
    });

    if (!response.ok) {
      const err = await response.json();
      return {
        success: false,
        data: null,
        error: err.detail || "Request failed",
      };
    }

    return await response.json();
  } catch (err) {
    return { success: false, data: null, error: String(err) };
  }
};
