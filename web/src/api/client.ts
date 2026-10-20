// Small fetch wrapper for the Python service. The web app calls /api on its own address;
// Vite forwards it to the service (see vite.config.ts), so there is no CORS to configure.

export class ApiError extends Error {
  /** null when the service could not be reached. */
  constructor(
    public status: number | null,
    message: string,
  ) {
    super(message)
  }

  get isUnauthorized() {
    return this.status === 401
  }
}

let token: string | null = localStorage.getItem('pos.token')
let onUnauthorized: () => void = () => {}

export function setToken(value: string | null) {
  token = value
  if (value) localStorage.setItem('pos.token', value)
  else localStorage.removeItem('pos.token')
}

export function onSessionExpired(handler: () => void) {
  onUnauthorized = handler
}

type Query = Record<string, string | number | boolean | null | undefined>

function url(path: string, query?: Query) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== null && value !== undefined && value !== '') params.set(key, String(value))
  }
  const qs = params.toString()
  return `/api${path}${qs ? `?${qs}` : ''}`
}

async function errorMessage(response: Response) {
  try {
    const body = await response.json()
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail)) {
      return body.detail.map((e: { loc: unknown[]; msg: string }) => `${e.loc.at(-1)}: ${e.msg}`).join('\n')
    }
  } catch {
    // not JSON
  }
  return `Service error ${response.status}`
}

async function send(method: string, path: string, options: { query?: Query; body?: unknown; form?: FormData } = {}) {
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'

  let response: Response
  try {
    response = await fetch(url(path, options.query), {
      method,
      headers,
      body: options.form ?? (options.body !== undefined ? JSON.stringify(options.body) : undefined),
    })
  } catch {
    throw new ApiError(null, 'Cannot reach the POS service. Is it running?')
  }
  if (!response.ok) {
    const error = new ApiError(response.status, await errorMessage(response))
    if (error.isUnauthorized && token) onUnauthorized()
    throw error
  }
  return response
}

async function json<T>(response: Response): Promise<T> {
  const text = await response.text()
  return (text ? JSON.parse(text) : null) as T
}

export const api = {
  get: async <T>(path: string, query?: Query) => json<T>(await send('GET', path, { query })),
  text: async (path: string, query?: Query) => (await send('GET', path, { query })).text(),
  blob: async (path: string, query?: Query) => (await send('GET', path, { query })).blob(),
  post: async <T>(path: string, body: unknown = {}) => json<T>(await send('POST', path, { body })),
  put: async <T>(path: string, body: unknown) => json<T>(await send('PUT', path, { body })),
  patch: async <T>(path: string, body: unknown) => json<T>(await send('PATCH', path, { body })),
  delete: async (path: string) => {
    await send('DELETE', path)
  },
  upload: async <T>(path: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return json<T>(await send('POST', path, { form }))
  },
}
