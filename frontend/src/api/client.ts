import type { AnalyzeResponse, AnalyzeRequest, ApiError, ExampleQuery } from "../types/api";

/** Thrown for any non-2xx response, carrying the backend's structured error. */
export class AnalyzeError extends Error {
  constructor(public readonly detail: ApiError) {
    super(detail.message);
    this.name = "AnalyzeError";
  }
}

const BASE = import.meta.env.VITE_API_BASE ?? "/api";

/** Normalises anything the backend (or a proxy, or a crash) might return. */
function toApiError(body: unknown, status: number): ApiError {
  const error = (body as { error?: Partial<ApiError> } | null)?.error;
  if (error && typeof error.code === "string" && typeof error.message === "string") {
    return {
      code: error.code,
      message: error.message,
      details: (error.details as Record<string, unknown>) ?? {},
      request_id: error.request_id ?? null,
    };
  }
  // A malformed or non-JSON error body must still produce a renderable error.
  return {
    code: status >= 500 ? "SERVICE_ERROR" : "UNKNOWN_ERROR",
    message: `The service returned HTTP ${status} without a usable error body.`,
    details: {},
    request_id: null,
  };
}

export async function analyze(
  request: AnalyzeRequest,
  signal?: AbortSignal,
): Promise<AnalyzeResponse> {
  let response: Response;
  try {
    response = await fetch(`${BASE}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      signal,
    });
  } catch (exception) {
    if ((exception as Error)?.name === "AbortError") throw exception;
    throw new AnalyzeError({
      code: "NETWORK_ERROR",
      message: "Could not reach the analysis service. Is the backend running on port 8000?",
      details: {},
      request_id: null,
    });
  }

  const body = await response.json().catch(() => null);
  if (!response.ok) throw new AnalyzeError(toApiError(body, response.status));

  if (!body || typeof body !== "object" || !(body as AnalyzeResponse).visualization) {
    throw new AnalyzeError({
      code: "MALFORMED_RESPONSE",
      message: "The service returned a response this client could not understand.",
      details: {},
      request_id: null,
    });
  }
  return body as AnalyzeResponse;
}

export async function fetchExamples(): Promise<ExampleQuery[]> {
  try {
    const response = await fetch(`${BASE}/examples`);
    if (!response.ok) return [];
    const body = await response.json();
    return Array.isArray(body) ? (body as ExampleQuery[]) : [];
  } catch {
    return [];
  }
}
