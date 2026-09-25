import { z } from "zod";

export const errorEnvelopeSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z.unknown().optional(),
    request_id: z.string().nullable().optional(),
  }),
});

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly details: unknown;

  constructor(params: {
    status: number;
    code: string;
    message: string;
    requestId?: string | null;
    details?: unknown;
  }) {
    super(params.message);
    this.name = "ApiError";
    this.status = params.status;
    this.code = params.code;
    this.requestId = params.requestId ?? null;
    this.details = params.details;
  }
}

export class ApiUnreachableError extends Error {
  constructor(
    readonly url: string,
    cause: unknown,
  ) {
    super(`API is unreachable at ${url}`, { cause });
    this.name = "ApiUnreachableError";
  }
}

export class ApiContractError extends Error {
  constructor(
    readonly url: string,
    readonly issues: z.core.$ZodIssue[],
  ) {
    super(`API response from ${url} does not match the expected contract`);
    this.name = "ApiContractError";
  }
}

export function describeApiError(error: unknown): string {
  if (error instanceof ApiUnreachableError) return "Сервер API недоступен";
  if (error instanceof ApiContractError) return "Ответ API не совпал с ожидаемым форматом";
  if (error instanceof ApiError) return error.message;
  return "Запрос не выполнен";
}
