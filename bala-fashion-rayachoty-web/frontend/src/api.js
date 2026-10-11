import { supabase } from './supabase'

const BASE = (import.meta.env.VITE_API_BASE_URL || 'https://bala-fashion-api.onrender.com/api').replace(/\/$/, '')

async function currentAccessToken(fallback) {
  if (!supabase || !fallback) return fallback
  const { data } = await supabase.auth.getSession()
  let session = data?.session
  if (!session) return fallback
  if (session.expires_at && session.expires_at * 1000 < Date.now() + 30_000) {
    const refreshed = await supabase.auth.refreshSession()
    if (refreshed.error) throw new Error('Your session expired. Please sign in again.')
    session = refreshed.data?.session || session
  }
  return session.access_token || fallback
}

async function request(path, options, token, retried = false) {
  const headers = new Headers(options.headers || {})
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(`${BASE}${path}`, { ...options, headers })
  const type = response.headers.get('content-type') || ''
  const data = type.includes('application/json') ? await response.json() : await response.text()

  if (response.status === 401 && token && supabase && !retried) {
    const refreshed = await supabase.auth.refreshSession()
    const newToken = refreshed.data?.session?.access_token
    if (!refreshed.error && newToken && newToken !== token) {
      return request(path, options, newToken, true)
    }
  }
  if (!response.ok) {
    const message = typeof data === 'string' ? data : data?.detail || data?.error
    if (response.status === 401) throw new Error(message || 'Your session expired. Please sign in again.')
    if (response.status === 403) throw new Error(message || 'Your account does not have permission for this action.')
    throw new Error(message || `Request failed (${response.status})`)
  }
  return data
}

export async function api(path, { token, ...options } = {}) {
  const accessToken = await currentAccessToken(token)
  return request(path, options, accessToken)
}
