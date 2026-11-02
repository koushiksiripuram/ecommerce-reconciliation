/** Base URL for backend API calls. Falls back to the Vite dev proxy path. */
const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '/api'

export interface HealthResponse {
  status: string
  service: string
}

/** Call the backend health endpoint. Throws when the request fails. */
export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/health`)

  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}`)
  }

  return (await response.json()) as HealthResponse
}
