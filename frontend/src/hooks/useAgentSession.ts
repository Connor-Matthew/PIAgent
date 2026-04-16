import { startTransition, useCallback, useEffect, useRef } from 'react'

import { agentApi, workflowApi } from '../services/api'
import { useAgentStore } from '../stores/agentStore'
import { useWorkflowStore } from '../stores/workflowStore'
import type { AgentSessionEvent } from '../types/agent'
import { getApiErrorMessage } from '../utils/apiErrors'

const STREAMED_EVENT_TYPES: AgentSessionEvent['type'][] = [
  'agent_session_started',
  'clarify_question',
  'clarify_completed',
  'recipe_generating',
  'recipe_repairing',
  'recipe_fallback',
  'plan_ready',
  'agent_error',
]

export function useAgentSession() {
  const eventSourceRef = useRef<EventSource | null>(null)
  const refreshTimerRef = useRef<number | null>(null)

  const {
    sessionId,
    session,
    events,
    isBusy,
    isStreaming,
    error,
    setSessionId,
    setSession,
    appendEvent,
    setBusy,
    setStreaming,
    setError,
    reset,
  } = useAgentStore()

  const { setDraftWorkflow, setWorkflow } = useWorkflowStore()

  const refreshSession = useCallback(async (id = sessionId) => {
    if (!id) return null
    const nextSession = await agentApi.getSession(id)
    startTransition(() => {
      setSession(nextSession)
    })
    return nextSession
  }, [sessionId, setSession])

  const scheduleRefresh = useCallback(() => {
    if (refreshTimerRef.current !== null) {
      window.clearTimeout(refreshTimerRef.current)
    }
    refreshTimerRef.current = window.setTimeout(() => {
      void refreshSession()
    }, 80)
  }, [refreshSession])

  const connect = useCallback((id: string) => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
    }

    const es = new EventSource(agentApi.eventsUrl(id))
    eventSourceRef.current = es
    setStreaming(true)

    for (const eventType of STREAMED_EVENT_TYPES) {
      es.addEventListener(eventType, (event) => {
        const payload = JSON.parse(event.data) as AgentSessionEvent
        appendEvent(payload)
        scheduleRefresh()
      })
    }

    es.onerror = () => {
      setStreaming(false)
      es.close()
    }
  }, [appendEvent, scheduleRefresh, setStreaming])

  useEffect(() => {
    if (!sessionId) return undefined
    connect(sessionId)
    return () => {
      eventSourceRef.current?.close()
      eventSourceRef.current = null
      setStreaming(false)
    }
  }, [connect, sessionId, setStreaming])

  useEffect(() => {
    if (!session?.generated_graph || session.workflow_id || session.status !== 'ready') return
    setDraftWorkflow(
      session.recipe_ir?.goal_summary || 'Agent Draft',
      session.generated_graph.nodes,
      session.generated_graph.edges
    )
  }, [session, setDraftWorkflow])

  useEffect(() => {
    return () => {
      if (refreshTimerRef.current !== null) {
        window.clearTimeout(refreshTimerRef.current)
      }
    }
  }, [])

  const createSession = async (goal: string) => {
    setBusy(true)
    setError(null)
    try {
      const created = await agentApi.createSession(goal)
      setSessionId(created.session_id)
      await refreshSession(created.session_id)
      return created
    } catch (err) {
      const message = getApiErrorMessage(err, '创建 Agent 会话失败')
      setError(message)
      throw err
    } finally {
      setBusy(false)
    }
  }

  const answerSession = async (answer: string) => {
    if (!sessionId) return
    setBusy(true)
    setError(null)
    try {
      await agentApi.answerSession(sessionId, answer)
      await refreshSession(sessionId)
    } catch (err) {
      const message = getApiErrorMessage(err, '提交回答失败')
      setError(message)
      throw err
    } finally {
      setBusy(false)
    }
  }

  const skipSession = async () => {
    if (!sessionId) return
    setBusy(true)
    setError(null)
    try {
      await agentApi.skipSession(sessionId)
      await refreshSession(sessionId)
    } catch (err) {
      const message = getApiErrorMessage(err, '跳过澄清失败')
      setError(message)
      throw err
    } finally {
      setBusy(false)
    }
  }

  const applySession = async () => {
    if (!sessionId) return null
    setBusy(true)
    setError(null)
    try {
      const applied = await agentApi.applySession(sessionId)
      const workflow = await workflowApi.get(applied.workflow_id)
      setWorkflow(workflow.id, workflow.name, workflow.graph.nodes, workflow.graph.edges)
      await refreshSession(sessionId)
      return applied
    } catch (err) {
      const message = getApiErrorMessage(err, '应用工作流失败')
      setError(message)
      throw err
    } finally {
      setBusy(false)
    }
  }

  return {
    sessionId,
    session,
    events,
    isBusy,
    isStreaming,
    error,
    createSession,
    answerSession,
    skipSession,
    applySession,
    refreshSession,
    reset,
  }
}
