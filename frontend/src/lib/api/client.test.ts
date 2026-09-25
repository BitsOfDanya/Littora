import { afterEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";
import { apiRequest, apiUrl, resolveApiUrl } from "./client";
import { ApiContractError, ApiError, ApiUnreachableError } from "./errors";

const schema = z.object({ status: z.literal("ok") });

function mockFetch(response: Response | Error) {
  const fetchMock = vi.fn(async () => {
    if (response instanceof Error) throw response;
    return response;
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const json = (body: unknown, init: ResponseInit = {}) =>
  new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" }, ...init });

afterEach(() => vi.unstubAllGlobals());

describe("apiRequest", () => {
  it("builds versioned URLs against the configured base", () => {
    expect(apiUrl("/health")).toBe("http://localhost:8000/api/v1/health");
    expect(resolveApiUrl("http://api.example.org", "/meta")).toBe(
      "http://api.example.org/api/v1/meta",
    );
  });

  it("keeps requests on the page origin in same-origin mode", () => {
    expect(resolveApiUrl("/", "/health")).toBe("/api/v1/health");
  });

  it("returns parsed data for a valid response", async () => {
    mockFetch(json({ status: "ok" }));
    await expect(apiRequest("/health", schema)).resolves.toEqual({ status: "ok" });
  });

  it("maps the backend error envelope to ApiError", async () => {
    mockFetch(
      json(
        {
          error: { code: "not_found", message: "Not Found", details: null, request_id: "abc12345" },
        },
        { status: 404 },
      ),
    );
    const error = await apiRequest("/missing", schema).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 404, code: "not_found", requestId: "abc12345" });
  });

  it("reports an unreachable backend separately from HTTP errors", async () => {
    mockFetch(new TypeError("Failed to fetch"));
    await expect(apiRequest("/health", schema)).rejects.toBeInstanceOf(ApiUnreachableError);
  });

  it("rejects responses that break the contract", async () => {
    mockFetch(json({ status: "degraded" }));
    await expect(apiRequest("/health", schema)).rejects.toBeInstanceOf(ApiContractError);
  });
});
