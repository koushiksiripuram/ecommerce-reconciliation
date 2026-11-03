import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import {
  ApiError,
  fetchCurrentUser,
  login as loginRequest,
  logout as logoutRequest,
} from '../api/client'
import type { CurrentUser } from '../api/client'

export type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated'

interface AuthContextValue {
  status: AuthStatus
  user: CurrentUser | null
  signIn: (email: string, password: string) => Promise<void>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

/**
 * Holds the session for the whole app.
 *
 * The access token lives in an HttpOnly cookie, so this component only ever
 * holds the public user profile. On mount it asks the backend who is signed in,
 * which is also what protects the application screens from unauthenticated
 * access: until that call succeeds, `status` is not `authenticated`.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [user, setUser] = useState<CurrentUser | null>(null)

  useEffect(() => {
    let cancelled = false

    fetchCurrentUser()
      .then((current) => {
        if (cancelled) return
        setUser(current)
        setStatus('authenticated')
      })
      .catch((error: unknown) => {
        if (cancelled) return
        // A 401 just means "not signed in". Any other failure is surfaced in the
        // console but also treated as signed out, so the UI never gets stuck.
        if (!(error instanceof ApiError) || error.status !== 401) {
          console.warn('Could not restore the session', error)
        }
        setUser(null)
        setStatus('unauthenticated')
      })

    return () => {
      cancelled = true
    }
  }, [])

  const signIn = useCallback(async (email: string, password: string) => {
    const current = await loginRequest(email, password)
    setUser(current)
    setStatus('authenticated')
  }, [])

  const signOut = useCallback(async () => {
    try {
      await logoutRequest()
    } catch (error) {
      console.warn('Logout request failed', error)
    }
    setUser(null)
    setStatus('unauthenticated')
  }, [])

  const value = useMemo(
    () => ({ status, user, signIn, signOut }),
    [status, user, signIn, signOut],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

/** Access the current session. Throws when used outside an `AuthProvider`. */
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (context === null) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
