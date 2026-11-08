/**
 * Direct tests for the reconciliation API client.
 *
 * The page/component tests mock this module away, so the client's own job — the
 * exact URLs, HTTP methods and query-string mapping it sends — was untested.
 * These tests pin the client to the real routes in
 * `backend/app/api/routes/reconciliation.py` (note the `status`, `has_issues`
 * and `run_id` query aliases).
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { API_BASE_URL, ApiError } from '../client'
import {
  getResult,
  getSummary,
  listResults,
  listRuns,
  runReconciliation,
} from '../reconciliation'

/** Minimal Response stand-in: only the members `request()` touches. */
function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response
}

/** Stub `fetch` to record calls and return a canned JSON body. */
function stubFetch(body: unknown = {}, status = 200) {
  const fetchMock = vi.fn(async () => jsonResponse(body, status))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** The URL passed to the most recent fetch call. */
function lastUrl(fetchMock: ReturnType<typeof vi.fn>): string {
  const [url] = fetchMock.mock.calls.at(-1) as [string]
  return url
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('reconciliation API client', () => {
  it('maps every filter onto the documented query aliases', async () => {
    const fetchMock = stubFetch({ rows: [], total: 0 })

    await listResults({
      status: 'short_paid',
      marketplace: 'amazon',
      hasIssues: true,
      runId: 2,
      limit: 20,
      offset: 40,
    })

    expect(lastUrl(fetchMock)).toBe(
      `${API_BASE_URL}/reconciliation?status=short_paid&marketplace=amazon&has_issues=true&run_id=2&limit=20&offset=40`,
    )
  })

  it('drops empty filters and falsey flags instead of sending blanks', async () => {
    const fetchMock = stubFetch({ rows: [], total: 0 })

    await listResults({ status: '', marketplace: '', hasIssues: false, runId: undefined })

    expect(lastUrl(fetchMock)).toBe(`${API_BASE_URL}/reconciliation`)
  })

  it('reads the latest run when no run_id is given', async () => {
    const fetchMock = stubFetch({ rows: [], total: 0 })

    await listResults()

    expect(lastUrl(fetchMock)).toBe(`${API_BASE_URL}/reconciliation`)
  })

  it('lists runs without a query string when unpaged, and with one when paged', async () => {
    const fetchMock = stubFetch({ rows: [], total: 0 })

    await listRuns()
    expect(lastUrl(fetchMock)).toBe(`${API_BASE_URL}/reconciliation/runs`)

    await listRuns({ limit: 10, offset: 20 })
    expect(lastUrl(fetchMock)).toBe(`${API_BASE_URL}/reconciliation/runs?limit=10&offset=20`)
  })

  it('scopes the summary by marketplace and run', async () => {
    const fetchMock = stubFetch({ run_id: 3 })

    await getSummary({ marketplace: 'flipkart', runId: 3 })

    expect(lastUrl(fetchMock)).toBe(
      `${API_BASE_URL}/reconciliation/summary?marketplace=flipkart&run_id=3`,
    )
  })

  it('loads a single result by id and a run with its results', async () => {
    const fetchMock = stubFetch({ id: 10 })

    await getResult(10)
    expect(lastUrl(fetchMock)).toBe(`${API_BASE_URL}/reconciliation/10`)
  })

  it('runs reconciliation with a POST', async () => {
    const fetchMock = stubFetch({ id: 7, is_current: true })

    await runReconciliation()

    const [url, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit]
    expect(url).toBe(`${API_BASE_URL}/reconciliation/run`)
    expect(init.method).toBe('POST')
  })

  it('surfaces a backend failure as an ApiError carrying its status', async () => {
    stubFetch({ detail: 'Reconciliation result 10 was not found.' }, 404)

    await expect(getResult(10)).rejects.toBeInstanceOf(ApiError)
    await expect(getResult(10)).rejects.toMatchObject({
      status: 404,
      message: 'Reconciliation result 10 was not found.',
    })
  })
})
