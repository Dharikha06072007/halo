import apiFetch from './api'

export const startInterview = (analysisId: string) => apiFetch<any>('/api/interview/start', {
  method: 'POST',
  body: JSON.stringify({ analysis_id: analysisId }),
}, true)

export const answerQuestion = (payload: { session_id: string; question_id: string; answer_submission_id: string; transcript: string }) => apiFetch<any>('/api/interview/answer', {
  method: 'POST',
  body: JSON.stringify(payload),
}, true)

export const endInterview = (sessionId: string) => apiFetch<any>('/api/interview/end', {
  method: 'POST',
  body: JSON.stringify({ session_id: sessionId }),
}, true)

export const getInterviewState = (sessionId: string) => apiFetch<any>(`/api/interview/${sessionId}/state`, {}, true)
export const getInterviewReport = (sessionId: string) => apiFetch<any>(`/api/interview/${sessionId}/report`, {}, true)

export default { startInterview, answerQuestion, endInterview, getInterviewState, getInterviewReport }