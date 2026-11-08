import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  getResult,
  getSummary,
  listResults,
  listRuns,
  runReconciliation,
} from '../../api/reconciliation'
import { makeResult, makeRun, makeSummary } from '../../test/reconciliationFixtures'
import { Reconciliation } from '../Reconciliation'

/** Mutable role so each test can render the page for a different permission set. */
const authState = vi.hoisted(() => ({ role: 'finance_executive' }))

vi.mock('../../auth/AuthContext', () => ({
  useAuth: () => ({
    status: 'authenticated',
    user: {
      id: 1,
      email: 'fin@example.com',
      full_name: 'Fin Exec',
      is_active: true,
      role: { id: 1, name: authState.role },
    },
    signIn: async () => {},
    signOut: async () => {},
  }),
}))

vi.mock('../../api/reconciliation', () => ({
  listRuns: vi.fn(),
  getRun: vi.fn(),
  listResults: vi.fn(),
  getSummary: vi.fn(),
  getResult: vi.fn(),
  runReconciliation: vi.fn(),
}))

const currentRun = makeRun({ id: 2, is_current: true })
const pastRun = makeRun({ id: 1, is_current: false })

beforeEach(() => {
  vi.resetAllMocks()
  authState.role = 'finance_executive'
  vi.mocked(listRuns).mockResolvedValue({
    total: 2,
    returned: 2,
    limit: 10,
    offset: 0,
    rows: [currentRun, pastRun],
  })
  vi.mocked(getSummary).mockResolvedValue(makeSummary({ run_id: 2 }))
  vi.mocked(listResults).mockResolvedValue({
    total: 1,
    returned: 1,
    limit: 20,
    offset: 0,
    rows: [makeResult({ id: 10, run_id: 2 })],
  })
})

describe('Reconciliation page', () => {
  it('renders the summary, results and run history from the API', async () => {
    render(<Reconciliation />)

    expect(screen.getByRole('heading', { name: 'Reconciliation' })).toBeInTheDocument()
    expect(await screen.findByText('Total orders')).toBeInTheDocument()
    expect(await screen.findByText('A-1')).toBeInTheDocument()

    await waitFor(() => expect(listRuns).toHaveBeenCalledWith({ limit: 10, offset: 0 }))
    await waitFor(() => expect(listResults).toHaveBeenCalledWith({
      status: '',
      marketplace: '',
      hasIssues: undefined,
      runId: 2,
      limit: 20,
      offset: 0,
    }))
    expect(getSummary).toHaveBeenCalledWith({ runId: 2, marketplace: '' })
  })

  it('hides the run button for roles that cannot run reconciliation', async () => {
    authState.role = 'analyst'
    render(<Reconciliation />)

    expect(await screen.findByText(/can review reconciliation but not start a new run/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /run reconciliation/i })).not.toBeInTheDocument()
  })

  it('starts a run and reports the new run number', async () => {
    const user = userEvent.setup()
    vi.mocked(runReconciliation).mockResolvedValue(makeRun({ id: 3, is_current: true }))

    render(<Reconciliation />)
    await user.click(await screen.findByRole('button', { name: /run reconciliation/i }))

    await waitFor(() => expect(runReconciliation).toHaveBeenCalledTimes(1))
    expect(await screen.findByText(/reconciliation run #3 completed/i)).toBeInTheDocument()
  })

  it('opens the order-level detail view when a result is viewed', async () => {
    const user = userEvent.setup()
    vi.mocked(getResult).mockResolvedValue(makeResult({ id: 10, run_id: 2 }))

    render(<Reconciliation />)
    await screen.findByText('A-1')

    // The results table is rendered before the run history, so its View button
    // comes first in the document.
    await user.click(screen.getAllByRole('button', { name: 'View' })[0])

    expect(await screen.findByRole('button', { name: /back to reconciliation/i })).toBeInTheDocument()
    expect(getResult).toHaveBeenCalledWith(10)
  })

  it('surfaces an error when the results cannot be loaded', async () => {
    vi.mocked(listResults).mockRejectedValue(new Error('offline'))
    render(<Reconciliation />)

    expect(await screen.findByText(/could not load reconciliation data/i)).toBeInTheDocument()
  })
})
