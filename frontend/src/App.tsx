import { useState } from 'react'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { Layout } from './components/Layout'
import { NAV_ITEMS } from './config/navigation'
import { Imports } from './pages/Imports'
import { Login } from './pages/Login'
import { Overview } from './pages/Overview'
import { PlaceholderPage } from './pages/Placeholder'

function SessionLoading() {
  return (
    <div className="auth-screen">
      <p className="auth-card__subtitle" role="status">
        Loading your session…
      </p>
    </div>
  )
}

function renderScreen(activeId: string, title: string) {
  switch (activeId) {
    case 'overview':
      return <Overview />
    case 'imports':
      return <Imports />
    default:
      return <PlaceholderPage title={title} />
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

  const activeItem = NAV_ITEMS.find((item) => item.id === activeId) ?? NAV_ITEMS[0]

  return (
    <Layout
      items={NAV_ITEMS}
      activeId={activeId}
      onSelect={setActiveId}
      user={user}
      onSignOut={signOut}
    >
      {renderScreen(activeId, activeItem.label)}
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
