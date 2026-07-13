import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AuthContext } from './authState'

async function readResponse(response) {
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const error = new Error(body.error?.message || 'Request failed')
    error.code = body.error?.code
    error.status = response.status
    throw error
  }
  return body.data !== undefined ? body.data : body
}

export function AuthProvider({ children }) {
  const [accessToken, setAccessToken] = useState(null)
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)
  const [sessionExpired, setSessionExpired] = useState(false)
  const refreshPromiseRef = useRef(null)

  const applyIdentity = useCallback((identity) => {
    setAccessToken(identity.access_token)
    setUser(identity.user)
    setSessionExpired(false)
    return identity
  }, [])

  const updateUser = useCallback((nextUser) => {
    setUser(nextUser)
    return nextUser
  }, [])

  const refresh = useCallback(() => {
    if (!refreshPromiseRef.current) {
      refreshPromiseRef.current = fetch('/api/v1/auth/refresh', { method: 'POST', credentials: 'include' })
        .then(readResponse)
        .then(applyIdentity)
        .finally(() => { refreshPromiseRef.current = null })
    }
    return refreshPromiseRef.current
  }, [applyIdentity])

  useEffect(() => {
    refresh()
      .catch(() => {
        setAccessToken(null)
        setUser(null)
      })
      .finally(() => setReady(true))
  }, [refresh])

  const login = useCallback(async (identifier, password) => {
    const response = await fetch('/api/v1/auth/login', {
      method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ identifier, password }),
    })
    return applyIdentity(await readResponse(response))
  }, [applyIdentity])

  const register = useCallback(async (payload) => {
    const response = await fetch('/api/v1/auth/register', {
      method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    return applyIdentity(await readResponse(response))
  }, [applyIdentity])

  const logout = useCallback(async () => {
    if (accessToken) {
      await fetch('/api/v1/auth/logout', {
        method: 'POST', credentials: 'include', headers: { Authorization: `Bearer ${accessToken}` },
      }).catch(() => null)
    }
    setAccessToken(null)
    setUser(null)
    setSessionExpired(false)
  }, [accessToken])

  const request = useCallback(async (path, options = {}) => {
    const execute = (token) => fetch(path, {
      ...options,
      credentials: 'include',
      headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers, ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    })
    let response = await execute(accessToken)
    if (response.status === 401 && accessToken) {
      try {
        const identity = await refresh()
        response = await execute(identity.access_token)
      } catch {
        setAccessToken(null)
        setUser(null)
        setSessionExpired(true)
      }
    }
    return readResponse(response)
  }, [accessToken, refresh])

  const value = useMemo(() => ({ ready, user, accessToken, sessionExpired, login, register, logout, refresh, request, updateUser }), [ready, user, accessToken, sessionExpired, login, register, logout, refresh, request, updateUser])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
