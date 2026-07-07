import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import RootRedirect from './components/RootRedirect'
import TabLayout from './components/TabLayout'
import Login from './pages/Login'
import Home from './pages/Home'
import Rank from './pages/Rank'
import My from './pages/My'
import WorkDetail from './pages/WorkDetail'
import Admin from './pages/admin/Admin'

function LoginRoute() {
  const { auth } = useAuth()
  if (auth) {
    return <Navigate to={auth.role === 'admin' ? '/admin' : '/home'} replace />
  }
  return <Login />
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginRoute />} />
          <Route path="/" element={<RootRedirect />} />

          <Route
            path="/"
            element={
              <ProtectedRoute role="user">
                <TabLayout />
              </ProtectedRoute>
            }
          >
            <Route path="home" element={<Home />} />
            <Route path="rank" element={<Rank />} />
            <Route path="my" element={<My />} />
          </Route>

          <Route
            path="/works/:id"
            element={
              <ProtectedRoute role="user">
                <WorkDetail />
              </ProtectedRoute>
            }
          />

          <Route
            path="/admin"
            element={
              <ProtectedRoute role="admin">
                <Admin />
              </ProtectedRoute>
            }
          />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
