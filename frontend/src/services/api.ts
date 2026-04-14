import axios from 'axios'
import type { Workflow, WorkflowGraph } from '../types/workflow'

const api = axios.create({ baseURL: '/api' })

export const workflowApi = {
  list: () => api.get<Workflow[]>('/workflows').then(r => r.data),
  get: (id: string) => api.get<Workflow>(`/workflows/${id}`).then(r => r.data),
  create: (data: { name: string; description?: string; graph: WorkflowGraph }) =>
    api.post<Workflow>('/workflows', data).then(r => r.data),
  update: (id: string, data: Partial<Workflow>) =>
    api.put<Workflow>(`/workflows/${id}`, data).then(r => r.data),
  delete: (id: string) => api.delete(`/workflows/${id}`),
  run: (id: string, input: string) =>
    api.post<{ run_id: string; status: string; output: unknown }>(`/workflows/${id}/run`, { input }).then(r => r.data),
}

export const providerApi = {
  list: () => api.get('/providers').then(r => r.data),
  models: (name: string) => api.get(`/providers/${name}/models`).then(r => r.data),
  test: (name: string) => api.post(`/providers/${name}/test`).then(r => r.data),
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
