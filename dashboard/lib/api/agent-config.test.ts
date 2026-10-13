import { afterEach, describe, expect, it, vi } from "vitest";

import { validateAgentConfig } from "./agent-config";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("validateAgentConfig", () => {
  it("posts the config to the API and returns the parsed result", async () => {
    vi.stubEnv("API_URL", "http://api.test");
    const result = { valid: false, errors: [{ path: "$.greeting", message: "required" }] };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(result)));
    vi.stubGlobal("fetch", fetchMock);

    await expect(validateAgentConfig({ greeting: "" })).resolves.toEqual(result);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api.test/agent-configs/validate",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ greeting: "" }) }),
    );
  });

  it("rejects a malformed API response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: 1 }))));
    await expect(validateAgentConfig({})).rejects.toThrow();
  });

  it("throws on non-2xx", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 500 })));
    await expect(validateAgentConfig({})).rejects.toThrow("500");
  });
});
