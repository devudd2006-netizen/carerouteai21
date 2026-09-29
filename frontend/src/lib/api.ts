// CareRoute AI — API client. Attaches JWT, refreshes expired sessions, normalizes errors.
const BASE: string =
  import.meta.env.VITE_API_BASE ?? (import.meta.env.DEV ? "http://localhost:8000" : "")

const ACCESS = "cr_access"
const REFRESH = "cr_refresh"

export function tokens() {
  return { access: localStorage.getItem(ACCESS), refresh: localStorage.getItem(REFRESH) }
}
export function setTokens(access: string, refresh?: string) {
  localStorage.setItem(ACCESS, access)
  if (refresh) localStorage.setItem(REFRESH, refresh)
}
export function clearTokens() {
  localStorage.removeItem(ACCESS)
  localStorage.removeItem(REFRESH)
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function raw(path: string, opts: RequestInit = {}): Promise<Response> {
  const { access } = tokens()
  const res = await fetch(BASE + path, {
    ...opts,
    headers: {
      ...(opts.body && !(opts.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
      ...(access ? { Authorization: `Bearer ${access}` } : {}),
      ...(opts.headers ?? {}),
    },
  })
  return res
}

async function refreshSession(): Promise<boolean> {
  const { refresh } = tokens()
  if (!refresh) return false
  const res = await fetch(BASE + "/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  })
  if (!res.ok) return false
  const data = await res.json()
  setTokens(data.access_token)
  return true
}

export async function api<T = any>(path: string, opts: RequestInit = {}, retried = false): Promise<T> {
  let res: Response
  try {
    res = await raw(path, opts)
  } catch {
    throw new ApiError(0, "Network error — check your connection and try again.")
  }
  if (res.status === 401 && !retried && (await refreshSession())) {
    return api<T>(path, opts, true)
  }
  if (res.status === 204) return undefined as T
  let body: any = null
  try {
    body = await res.json()
  } catch {
    /* non-JSON */
  }
  if (!res.ok) {
    if (res.status === 401) clearTokens()
    const detail =
      typeof body?.detail === "string"
        ? body.detail
        : Array.isArray(body?.detail)
          ? body.detail.map((d: any) => d.msg).join("; ")
          : `Request failed (${res.status})`
    throw new ApiError(res.status, detail)
  }
  return body as T
}

export const get = <T = any>(path: string) => api<T>(path)
export const post = <T = any>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) })
export const put = <T = any>(path: string, body?: unknown) =>
  api<T>(path, { method: "PUT", body: body === undefined ? undefined : JSON.stringify(body) })
export const upload = <T = any>(path: string, form: FormData) =>
  api<T>(path, { method: "POST", body: form })

/** Authenticated file view: fetches with the JWT and opens the blob in a new tab. */
export async function openFile(path: string) {
  const { access } = tokens()
  const res = await fetch(BASE + path, { headers: access ? { Authorization: `Bearer ${access}` } : {} })
  if (!res.ok) throw new ApiError(res.status, "Could not open document")
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  window.open(url, "_blank")
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
