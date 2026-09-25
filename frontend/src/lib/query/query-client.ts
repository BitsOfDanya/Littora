import { QueryClient } from "@tanstack/react-query";
import { ApiError } from "@/lib/api/errors";

const MAX_RETRIES = 2;

function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status < 500) return false;
  return failureCount < MAX_RETRIES;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        retry: shouldRetry,
      },
    },
  });
}
