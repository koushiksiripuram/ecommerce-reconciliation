import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError } from '../api/client'
import { getSummary, listResults, listRuns, runReconciliation } from '../api/reconciliation'
import type {
  ReconciliationResult,
  ReconciliationRun,
  ReconciliationSummary,
} from '../api/reconciliation'
import { useAuth } from '../auth/AuthContext'
import { canManageReconciliation } from '../config/roles'
import { ReconciliationDetail } from './reconciliation/ReconciliationDetail'
import { ReconciliationResultsTable } from './reconciliation/ReconciliationResultsTable'
import type { ReconciliationFilters } from './reconciliation/ReconciliationResultsTable'
import { ReconciliationRuns } from './reconciliation/ReconciliationRuns'
import { ReconciliationSummaryCards } from './reconciliation/ReconciliationSummary'
import { formatDateTime } from './reconciliation/format'

const PAGE_SIZE = 20
const RUN_PAGE_SIZE = 10

const EMPTY_FILTERS: ReconciliationFilters = { status: '', marketplace: '', onlyIssues: false }

function listErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 401) {
    return 'Your session has expired. Please sign in again.'
  }
  return 'Could not load reconciliation data. Please try again.'
}

function runErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return 'Your session has expired. Please sign in again.'
    if (error.status === 403) return 'You do not have permission to run reconciliation.'
    return error.message
  }
  return 'Could not run reconciliation. Please try again.'
}

