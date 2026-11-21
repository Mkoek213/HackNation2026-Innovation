const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly kind: "http" | "network" | "response",
    public readonly status?: number,
    options?: ErrorOptions,
  ) {
    super(message, options);
    this.name = "ApiError";
  }
}

/** Read a JSON API operation. T must match its documented OpenAPI response. */
export async function apiGet<T>(path: `/${string}`, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl.replace(/\/+$/, "")}/${path.replace(/^\/+/, "")}`, {
      headers: { Accept: "application/json" },
      credentials: "omit",
      cache: "no-store",
      signal,
    });
  } catch (cause) {
    if (signal?.aborted) throw cause;
    throw new ApiError("Nie udało się połączyć z API. Spróbuj ponownie.", "network", undefined, { cause });
  }
  if (!response.ok) {
    throw new ApiError(`API zwróciło błąd HTTP ${response.status}.`, "http", response.status);
  }
  try {
    return await response.json() as T;
  } catch (cause) {
    throw new ApiError("API zwróciło nieprawidłową odpowiedź JSON.", "response", response.status, { cause });
  }
}
