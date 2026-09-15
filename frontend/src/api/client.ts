import type { AnalyzeResponse, ApiError, ExampleQuery } from "../types/api";

/** Thrown for any non-2xx response, carrying the backend's structured error. */
export class AnalyzeError extends Error {
  constructor(public readonly detail: ApiError) {
    super(detail.message);
  }
}

const BASE = import.meta.env.VITE_API_BASE ?? "/api";

export async function analyze(query: string): Promise<AnalyzeResponse> {
  let response: Response;
  try {
    response = await fetch(`${BASE}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
  } catch {
    throw new AnalyzeError({
      code: "NETWORK_ERROR",
      message: "Could not reach the analysis service. Is the backend running on port 8000?",
      details: {},
    });
  }

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new AnalyzeError(
      body?.error ?? {
        code: "UNKNOWN_ERROR",
        message: `The service returned HTTP ${response.status}.`,
        details: {},
      },
    );
  }
  return body as AnalyzeResponse;
}

export async function fetchExamples(): Promise<ExampleQuery[]> {
  try {
    const response = await fetch(`${BASE}/examples`);
    return response.ok ? ((await response.json()) as ExampleQuery[]) : [];
  } catch {
    return [];
  }
}
