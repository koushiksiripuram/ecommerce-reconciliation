import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../../api/client'
import { uploadImport } from '../../../api/imports'
import { SOURCE_TYPES, makeBatch } from '../../../test/importFixtures'
import { ImportUploadForm } from '../ImportUploadForm'

vi.mock('../../../api/imports', () => ({
  uploadImport: vi.fn(),
}))

const uploadMock = vi.mocked(uploadImport)

function renderForm(canManage = true) {
  const onUploaded = vi.fn()
  render(
    <ImportUploadForm
      canManage={canManage}
      sourceTypes={SOURCE_TYPES}
      partnerSuggestions={['amazon']}
      onUploaded={onUploaded}
    />,
  )
  return { onUploaded }
}

async function chooseFile(user: ReturnType<typeof userEvent.setup>) {
  const file = new File(['Order ID,Amount\nA-1,10.00'], 'orders.csv', { type: 'text/csv' })
  await user.upload(screen.getByLabelText('File'), file)
  return file
}

/**
 * The form uses native `required` validation, which jsdom evaluates more
 * strictly than a browser; dispatch the submit event directly instead.
 */
function submitForm() {
  const form = screen.getByRole('button', { name: /upload file/i }).closest('form')
  if (form === null) throw new Error('Upload form not found')
  fireEvent.submit(form)
}

describe('ImportUploadForm', () => {
  it('hides the upload controls from non-operators', () => {
    renderForm(false)
    expect(screen.getByText(/can view imports but not upload/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /upload file/i })).not.toBeInTheDocument()
  })

  it('keeps submit disabled until a source, partner and file are chosen', async () => {
    const user = userEvent.setup()
    renderForm()

    const submit = screen.getByRole('button', { name: /upload file/i })
    expect(submit).toBeDisabled()

    await user.type(screen.getByLabelText('Partner'), 'amazon')
    expect(submit).toBeDisabled()

    await chooseFile(user)
    expect(submit).toBeEnabled()
  })

  it('uploads the file and reports the created batch', async () => {
    const user = userEvent.setup()
    const batch = makeBatch({ id: 42, original_filename: 'orders.csv' })
    uploadMock.mockResolvedValue(batch)
    const { onUploaded } = renderForm()

    await user.type(screen.getByLabelText('Partner'), 'amazon')
    const file = await chooseFile(user)
    submitForm()

    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith(batch))
    expect(uploadMock).toHaveBeenCalledTimes(1)
    const payload = uploadMock.mock.calls[0][0]
    expect(payload.file).toBe(file)
    expect(payload.sourceType).toBe('orders')
    expect(payload.partner).toBe('amazon')
    expect(await screen.findByText(/uploaded orders\.csv/i)).toBeInTheDocument()
  })

  it('surfaces duplicate-upload conflicts from the backend', async () => {
    const user = userEvent.setup()
    uploadMock.mockRejectedValue(new ApiError(409, 'This file was already imported (batch 3).'))
    renderForm()

    await user.type(screen.getByLabelText('Partner'), 'amazon')
    await chooseFile(user)
    submitForm()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('This file was already imported (batch 3).')
  })

  it('explains when the file type is rejected', async () => {
    const user = userEvent.setup()
    uploadMock.mockRejectedValue(new ApiError(415, 'Unsupported'))
    renderForm()

    await user.type(screen.getByLabelText('Partner'), 'amazon')
    await chooseFile(user)
    submitForm()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Only CSV and XLSX files are supported.')
  })
})
