import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  getImportPreview,
  listImportRecords,
  listImports,
  listSourceTypes,
} from '../../api/imports'
import { SOURCE_TYPES, makeBatch, makePreview } from '../../test/importFixtures'
import { Imports } from '../Imports'

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

vi.mock('../../api/imports', () => ({
  listSourceTypes: vi.fn(),
  listImports: vi.fn(),
  getImportPreview: vi.fn(),
  updateImportMapping: vi.fn(),
  processImport: vi.fn(),
  listImportRecords: vi.fn(),
  uploadImport: vi.fn(),
}))

const batch = makeBatch({ id: 5, original_filename: 'orders-jan.csv', status: 'completed' })

beforeEach(() => {
  vi.resetAllMocks()
  authState.role = 'finance_executive'
  vi.mocked(listSourceTypes).mockResolvedValue(SOURCE_TYPES)
  vi.mocked(listImports).mockResolvedValue([batch])
  vi.mocked(listImportRecords).mockResolvedValue({ total: 0, returned: 0, rows: [] })
})

describe('Imports page', () => {
  it('renders the import history from the API', async () => {
    render(<Imports />)

    expect(screen.getByRole('heading', { name: 'Imports' })).toBeInTheDocument()
    expect(await screen.findByText('orders-jan.csv')).toBeInTheDocument()
    expect(listImports).toHaveBeenCalledWith({
      status: '',
      sourceType: '',
      partner: '',
      limit: 20,
      offset: 0,
    })
  })

  it('hides upload controls for roles that cannot manage imports', async () => {
    authState.role = 'analyst'
    render(<Imports />)

    expect(await screen.findByText(/can view imports but not upload/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /upload file/i })).not.toBeInTheDocument()
  })

  it('shows upload controls for finance operators', async () => {
    render(<Imports />)

    expect(await screen.findByRole('button', { name: /upload file/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'New import' })).toBeInTheDocument()
  })

  it('opens an existing batch and shows its column mapping', async () => {
    const user = userEvent.setup()
    vi.mocked(getImportPreview).mockResolvedValue(
      makePreview({ batch: makeBatch({ id: 5, status: 'mapping_required' }) }),
    )

    render(<Imports />)
    await user.click(await screen.findByRole('button', { name: 'Open' }))

    expect(await screen.findByRole('heading', { name: 'Column mapping' })).toBeInTheDocument()
    await waitFor(() => expect(getImportPreview).toHaveBeenCalledWith(5))
  })

  it('surfaces an error when the history cannot be loaded', async () => {
    vi.mocked(listImports).mockRejectedValue(new Error('offline'))
    render(<Imports />)

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load the import history/i)
  })
})
