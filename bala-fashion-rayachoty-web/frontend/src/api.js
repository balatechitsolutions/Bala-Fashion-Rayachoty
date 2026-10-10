const BASE = (import.meta.env.VITE_API_BASE_URL || 'https://bala-fashion-api.onrender.com/api').replace(/\/$/, '')
export async function api(path, { token, ...options } = {}) {
  const headers = new Headers(options.headers || {})
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(`${BASE}${path}`, { ...options, headers })
  const type = response.headers.get('content-type') || ''
  const data = type.includes('application/json') ? await response.json() : await response.text()
  if (!response.ok) throw new Error(data?.detail || data?.error || `Request failed (${response.status})`)
  return data
}
