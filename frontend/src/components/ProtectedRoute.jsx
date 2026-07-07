import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

/**
 * @param {Object} props
 * @param {'user' | 'admin'} props.role
 * @param {import('react').ReactNode} props.children
 */
export default function ProtectedRoute({ role, children }) {
  const { auth } = useAuth()

  if (!auth) {
    return <Navigate to="/login" replace />
  }

  if (auth.role !== role) {
    return <Navigate to={auth.role === 'admin' ? '/admin' : '/home'} replace />
  }

  return children
}
