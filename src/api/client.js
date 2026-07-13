/**
 * Shared API client — task 14.3
 *
 * Features:
 * - Attaches Bearer token from AuthContext on every request.
 * - Injects a unique X-Request-ID header for server-side tracing.
 * - Transparently refreshes the access token on 401 and retries once.
 * - Normalises all error responses into ApiError instances with `.code`,
 *   `.status`, and `.details` fields so callers never parse raw objects.
 * - Exposes `api.get / .post / .patch / .delete` convenience helpers.
 * - Never logs or stores credentials; never exposes raw storage paths.
 *
 * Usage:
 *   import { createApiClient } from '../api/client'
 *   // Inside a component or hook:
 *   const api = createApiClient(authContext)
 *   const data = await api.get('/api/v1/patients/me/ehr')
 */

// ---------------------------------------------------------------------------
// Error type
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(message, code = 'unknown_error', status = 0, details = []) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.details = details
  }
}

// ---------------------------------------------------------------------------
// Request ID generator
// ---------------------------------------------------------------------------

function newRequestId() {
  // Compact 16-char hex string — readable in server logs without UUID overhead.
  return Array.from(crypto.getRandomValues(new Uint8Array(8)))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('')
}

// ---------------------------------------------------------------------------
// Response normaliser
// ---------------------------------------------------------------------------

async function parseResponse(response) {
  let body
  try {
    body = await response.json()
  } catch {
    body = {}
  }

  if (!response.ok) {
    // The backend returns { status, code, message, details } on errors.
    const msg = body?.message || body?.error?.message || `HTTP ${response.status}`
    const code = body?.code || body?.error?.code || 'http_error'
    const details = body?.details || []
    throw new ApiError(msg, code, response.status, details)
  }

  // v1 endpoints wrap in { status: 'success', data: ... }
  // Legacy endpoints return data directly.
  return body?.data !== undefined ? body.data : body
}

// ---------------------------------------------------------------------------
// Core factory
// ---------------------------------------------------------------------------

/**
 * @param {{ accessToken: string|null, refresh: () => Promise<{access_token:string}> }} auth
 */
export function createApiClient(auth) {
  const { accessToken, refresh } = auth

  async function execute(path, options = {}, retried = false) {
    const requestId = newRequestId()
    const isMultipart = typeof FormData !== 'undefined' && options.body instanceof FormData
    const headers = {
      'X-Request-ID': requestId,
      ...(options.body && !isMultipart ? { 'Content-Type': 'application/json' } : {}),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      // A retry supplies the refreshed token explicitly. Keep caller headers
      // last so the stale token captured by this client cannot overwrite it.
      ...options.headers,
    }

    const response = await fetch(path, {
      ...options,
      credentials: 'include',
      headers,
    })

    // Single transparent retry after token refresh on 401.
    if (response.status === 401 && !retried && accessToken) {
      try {
        const identity = await refresh()
        return execute(path, {
          ...options,
          headers: {
            ...options.headers,
            Authorization: `Bearer ${identity.access_token}`,
          },
        }, true)
      } catch {
        throw new ApiError('Session expired. Please sign in again.', 'session_expired', 401)
      }
    }

    return parseResponse(response)
  }

  return {
    /** GET request — query params passed as a plain object. */
    get(path, params = {}, options = {}) {
      const url = Object.keys(params).length
        ? `${path}?${new URLSearchParams(params)}`
        : path
      return execute(url, { ...options, method: 'GET' })
    },

    /** POST request — body is JSON-serialised. */
    post(path, body = null, options = {}) {
      return execute(path, {
        ...options,
        method: 'POST',
        body: body !== null ? JSON.stringify(body) : undefined,
      })
    },

    /** PATCH request. */
    patch(path, body = null, options = {}) {
      return execute(path, {
        ...options,
        method: 'PATCH',
        body: body !== null ? JSON.stringify(body) : undefined,
      })
    },

    /** DELETE request. */
    delete(path, options = {}) {
      return execute(path, { ...options, method: 'DELETE' })
    },

    /**
     * Multipart form-data upload (documents).
     * Pass a FormData object; Content-Type is set automatically.
     */
    upload(path, formData, options = {}) {
      return execute(path, {
        ...options,
        method: 'POST',
        body: formData,
        // Do NOT set Content-Type — fetch sets the correct multipart boundary.
      })
    },
  }
}

// ---------------------------------------------------------------------------
// Convenience hook-friendly wrapper
// ---------------------------------------------------------------------------

/**
 * Returns a stable api client bound to the current auth context.
 * Import useApiClient in components instead of createApiClient directly.
 */
import { useCallback } from 'react'
import { useAuth } from '../auth/authState'

export function useApiClient() {
  const auth = useAuth()
  // Re-create only when the access token changes.
  return useCallback(
    (path, options) => createApiClient(auth).get(path, {}, options),
    [auth.accessToken] // eslint-disable-line react-hooks/exhaustive-deps
  )
}
