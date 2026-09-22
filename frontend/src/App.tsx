import { FormEvent, useEffect, useState } from 'react'
import { analysisService, authService, healthService, jobService, resumeService, getAuthToken, setAuthToken } from './services/api'

export default function App() {
  const [isLogin, setIsLogin] = useState(true)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [token, setToken] = useState<string | null>(getAuthToken())
  const [user, setUser] = useState<{ id: string; name: string; email: string } | null>(null)
  const [resumeFile, setResumeFile] = useState<File | null>(null)
  const [jobText, setJobText] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [analyses, setAnalyses] = useState<any[]>([])

  const loadUser = async () => {
    if (!token) return
    try {
      const data = await authService.me()
      setUser(data)
    } catch (err: any) {
      setError(err.message || 'Session invalid')
      setToken(null)
      setAuthToken(null)
    }
  }

  const loadAnalyses = async () => {
    if (!token) return
    try {
      const data = await analysisService.list()
      setAnalyses(data)
    } catch (err: any) {
      setAnalyses([])
      setError(err.message || 'Could not load analyses')
    }
  }

  useEffect(() => {
    if (token) {
      loadUser()
      loadAnalyses()
    }
  }, [token])

  const handleAuth = async (event: FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setError('')
    setMessage('')

    try {
      if (isLogin) {
        const res = await authService.login(email, password)
        setAuthToken(res.access_token)
        setToken(res.access_token)
        setUser(res.user)
        setMessage('Logged in successfully.')
      } else {
        await authService.register(name, email, password)
        setMessage('Registration successful. Please log in.')
        setIsLogin(true)
      }
    } catch (err: any) {
      setError(err.message || 'Authentication failed')
    } finally {
      setLoading(false)
    }
  }

  const handleResumeUpload = async () => {
    if (!resumeFile) {
      setError('Choose a PDF or DOCX resume first.')
      return
    }
    setLoading(true)
    setError('')
    setMessage('')
    try {
      await resumeService.upload(resumeFile)
      setMessage('Resume uploaded and analyzed.')
    } catch (err: any) {
      setError(err.message || 'Resume upload failed')
    } finally {
      setLoading(false)
    }
  }

  const handleAnalyzeJob = async () => {
    if (!jobText.trim()) {
      setError('Paste a job description first.')
      return
    }
    setLoading(true)
    setError('')
    setMessage('')
    try {
      const res = await jobService.analyze(jobText)
      setMessage(`Job analyzed: ${res.job_title || 'Role detected'}`)
    } catch (err: any) {
      setError(err.message || 'Job analysis failed')
    } finally {
      setLoading(false)
    }
  }

  const logout = () => {
    setAuthToken(null)
    setToken(null)
    setUser(null)
    setAnalyses([])
  }

  const backendStatus = async () => {
    try {
      const status = await healthService.check()
      setMessage(`Backend: ${status.status} | DB: ${status.database}`)
    } catch (err: any) {
      setError(err.message || 'Health check failed')
    }
  }

  if (!token) {
    return (
      <div className="auth-shell">
        <div className="auth-card">
          <h1>SkillSync AI</h1>
          <div className="switch-row">
            <button className={isLogin ? 'active' : ''} onClick={() => setIsLogin(true)}>Login</button>
            <button className={!isLogin ? 'active' : ''} onClick={() => setIsLogin(false)}>Register</button>
          </div>

          <form onSubmit={handleAuth} className="auth-form">
            {!isLogin && (
              <input
                placeholder="Full name"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            )}
            <input
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <button type="submit" disabled={loading}>{loading ? 'Please wait...' : isLogin ? 'Login' : 'Register'}</button>
          </form>

          {message && <div className="success-box">{message}</div>}
          {error && <div className="error-box">{error}</div>}
        </div>
      </div>
    )
  }

  return (
    <div className="dashboard-shell">
      <header className="topbar">
        <div>
          <h2>SkillSync AI</h2>
          <small>{user?.email}</small>
        </div>
        <button onClick={logout}>Logout</button>
      </header>

      <div className="actions-grid">
        <div className="panel">
          <h3>Resume Upload</h3>
          <input type="file" accept=".pdf,.docx" onChange={(e) => setResumeFile(e.target.files?.[0] || null)} />
          <button onClick={handleResumeUpload} disabled={loading}>Upload Resume</button>
        </div>

        <div className="panel">
          <h3>Job Description</h3>
          <textarea value={jobText} onChange={(e) => setJobText(e.target.value)} placeholder="Paste the target job description..." />
          <button onClick={handleAnalyzeJob} disabled={loading}>Analyze Job</button>
        </div>
      </div>

      <div className="panel">
        <h3>System status</h3>
        <button onClick={backendStatus}>Check backend health</button>
      </div>

      <div className="panel">
        <h3>Analyses</h3>
        {analyses.length === 0 ? <p>No analyses yet.</p> : analyses.map((item) => (
          <div key={item.id} className="analysis-item">
            <strong>{item.overall_match_score ?? 0}% match</strong>
            <div>{item.matched_skills?.join(', ') || 'No matched skills yet.'}</div>
          </div>
        ))}
      </div>

      {message && <div className="success-box">{message}</div>}
      {error && <div className="error-box">{error}</div>}
    </div>
  )
}
