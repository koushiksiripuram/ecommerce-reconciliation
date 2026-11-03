/** Base URL for backend API calls. Falls back to the Vite dev proxy path. */
const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '/api'

/** Error carrying the HTTP status so callers can branch on 401/403. */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export interface HealthResponse {
  status: string
  service: string
}

export interface Role {
  id: number
  name: string
}

export interface CurrentUser {
  id: number
  email: string
  full_name: string
  is_active: boolean
  role: Role
}

/** Extract the backend `detail` field when present, else fall back to the status. */
async function readErrorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') {
      return body.detail
    }
  } catch {
    // Non-JSON error body; fall through to the generic message.
  }
  return `Request failed with status ${response.status}`
}

/**
 * Shared fetch wrapper.
 *
 * `credentials: 'include'` is what sends the HttpOnly access-token cookie. The
 * token itself is never readable from JavaScript.
 */
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...init.headers },
  })

  if (!response.ok) {
    throw new ApiError(response.status, await readErrorMessage(response))
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

/** Call the backend health endpoint. */
export function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health')
}

/** Exchange credentials for an access-token cookie. */
export function login(email: string, password: string): Promise<CurrentUser> {
  return request<CurrentUser>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

/** Fetch the currently authenticated user. Throws an ApiError with status 401 when signed out. */
export function fetchCurrentUser(): Promise<CurrentUser> {
  return request<CurrentUser>('/auth/me')
}

/** Clear the access-token cookie on the server. */
export function logout(): Promise<void> {
  return request<void>('/auth/logout', { method: 'POST' })
}
