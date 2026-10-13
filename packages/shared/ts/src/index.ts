export { agentConfigSchema, type AgentConfig } from "./generated/agent-config";
export { callEventSchema, type CallEvent } from "./generated/events";

/** Response of `POST /agent-configs/validate` — the only place configs are validated. */
export { validationResultSchema, type ValidationResult } from "./validation";
