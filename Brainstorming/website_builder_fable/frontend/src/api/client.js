// OWNED BY: scaffold (infrastructure). Module agents READ this file, never edit it.
// Small fetch wrapper. All paths are relative /api/... URLs (Vite proxy handles them).

export class ApiError extends Error {
  constructor(status, detail) {
    const message = typeof detail === 'string' ? detail : 'Request failed'
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function handle(res) {
  if (res.status === 204) return null
  const contentType = res.headers.get('content-type') || ''
  const body = contentType.includes('application/json') ? await res.json() : await res.text()
  if (!res.ok) {
    const detail = body && typeof body === 'object' ? body.detail : body
    throw new ApiError(res.status, detail)
  }
  return body
}

export function apiGet(path) {
  return fetch(path).then(handle)
}

export function apiPost(path, data) {
  return fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data ?? {})
  }).then(handle)
}

export function apiPut(path, data) {
  return fetch(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data ?? {})
  }).then(handle)
}

export function apiDelete(path) {
  return fetch(path, { method: 'DELETE' }).then(handle)
}

// Multipart upload; field name is "file" per the API contract.
export function uploadFile(path, file) {
  const form = new FormData()
  form.append('file', file)
  return fetch(path, { method: 'POST', body: form }).then(handle)
}
