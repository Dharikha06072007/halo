import apiFetch from './api'

export const startInterview = async (analysisId: string) => {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 45000)
  try {
    return await apiFetch<any>('/api/interview/start', {
      method: 'POST',
      body: JSON.stringify({ analysis_id: analysisId }),
      signal: controller.signal,
    }, true)
  } catch (error: any) {
    if (error?.name === 'AbortError') {
      throw { message: 'Interview preparation took too long. Please retry.', status: 504 }
    }
    throw error
  } finally {
    window.clearTimeout(timeout)
  }
}

export const answerQuestion = (payload: { session_id: string; question_id: string; answer_submission_id: string; transcript: string }) => apiFetch<any>('/api/interview/answer', {
  method: 'POST',
  body: JSON.stringify(payload),
}, true)

export const endInterview = (sessionId: string) => apiFetch<any>('/api/interview/end', {
  method: 'POST',
  body: JSON.stringify({ session_id: sessionId }),
}, true)

export const recordIntegrityEvent = (payload: { session_id: string; question_id?: string | null; event_type: string; metadata?: Record<string, unknown> }) => apiFetch<any>('/api/interview/integrity-event', {
  method: 'POST',
  body: JSON.stringify(payload),
}, true)

export const getInterviewState = (sessionId: string) => apiFetch<any>(`/api/interview/${sessionId}/state`, {}, true)
export const getInterviewReport = (sessionId: string) => apiFetch<any>(`/api/interview/${sessionId}/report`, {}, true)
export const getInterviewHistory = () => apiFetch<any[]>('/api/interview/history', {}, true)

export default { startInterview, answerQuestion, endInterview, recordIntegrityEvent, getInterviewState, getInterviewReport, getInterviewHistory }