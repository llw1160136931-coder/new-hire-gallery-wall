import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import { loginAdmin, loginUser } from '../api/client'
import { verifyAdmin, verifyUser } from '../api/userMock'

/** @typedef {'user' | 'admin'} UserRole */

/**
 * @typedef {Object} AuthUser
 * @property {number} id
 * @property {string} name
 */

/**
 * @typedef {Object} AuthState
 * @property {UserRole} role
 * @property {AuthUser} user
 */

const AUTH_KEY = 'display-wall-auth'

/** @returns {AuthState | null} */
function loadAuth() {
  try {
    const stored = sessionStorage.getItem(AUTH_KEY)
    if (!stored) return null
    const auth = JSON.parse(stored)
    if (auth.role === 'user' && !verifyUser(auth.user.id, auth.user.name)) return null
    if (auth.role === 'admin' && !verifyAdmin(auth.user.id, auth.user.name)) return null
    return auth
  } catch {
    /* ignore */
  }
  return null
}

/** @param {AuthState | null} auth */
function saveAuth(auth) {
  if (auth) {
    sessionStorage.setItem(AUTH_KEY, JSON.stringify(auth))
  } else {
    sessionStorage.removeItem(AUTH_KEY)
  }
}

const AuthContext = createContext(/** @type {import('react').Context<{
  auth: AuthState | null
  loginAsUser: (name: string) => Promise<void>
  loginAsAdmin: (name: string) => Promise<void>
  logout: () => void
} | null>} */ (null))

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState(loadAuth)

  const loginAsUser = useCallback(async (name) => {
    const user = await loginUser(name)
    const next = { role: /** @type {UserRole} */ ('user'), user }
    saveAuth(next)
    setAuth(next)
  }, [])

  const loginAsAdmin = useCallback(async (name) => {
    const admin = await loginAdmin(name)
    const next = { role: /** @type {UserRole} */ ('admin'), user: admin }
    saveAuth(next)
    setAuth(next)
  }, [])

  const logout = useCallback(() => {
    saveAuth(null)
    setAuth(null)
  }, [])

  const value = useMemo(
    () => ({ auth, loginAsUser, loginAsAdmin, logout }),
    [auth, loginAsUser, loginAsAdmin, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

/** @returns {AuthUser} */
export function useUser() {
  const { auth } = useAuth()
  if (!auth) throw new Error('Not logged in')
  return auth.user
}
