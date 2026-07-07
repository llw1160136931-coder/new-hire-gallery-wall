import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function RootRedirect() {
  const { auth } = useAuth()

  if (!auth) return <Navigate to="/login" replace />
  if (auth.role === 'admin') return <Navigate to="/admin" replace />
  return <Navigate to="/home" replace />
}
