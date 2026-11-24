import { idToken } from "@/auth/firebase";

const API_BASE = "/api/v1";

// Fired when the API says the person is no longer signed in (401), so the app can show the
// sign-in page; and when it refuses an action for their role or account (403).
export const SIGNED_OUT_EVENT = "si:signed-out";

// Why a request failed, with the server's own short code when it gave one ("signed_out",
// "no_access", "disabled", "forbidden", "refused"...), so a screen can react to the reason.
export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(message: string, status: number, code: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

// What a person is told when the server gave no message of its own.
function plainFailure(status: number): string {
  if (status === 401) return "Your sign-in has ended. Sign in again.";
  if (status === 403) return "You do not have permission for this.";
  if (status === 404)
    return "That could not be found. It may have been removed.";
  if (status >= 500)
    return "Something went wrong on our side. Try again in a moment.";
  return "That did not work. Try again.";
}

type Detail = string | { code?: unknown; message?: unknown } | undefined;

// The error a failed response becomes: the server's message when it wrote one (a plain string, or
// the `message` of a structured refusal), else a plain sentence for the status.
export function failureFrom(status: number, detail: Detail): ApiError {
  if (typeof detail === "string") return new ApiError(detail, status);
  const code = typeof detail?.code === "string" ? detail.code : null;
  const message =
    typeof detail?.message === "string" ? detail.message : plainFailure(status);
  return new ApiError(message, status, code);
}

interface Options {
  method?: string;
  json?: unknown;
  form?: FormData;
}

async function send(path: string, options: Options, fresh: boolean) {
  const headers: Record<string, string> = {};
  const token = await idToken(fresh);
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: FormData | string | undefined;
  if (options.form) body = options.form;
  else if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  }
  return fetch(`${API_BASE}${path}`, {
    method: options.method ?? "GET",
    headers,
    body,
  });
}

// Every request goes through here, so each one carries the sign-in token. A 401 is tried once more
// with a freshly issued token (the old one may have just expired) before the person is signed out.
async function request<T>(path: string, options: Options = {}): Promise<T> {
  let res = await send(path, options, false);
  if (res.status === 401) res = await send(path, options, true);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const error = failureFrom(res.status, body?.detail as Detail);
    if (res.status === 401)
      window.dispatchEvent(new window.Event(SIGNED_OUT_EVENT));
    throw error;
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path);
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, { method: "POST", json: body });
}

export function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "PATCH", json: body });
}

export function apiPut<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "PUT", json: body });
}

export function apiDelete<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

export function uploadCsv<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  return request<T>(path, { method: "POST", form });
}

// Posts a form (a file plus any fields). The server's refusal is shown as written: a plain message,
// or the `message` of a structured refusal such as "this file is already in the library".
export function apiUpload<T>(path: string, form: FormData): Promise<T> {
  return request<T>(path, { method: "POST", form });
}
