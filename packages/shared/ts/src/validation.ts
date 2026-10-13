import { z } from "zod";

// Mirrors api/app/routers/agent_configs.py ValidationResult.
export const validationResultSchema = z.object({
  valid: z.boolean(),
  errors: z.array(z.object({ path: z.string(), message: z.string() })),
});

export type ValidationResult = z.infer<typeof validationResultSchema>;
