const API_BASE = import.meta.env.VITE_API_URL || ''

export interface ApiError {
  message: string
  status?: number
}

export function getAuthToken(): string | null {
  return localStorage.getItem('skillsync_token')
}

export function setAuthToken(token: string | null): void {
  if (token) {
    localStorage.setItem('skillsync_token', token)
  } else {
    localStorage.removeItem('skillsync_token')
  }
}

async function apiFetch<T>(path: string, options: RequestInit = {}, requireAuth = false): Promise<T> {
  const headers = new Headers(options.headers || {})
  headers.set('Content-Type', 'application/json')

  if (requireAuth) {
    const token = getAuthToken()
    if (!token) {
      throw { message: 'Authentication required', status: 401 } as ApiError
    }
    headers.set('Authorization', `Bearer ${token}`)
  }

  if (options.body && options.body instanceof FormData) {
    headers.delete('Content-Type')
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })

  if (!res.ok) {
    const text = await res.text()
    let message = 'Request failed'
    try {
      const json = JSON.parse(text)
      message = json.detail || json.message || message
    } catch {
      message = text || message
    }
    throw { message, status: res.status } as ApiError
  }

  if (res.status === 204) {
    return undefined as T
  }

  return res.json() as Promise<T>
}

export const authService = {
  register: (name: string, email: string, password: string) =>
    apiFetch<{ access_token?: string; token_type?: string; user?: any }>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ name, email, password }),
    }),
  login: (email: string, password: string) =>
    apiFetch<{ access_token: string; user: any }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  me: () => apiFetch<{ id: string; name: string; email: string }>('/api/auth/me', {}, true),
}

export const resumeService = {
  upload: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return apiFetch<{ id: string; file_name: string; file_type: string }>('/api/resume/upload', {
      method: 'POST',
      body: formData,
    }, true)
  },
}

export const jobService = {
  analyze: (job_description: string) =>
    apiFetch<{ id: string; job_title: string; required_skills: string[] }>('/api/job/analyze', {
      method: 'POST',
      body: JSON.stringify({ job_description }),
    }, true),
}

export const analysisService = {
  list: () => apiFetch<any[]>('/api/analysis', {}, true),
  get: (id: string) => apiFetch<any>(`/api/analysis/${id}`, {}, true),
  reprocess: (id: string) => apiFetch<any>(`/api/analysis/${id}/reprocess`, { method: 'POST' }, true),
  learningPath: (id: string) => apiFetch<any>(`/api/analysis/${id}/learning-path`, {}, true),
}

export const matchService = {
  create: (resume_id: string, job_description_id: string) =>
    apiFetch<any>('/api/match', {
      method: 'POST',
      body: JSON.stringify({ resume_id, job_description_id }),
    }, true),
}

export const interviewService = {
  start: (analysis_id: string) => apiFetch<any>('/api/interview/start', {
    method: 'POST',
    body: JSON.stringify({ analysis_id }),
  }, true),
  state: (session_id: string) => apiFetch<any>(`/api/interview/${session_id}/state`, {}, true),
  report: (session_id: string) => apiFetch<any>(`/api/interview/${session_id}/report`, {}, true),
}

export const healthService = {
  check: () => apiFetch<{ status: string; database: string; gemini: string; huggingface: string }>('/api/health'),
}

export default apiFetch
