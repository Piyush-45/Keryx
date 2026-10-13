// The call detail page parses persisted events with these generated types.
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { type CallEvent, callEventSchema } from "../src";

const dir = fileURLToPath(new URL("../../examples/events/", import.meta.url));
const files = readdirSync(dir).filter((f) => f.endsWith(".json"));
const load = (file: string): unknown => JSON.parse(readFileSync(dir + file, "utf8"));

describe("generated callEventSchema", () => {
  it.each(files)("parses %s", (file) => {
    expect(callEventSchema.safeParse(load(file)).success).toBe(true);
  });

  it("types turn sides as nullable objects with offsets", () => {
    const event: CallEvent = callEventSchema.parse(load("turn_greeting.json"));
    if (event.type !== "turn") throw new Error("expected a turn");
    expect(event.payload.user).toBeNull();
    expect(event.payload.agent?.start_ms).toBe(420);
    expect(event.payload.agent?.end_ms).toBe(3900);
  });

  it("rejects an unknown event type", () => {
    const bad = { ...(load("call_started.json") as object), type: "call.exploded" };
    expect(callEventSchema.safeParse(bad).success).toBe(false);
  });
});
