export interface ActionResult {
  success: boolean;
  data: unknown;
  error?: string;
  meta?: unknown;
}

export async function executeAction(
  tool: string,
  inputs: Record<string, unknown>,
  config: Record<string, unknown>,
): Promise<ActionResult> {
  try {
    const res = await fetch("/api/actions/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tool, inputs, config }),
    });

    if (!res.ok) {
      throw new Error(`API Error: ${res.statusText}`);
    }

    return await res.json();
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Unknown error";
    console.error("Action Execution Failed:", err);
    return {
      success: false,
      data: null,
      error: message,
    };
  }
}
