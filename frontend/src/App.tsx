import { useState } from 'react'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { Layout } from './components/Layout'
import { NAV_ITEMS } from './config/navigation'
import { Imports } from './pages/Imports'
import { Login } from './pages/Login'
import { Overview } from './pages/Overview'
import { Reconciliation } from './pages/Reconciliation'

function SessionLoading() {
  return (
    <div className="auth-screen">
      <p className="auth-card__subtitle" role="status">
        Loading your session…
      </p>
    </div>
  )
}

function renderScreen(activeId: string) {
  switch (activeId) {
    case 'imports':
      return <Imports />
    case 'reconciliation':
      return <Reconciliation />
    case 'overview':
    default:
      return <Overview />
  }
}

function AppContent() {
  const { status, user, signOut } = useAuth()
  const [activeId, setActiveId] = useState(NAV_ITEMS[0].id)

  if (status === 'loading') {
    return <SessionLoading />
  }

  // Screens are only rendered once the backend has confirmed the session.
  if (status === 'unauthenticated' || user === null) {
    return <Login />
  }

  return (
    <Layout
      items={NAV_ITEMS}
      activeId={activeId}
      onSelect={setActiveId}
      user={user}
      onSignOut={signOut}
    >
      {renderScreen(activeId)}
    </Layout>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  )
}
