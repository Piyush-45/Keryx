export { agentConfigSchema, type AgentConfig } from "./generated/agent-config";

/** Response of `POST /agent-configs/validate` — the only place configs are validated. */
export { validationResultSchema, type ValidationResult } from "./validation";