export function Reconciliation() {
  const { user } = useAuth()
  const canRun = user !== null && canManageReconciliation(user.role.name)

  const [runs, setRuns] = useState<ReconciliationRun[]>([])
  const [runsTotal, setRunsTotal] = useState(0)
  const [runsPage, setRunsPage] = useState(0)
  const [runsLoading, setRunsLoading] = useState(true)
  const [runsError, setRunsError] = useState<string | null>(null)

  //: The run the summary and results are scoped to. Null until the first load.
  const [activeRun, setActiveRun] = useState<ReconciliationRun | null>(null)

  const [summary, setSummary] = useState<ReconciliationSummary | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(true)
  const [summaryError, setSummaryError] = useState<string | null>(null)

  const [results, setResults] = useState<ReconciliationResult[]>([])
  const [resultsTotal, setResultsTotal] = useState(0)
  const [resultsLoading, setResultsLoading] = useState(true)
  const [resultsError, setResultsError] = useState<string | null>(null)

  const [filters, setFilters] = useState<ReconciliationFilters>(EMPTY_FILTERS)
  const [page, setPage] = useState(0)
  const [reloadToken, setReloadToken] = useState(0)
  const [selectedId, setSelectedId] = useState<number | null>(null)

  const [isRunning, setIsRunning] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [runNotice, setRunNotice] = useState<string | null>(null)

  // The run history doubles as the source of the run-level counts. The first
  // page always holds the current run, so it is the default scope.
  useEffect(() => {
    let cancelled = false
    setRunsLoading(true)
    setRunsError(null)

    listRuns({ limit: RUN_PAGE_SIZE, offset: runsPage * RUN_PAGE_SIZE })
      .then((data) => {
        if (cancelled) return
        setRuns(data.rows)
        setRunsTotal(data.total)
        if (runsPage === 0) {
          setActiveRun((current) => {
            const stillLoaded = current !== null && data.rows.some((run) => run.id === current.id)
            return stillLoaded ? current : (data.rows[0] ?? null)
          })
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setRunsError(listErrorMessage(err))
        setRuns([])
        setRunsTotal(0)
      })
      .finally(() => {
        if (!cancelled) setRunsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [runsPage, reloadToken])

  const activeRunId = activeRun?.id
  const marketplaceFilter = filters.marketplace.trim()

  useEffect(() => {
    let cancelled = false
    setSummaryLoading(true)
    setSummaryError(null)

    getSummary({ runId: activeRunId, marketplace: marketplaceFilter })
      .then((data) => {
        if (!cancelled) setSummary(data)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setSummaryError(listErrorMessage(err))
        setSummary(null)
      })
      .finally(() => {
        if (!cancelled) setSummaryLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [activeRunId, marketplaceFilter, reloadToken])

  useEffect(() => {
    let cancelled = false
    setResultsLoading(true)
    setResultsError(null)

    listResults({
      status: filters.status,
      marketplace: marketplaceFilter,
      hasIssues: filters.onlyIssues ? true : undefined,
      runId: activeRunId,
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    })
      .then((data) => {
        if (cancelled) return
        setResults(data.rows)
        setResultsTotal(data.total)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setResultsError(listErrorMessage(err))
        setResults([])
        setResultsTotal(0)
      })
      .finally(() => {
        if (!cancelled) setResultsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [activeRunId, filters, page, reloadToken])

  const refresh = useCallback(() => {
    setReloadToken((token) => token + 1)
  }, [])

  const handleFiltersChange = useCallback((next: ReconciliationFilters) => {
    setFilters(next)
    setPage(0)
  }, [])

  const handleSelectRun = useCallback((run: ReconciliationRun) => {
    setActiveRun(run)
    setPage(0)
    setSelectedId(null)
  }, [])

  const handleRun = useCallback(async () => {
    setIsRunning(true)
    setRunError(null)
    setRunNotice(null)
    try {
      const run = await runReconciliation()
      setActiveRun(run)
      setRunsPage(0)
      setPage(0)
      setSelectedId(null)
      setReloadToken((token) => token + 1)
      setRunNotice(`Reconciliation run #${run.id} completed.`)
    } catch (err: unknown) {
      setRunError(runErrorMessage(err))
    } finally {
      setIsRunning(false)
    }
  }, [])

  /** Marketplaces seen on the loaded page, offered as filter options. */
  const marketplaces = useMemo(() => {
    const names = new Set<string>()
    for (const row of results) {
      const marketplace = row.order?.marketplace ?? row.settlement_record?.marketplace
      if (marketplace) names.add(marketplace)
    }
    return Array.from(names).sort((a, b) => a.localeCompare(b))
  }, [results])

  if (selectedId !== null) {
    return <ReconciliationDetail resultId={selectedId} onBack={() => setSelectedId(null)} />
  }

  const runsHasNext = runsPage * RUN_PAGE_SIZE + runs.length < runsTotal

  return (
    <section className="page page--wide">
      <header className="page__header">
        <div className="card__row">
          <div>
            <h1 className="page__title">Reconciliation</h1>
            <p className="page__subtitle">
              Compare every order against the money actually received, and review the gaps.
            </p>
          </div>
          {canRun && (
            <button
              className="button button--primary"
              type="button"
              onClick={handleRun}
              disabled={isRunning || runsLoading}
            >
              {isRunning ? 'Running…' : 'Run reconciliation'}
            </button>
          )}
        </div>
      </header>

      {!canRun && (
        <p className="card__hint">
          Your role can review reconciliation but not start a new run. Ask a Finance Executive or
          Co-Founder to run it.
        </p>
      )}

      {runError !== null && (
        <p className="alert alert--danger" role="alert">
          {runError}
        </p>
      )}

      {runNotice !== null && (
        <p className="alert alert--success" role="status">
          {runNotice}
        </p>
      )}

      <ReconciliationSummaryCards
        summary={summary}
        run={activeRun}
        isLoading={summaryLoading}
        error={summaryError}
      />

      {activeRun !== null && !activeRun.is_current && (
        <p className="alert alert--warning" role="status">
          Viewing run #{activeRun.id} from {formatDateTime(activeRun.started_at)}. This run has been
          superseded — its results are a preserved snapshot, not the current position.
        </p>
      )}

      <ReconciliationResultsTable
        results={results}
        total={resultsTotal}
        isLoading={resultsLoading}
        error={resultsError}
        filters={filters}
        marketplaces={marketplaces}
        page={page}
        pageSize={PAGE_SIZE}
        onFiltersChange={handleFiltersChange}
        onPrevious={() => setPage((current) => Math.max(0, current - 1))}
        onNext={() => setPage((current) => current + 1)}
        onRefresh={refresh}
        onOpen={setSelectedId}
      />

      <ReconciliationRuns
        runs={runs}
        activeRunId={activeRunId ?? null}
        isLoading={runsLoading}
        error={runsError}
        page={runsPage}
        pageSize={RUN_PAGE_SIZE}
        hasNext={runsHasNext}
        onSelect={handleSelectRun}
        onPrevious={() => setRunsPage((current) => Math.max(0, current - 1))}
        onNext={() => setRunsPage((current) => current + 1)}
        onRefresh={refresh}
      />
    </section>
  )
}
