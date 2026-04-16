import axios from 'axios'
import type { Workflow, WorkflowGraph } from '../types/workflow'
import type { Provider, ProviderCreate, ProviderUpdate, ProviderTypeInfo } from '../types/provider'
import type { AgentSession } from '../types/agent'

const api = axios.create({ baseURL: '/api' })

export const workflowApi = {
  list: () => api.get<Workflow[]>('/workflows').then(r => r.data),
  get: (id: string) => api.get<Workflow>(`/workflows/${id}`).then(r => r.data),
  create: (data: { name: string; description?: string; graph: WorkflowGraph }) =>
    api.post<Workflow>('/workflows', data).then(r => r.data),
  update: (id: string, data: Partial<Workflow>) =>
    api.put<Workflow>(`/workflows/${id}`, data).then(r => r.data),
  delete: (id: string) => api.delete(`/workflows/${id}`),
  run: (id: string, payload: { input?: string; inputs?: Record<string, unknown> }) =>
    api.post<{ run_id: string; status: string; output: unknown }>(`/workflows/${id}/run`, payload).then(r => r.data),
}

export const providerApi = {
  list: (category?: string) => api.get<Provider[]>('/providers', { params: category ? { category } : undefined }).then(r => r.data),
  create: (data: ProviderCreate) => api.post<Provider>('/providers', data).then(r => r.data),
  get: (id: number) => api.get<Provider>(`/providers/${id}`).then(r => r.data),
  update: (id: number, data: ProviderUpdate) => api.put<Provider>(`/providers/${id}`, data).then(r => r.data),
  delete: (id: number) => api.delete(`/providers/${id}`),
  test: (id: number) => api.post<{status: string}>(`/providers/${id}/test`).then(r => r.data),
  models: (id: number, refresh?: boolean) => api.get<{provider_id: number, models: string[], cached_at?: string, selected_models?: string[]}>(`/providers/${id}/models`, { params: { refresh } }).then(r => r.data),
  types: () => api.get<ProviderTypeInfo[]>('/providers/types').then(r => r.data),
}

export const knowledgeApi = {
  create: (data: { name: string; description?: string }) =>
    api.post('/knowledge-bases', data).then(r => r.data),
  get: (id: string) => api.get(`/knowledge-bases/${id}`).then(r => r.data),
  upload: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post(`/knowledge-bases/${id}/upload`, form).then(r => r.data)
  },
  query: (id: string, query: string, topK = 3) =>
    api.post(`/knowledge-bases/${id}/query`, { query, top_k: topK }).then(r => r.data),
}

export const agentApi = {
  createSession: (goal: string) =>
    api.post<{ session_id: string }>('/agent/sessions', { goal }).then(r => r.data),
  getSession: (id: string) =>
    api.get<AgentSession>(`/agent/sessions/${id}`).then(r => r.data),
  answerSession: (id: string, answer: string) =>
    api.post<{ status: string }>(`/agent/sessions/${id}/answer`, { answer }).then(r => r.data),
  skipSession: (id: string) =>
    api.post<{ status: string }>(`/agent/sessions/${id}/skip`).then(r => r.data),
  applySession: (id: string) =>
    api.post<{ workflow_id: string }>(`/agent/sessions/${id}/apply`).then(r => r.data),
  eventsUrl: (id: string) => `/api/agent/sessions/${id}/events`,
}
