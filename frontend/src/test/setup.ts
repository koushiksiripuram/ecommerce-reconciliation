import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// `globals` is off, so Testing Library cannot register its own auto-cleanup.
// Unmount rendered trees after every test to keep the jsdom document isolated.
afterEach(() => {
  cleanup()
})
