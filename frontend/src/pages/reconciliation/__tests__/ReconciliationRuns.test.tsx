import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { ReconciliationRun } from '../../../api/reconciliation'
import { makeRun } from '../../../test/reconciliationFixtures'
import { ReconciliationRuns } from '../ReconciliationRuns'

const currentRun = makeRun({ id: 2, is_current: true })
const pastRun = makeRun({ id: 1, is_current: false, triggered_by_email: null })

interface SetupOverrides {
  runs?: ReconciliationRun[]
  activeRunId?: number | null
  isLoading?: boolean
  error?: string | null
  page?: number
  pageSize?: number
  hasNext?: boolean
}

function setup(overrides: SetupOverrides = {}) {
  const handlers = {
    onSelect: vi.fn(),
    onPrevious: vi.fn(),
    onNext: vi.fn(),
    onRefresh: vi.fn(),
  }

  render(
    <ReconciliationRuns
      runs={overrides.runs ?? [currentRun, pastRun]}
      activeRunId={overrides.activeRunId ?? 2}
      isLoading={overrides.isLoading ?? false}
      error={overrides.error ?? null}
      page={overrides.page ?? 0}
      pageSize={overrides.pageSize ?? 10}
      hasNext={overrides.hasNext ?? false}
      {...handlers}
    />,
  )

  return handlers
}

describe('ReconciliationRuns', () => {
  it('flags the current run and marks superseded ones', () => {
    setup()

    expect(screen.getByText('Current')).toBeInTheDocument()
    expect(screen.getByText('Superseded')).toBeInTheDocument()
    expect(screen.getByText('#1')).toBeInTheDocument()
    expect(screen.getByText('#2')).toBeInTheDocument()
    // The superseded run has no triggering email recorded.
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('marks the active run as viewing and offers older runs to open', async () => {
    const user = userEvent.setup()
    const { onSelect } = setup()

    expect(screen.getByText('Viewing')).toBeInTheDocument()
    // Only the older (non-active) run has a View button.
    const viewButtons = screen.getAllByRole('button', { name: 'View' })
    expect(viewButtons).toHaveLength(1)

    await user.click(viewButtons[0])
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }))
  })

  it('shows an empty state before the first run', () => {
    setup({ runs: [], activeRunId: null })
    expect(screen.getByText(/no reconciliation has run yet/i)).toBeInTheDocument()
  })

  it('shows a loading state before the first page arrives', () => {
    setup({ runs: [], activeRunId: null, isLoading: true })
    expect(screen.getByText(/loading run history/i)).toBeInTheDocument()
  })

  it('shows an error alert when loading fails', () => {
    setup({ runs: [], activeRunId: null, error: 'Could not load reconciliation data. Please try again.' })
    expect(screen.getByRole('alert')).toHaveTextContent(/could not load reconciliation data/i)
  })

  it('pages when more runs exist', async () => {
    const user = userEvent.setup()
    const { onNext } = setup({ hasNext: true })

    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Next' }))
    expect(onNext).toHaveBeenCalledTimes(1)
  })
})
