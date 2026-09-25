import type { z } from "zod";
import { publicEnv, SAME_ORIGIN } from "@/config/env";
import { ApiContractError, ApiError, ApiUnreachableError, errorEnvelopeSchema } from "./errors";

export const API_V1 = "/api/v1";

type RequestOptions = {
  signal?: AbortSignal;
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
};

export function resolveApiUrl(base: string, path: string): string {
  if (base === SAME_ORIGIN) return `${API_V1}${path}`;
  return new URL(`${API_V1}${path}`, base).toString();
}

export function apiUrl(path: string): string {
  return resolveApiUrl(publicEnv.apiBaseUrl, path);
}

async function readErrorResponse(response: Response): Promise<ApiError> {
  const payload: unknown = await response.json().catch(() => null);
  const envelope = errorEnvelopeSchema.safeParse(payload);
  if (envelope.success) {
    const { code, message, details, request_id } = envelope.data.error;
    return new ApiError({ status: response.status, code, message, details, requestId: request_id });
  }
  return new ApiError({
    status: response.status,
    code: "http_error",
    message: response.statusText || `HTTP ${response.status}`,
    requestId: response.headers.get("X-Request-ID"),
  });
}

export async function apiRequest<Schema extends z.ZodType>(
  path: string,
  schema: Schema,
  options: RequestOptions = {},
): Promise<z.infer<Schema>> {
  const url = apiUrl(path);
  const hasBody = options.body !== undefined;

  let response: Response;
  try {
    response = await fetch(url, {
      method: options.method ?? "GET",
      signal: options.signal,
      headers: {
        Accept: "application/json",
        ...(hasBody ? { "Content-Type": "application/json" } : {}),
      },
      body: hasBody ? JSON.stringify(options.body) : undefined,
    });
  } catch (cause) {
    if (options.signal?.aborted) throw cause;
    throw new ApiUnreachableError(url, cause);
  }

  if (!response.ok) throw await readErrorResponse(response);

  const parsed = schema.safeParse(await response.json());
  if (!parsed.success) throw new ApiContractError(url, parsed.error.issues);
  return parsed.data;
}
