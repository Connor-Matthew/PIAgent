import axios from 'axios'
import type { HarnessSession } from '../types/harness'

const api = axios.create({ baseURL: '/api' })

export const harnessApi = {
  createSession: (goal: string, workflowId?: string | null) =>
    api.post<{ session_id: string; status: string }>('/harness/sessions', { goal, workflow_id: workflowId }).then(r => r.data),

  getSession: (id: string) =>
    api.get<HarnessSession>(`/harness/sessions/${id}`).then(r => r.data),

  resumeSession: (id: string, questionId: string, answer: string) =>
    api.post<{ status: string; session_id: string }>(`/harness/sessions/${id}/resume`, { question_id: questionId, answer }).then(r => r.data),

  applySession: (id: string) =>
    api.post<{ workflow_id: string; graph: Record<string, unknown> }>(`/harness/sessions/${id}/apply`).then(r => r.data),

  abortSession: (id: string) =>
    api.post<{ status: string; session_id: string }>(`/harness/sessions/${id}/abort`).then(r => r.data),

  streamEvents: (id: string) => {
    return new EventSource(`/api/harness/sessions/${id}/events`)
  },
}
