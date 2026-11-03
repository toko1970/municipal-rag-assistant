export type ApiError = {
  error: { code: string; message: string; retryable: boolean };
};

export type Reference = {
  reference_id: string;
  document_name: string;
  version?: string | null;
  effective_date?: string | null;
  document_role?: string | null;
  heading: string;
  page_number?: number | null;
  content: string;
  image_url?: string | null;
  image_alt?: string | null;
  visual_asset?: {
    url: string;
    mime_type: "image/png" | "image/jpeg" | "image/webp";
    page_number: number;
    alt: string;
  } | null;
  [key: string]: unknown;
};

export type QuestionResult = {
  request_id: string;
  answer: string;
  answer_label: string | null;
  answer_status: string;
  degraded: boolean;
  references: Reference[];
  generation: Record<string, unknown>;
  classification?: Record<string, unknown> | null;
  guidance?: Record<string, unknown> | null;
  [key: string]: unknown;
};

export type KeyRegistration = {
  submit_by: string;
  session_expires_at: string;
};

export type FeedbackValue = "採用した" | "修正して採用した" | "採用しなかった";

export class ApiClientError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly retryable: boolean,
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { credentials: "same-origin", ...init });
  } catch {
    throw new ApiClientError(0, "NETWORK_ERROR", "通信に失敗しました。接続を確認してください。", true);
  }
  if (response.status === 202) {
    throw new ApiClientError(202, "PROCESSING", "回答を作成しています。しばらくしてから状態を確認してください。", true);
  }
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const error = (payload as ApiError | null)?.error;
    throw new ApiClientError(
      response.status,
      error?.code ?? "INTERNAL_ERROR",
      error?.message ?? "処理を完了できませんでした。時間を置いて再度お試しください。",
      error?.retryable ?? response.status >= 500,
    );
  }
  return payload as T;
}

export const api = {
  registerKey(key: string) {
    return requestJson<KeyRegistration>("/api/idempotency-keys", {
      method: "POST",
      headers: { "Idempotency-Key": key },
    });
  },
  createRequest(question: string, key: string) {
    return requestJson<QuestionResult>("/api/requests", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": key },
      body: JSON.stringify({ question }),
    });
  },
  getByKey(key: string) {
    return requestJson<QuestionResult>("/api/requests/by-idempotency-key", {
      headers: { "Idempotency-Key": key },
    });
  },
  saveFeedback(requestId: string, value: FeedbackValue, comment: string) {
    return requestJson<{ saved: true }>(`/api/requests/${encodeURIComponent(requestId)}/feedback`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value, comment }),
    });
  },
};
