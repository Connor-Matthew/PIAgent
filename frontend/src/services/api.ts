import axios from 'axios'
import type { Workflow, WorkflowGraph } from '../types/workflow'
import type { Provider, ProviderCreate, ProviderUpdate, ProviderTypeInfo } from '../types/provider'
import type { AgentAutoRunStreamEvent, AgentSession } from '../types/agent'

const api = axios.create({ baseURL: '/api' })

function parseSSEBlock(block: string) {
  const lines = block.split(/\r?\n/)
  let eventName = ''
  const dataLines: string[] = []

  for (const rawLine of lines) {
    const line = rawLine.trimEnd()
    if (!line || line.startsWith(':')) continue
    if (line.startsWith('event:')) {
      eventName = line.slice('event:'.length).trim()
      continue
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).trimStart())
    }
  }

  if (dataLines.length === 0) return null

  const payload = JSON.parse(dataLines.join('\n')) as Record<string, unknown>
  if (!payload.type && eventName) {
    payload.type = eventName
  }
  return payload as unknown as AgentAutoRunStreamEvent
}

async function streamAgentEvents(
  goal: string,
  onEvent: (event: AgentAutoRunStreamEvent) => void
) {
  const response = await fetch('/api/harness/auto-run', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({ goal }),
  })

  if (!response.ok) {
    const text = await response.text()
    let detail = ''
    try {
      const parsed = JSON.parse(text) as { detail?: string }
      detail = parsed.detail || ''
    } catch {
      detail = ''
    }
    throw new Error(detail || text || 'Agent auto-run failed')
  }

  if (!response.body) {
    throw new Error('Agent auto-run stream is unavailable')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })

    let boundaryIndex = buffer.indexOf('\n\n')
    while (boundaryIndex >= 0) {
      const block = buffer.slice(0, boundaryIndex)
      buffer = buffer.slice(boundaryIndex + 2)
      const parsed = parseSSEBlock(block)
      if (parsed) {
        onEvent(parsed)
      }
      boundaryIndex = buffer.indexOf('\n\n')
    }

    if (done) {
      break
    }
  }

  const trailing = parseSSEBlock(buffer)
  if (trailing) {
    onEvent(trailing)
  }
}

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
  autoRun: (goal: string, onEvent: (event: AgentAutoRunStreamEvent) => void) =>
    streamAgentEvents(goal, onEvent),
  eventsUrl: (id: string) => `/api/agent/sessions/${id}/events`,
}
