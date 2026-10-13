// Checks that codegen produced a usable zod schema. This is not config validation: that is the
// API's job (POST /agent-configs/validate).
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { agentConfigSchema } from "../src";

const examplesDir = fileURLToPath(new URL("../../examples/", import.meta.url));
const examples = readdirSync(examplesDir).filter((f) => f.endsWith(".json"));

describe("generated agentConfigSchema", () => {
  it.each(examples)("parses %s", (file) => {
    const data: unknown = JSON.parse(readFileSync(examplesDir + file, "utf8"));
    expect(agentConfigSchema.safeParse(data).success).toBe(true);
  });

  it("keeps http tool parameter schemas intact", () => {
    const data: unknown = JSON.parse(readFileSync(examplesDir + "clinic_booking.json", "utf8"));
    const config = agentConfigSchema.parse(data);
    const lookup = config.tools.find((t) => t.name === "lookup_patient");
    expect(lookup && "parameters" in lookup ? lookup.parameters : undefined).toEqual({
      type: "object",
      properties: { phone: { type: "string" } },
      required: ["phone"],
    });
  });
});
