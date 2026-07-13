import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './authState'

export default function ProtectedRoute({ roles = [], children }) {
  const { ready, user, sessionExpired } = useAuth()
  const location = useLocation()
  if (!ready) return <div className="min-h-screen pt-32 text-center text-slate-600">Restoring your secure session…</div>
  if (!user) return <Navigate to={sessionExpired ? '/session-expired' : '/login'} state={{ from: location }} replace />
  if (roles.length && !user.roles?.some((role) => roles.includes(role))) return <Navigate to="/unauthorized" replace />
  return children
}
