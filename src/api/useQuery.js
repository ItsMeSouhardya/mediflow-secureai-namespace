/**
 * Lightweight query / cache hook — task 14.4
 *
 * Features:
 *  - Loading, error, and data states out of the box.
 *  - In-memory cache keyed by `key` string with configurable stale time.
 *  - Manual `refetch()` and `invalidate(key)` for post-mutation refresh.
 *  - `enabled` flag to defer fetching until prerequisites are ready.
 *  - SSE helper `useStream(url, onMessage)` for realtime queue feed (13.6).
 *
 * Usage:
 *   const { data, loading, error, refetch } = useQuery(
 *     'patient-ehr',
 *     () => api.get('/api/v1/patients/me/ehr'),
 *     { staleMs: 30_000 }
 *   )
 */

import { useCallback, useEffect, useRef, useState } from 'react'

// ---------------------------------------------------------------------------
// Simple module-level cache (survives re-renders, cleared on invalidation)
// ---------------------------------------------------------------------------

const _cache = new Map()          // key → { data, fetchedAt }
const _listeners = new Map()      // key → Set of () => void

function _notify(key) {
  _listeners.get(key)?.forEach(fn => fn())
}

/** Programmatically invalidate a cache entry from outside a component. */
export function invalidateQuery(key) {
  _cache.delete(key)
  _notify(key)
}

/** Invalidate all entries whose key starts with a prefix. */
export function invalidatePrefix(prefix) {
  for (const key of _cache.keys()) {
    if (key.startsWith(prefix)) {
      _cache.delete(key)
      _notify(key)
    }
  }
}

// ---------------------------------------------------------------------------
// Core hook
// ---------------------------------------------------------------------------

/**
 * @param {string|null} key        Cache key. null → fetch disabled.
 * @param {() => Promise<any>} fn  Async function that returns data.
 * @param {object} options
 * @param {number}  [options.staleMs=60000]   Cache TTL in milliseconds.
 * @param {boolean} [options.enabled=true]    Defer fetch when false.
 * @param {any}     [options.initialData]     Value to use before first fetch.
 */
export function useQuery(key, fn, { staleMs = 60_000, enabled = true, initialData } = {}) {
  const [state, setState] = useState({
    data: initialData ?? null,
    loading: Boolean(key && enabled),
    error: null,
  })
  const fnRef = useRef(fn)
  fnRef.current = fn

  const load = useCallback(async () => {
    if (!key || !enabled) return

    // Serve from cache if still fresh.
    const cached = _cache.get(key)
    if (cached && Date.now() - cached.fetchedAt < staleMs) {
      setState({ data: cached.data, loading: false, error: null })
      return
    }

    setState(s => ({ ...s, loading: true, error: null }))
    try {
      const data = await fnRef.current()
      _cache.set(key, { data, fetchedAt: Date.now() })
      setState({ data, loading: false, error: null })
    } catch (err) {
      setState(s => ({ ...s, loading: false, error: err }))
    }
  }, [key, enabled, staleMs])

  // Subscribe to external invalidation signals.
  useEffect(() => {
    if (!key) return
    if (!_listeners.has(key)) _listeners.set(key, new Set())
    _listeners.get(key).add(load)
    return () => _listeners.get(key)?.delete(load)
  }, [key, load])

  // Fetch on mount and when key / enabled changes.
  useEffect(() => { load() }, [load])

  const refetch = useCallback(() => {
    if (key) _cache.delete(key)
    load()
  }, [key, load])

  return { ...state, refetch }
}

// ---------------------------------------------------------------------------
// Mutation helper — fire-and-forget with automatic cache invalidation
// ---------------------------------------------------------------------------

/**
 * Returns { mutate, loading, error } for POST/PATCH/DELETE operations.
 *
 * @param {(payload: any) => Promise<any>} fn
 * @param {{ invalidates?: string[] }} options  Cache keys to invalidate on success.
 */
export function useMutation(fn, { invalidates = [] } = {}) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const fnRef = useRef(fn)
  fnRef.current = fn

  const mutate = useCallback(async (payload) => {
    setLoading(true)
    setError(null)
    try {
      const result = await fnRef.current(payload)
      invalidates.forEach(invalidateQuery)
      return result
    } catch (err) {
      setError(err)
      throw err
    } finally {
      setLoading(false)
    }
  }, [invalidates.join(',')]) // eslint-disable-line react-hooks/exhaustive-deps

  return { mutate, loading, error }
}

// ---------------------------------------------------------------------------
// SSE helper — wraps EventSource for realtime queue/monitoring streams (13.6)
// ---------------------------------------------------------------------------

/**
 * Opens an SSE connection and calls `onMessage` with parsed JSON on each event.
 * Automatically closes on component unmount.
 *
 * @param {string|null} url         SSE endpoint URL. null → disabled.
 * @param {(data: any) => void} onMessage
 * @param {(err: Event) => void} [onError]
 */
export function useStream(url, onMessage, onError) {
  const onMessageRef = useRef(onMessage)
  const onErrorRef = useRef(onError)
  onMessageRef.current = onMessage
  onErrorRef.current = onError

  useEffect(() => {
    if (!url) return
    const es = new EventSource(url)
    es.onmessage = (event) => {
      try {
        onMessageRef.current(JSON.parse(event.data))
      } catch {
        // Unparseable frame — ignore silently.
      }
    }
    es.onerror = (err) => {
      onErrorRef.current?.(err)
    }
    return () => es.close()
  }, [url])
}
