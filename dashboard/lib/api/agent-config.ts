import { type ValidationResult, validationResultSchema } from "@vp/shared";

const apiUrl = () => process.env.API_URL ?? "http://localhost:8000";

/**
 * Validate an agent config via the API (vp_shared.validate_agent_config).
 * The dashboard never validates configs itself; this is the only path.
 */
export async function validateAgentConfig(config: unknown): Promise<ValidationResult> {
  const res = await fetch(`${apiUrl()}/agent-configs/validate`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(config),
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Agent config validation request failed: ${res.status}`);
  }
  return validationResultSchema.parse(await res.json());
}
