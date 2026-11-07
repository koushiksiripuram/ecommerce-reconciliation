import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// Test runner configuration. Kept separate from `vite.config.ts` so the app
// build keeps its `/api` dev proxy untouched.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    // Tests import `describe`/`it`/`expect` from `vitest` explicitly, so the
    // globals stay off (and no extra tsconfig `types` entry is required).
    globals: false,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
