import { useCallback, useEffect, useState } from 'react'

import { harnessApi } from '../services/harnessApi'
import { useHarnessStore } from '../stores/harnessStore'
import { useWorkflowStore } from '../stores/workflowStore'
import { HARNESS_EVENT_TYPES, type HarnessEvent, type HarnessStatus } from '../types/harness'

let activeEventSource: EventSource | null = null

interface UseHarnessSessionOptions {
  autoConnect?: boolean
}

function getErrorMessage(error: unknown, fallback: string) {
  if (error instanceof Error && error.message) {
    return error.message
  }
  return fallback
}

function isHarnessStatus(status: unknown): status is HarnessStatus {
  return (
    status === 'idle' ||
    status === 'running' ||
    status === 'awaiting_user' ||
    status === 'waiting' ||
    status === 'ready' ||
    status === 'failed' ||
    status === 'applied'
  )
}

export function useHarnessSession(options: UseHarnessSessionOptions = {}) {
  const { autoConnect = true } = options
  const [isConnecting, setIsConnecting] = useState(false)

  const {
    sessionId,
    status,
    events,
    error,
    openQuestion,
    setSessionId,
    setStatus,
    setGoal,
    appendEvent,
    appendMessage,
    updateLastAgentMessage,
    finalizeAgentMessage,
    setGraphSnapshot,
    setOpenQuestion,
    setError,
    setRunning,
    reset,
  } = useHarnessStore()

  const setDraftSnapshot = useWorkflowStore((s) => s.setDraftSnapshot)
  const setDraftWorkflow = useWorkflowStore((s) => s.setDraftWorkflow)
  const setWorkflow = useWorkflowStore((s) => s.setWorkflow)
  const setHarnessLocked = useWorkflowStore((s) => s.setHarnessLocked)
  const setAllNodeVisuals = useWorkflowStore((s) => s.setAllNodeVisuals)

  const disconnect = useCallback(() => {
    if (activeEventSource) {
      activeEventSource.close()
      activeEventSource = null
    }
    setRunning(false)
  }, [setRunning])

  const handleEvent = useCallback((event: HarnessEvent) => {
    appendEvent(event)

    switch (event.type) {
      case 'session_start': {
        setStatus('running')
        if (event.goal) setGoal(event.goal)
        setDraftSnapshot('Harness Draft', [], [])
        break
      }

      case 'agent_message_delta': {
        if (event.content) {
          updateLastAgentMessage(event.content as string)
        }
        break
      }

      case 'agent_message': {
        if (event.content) {
          finalizeAgentMessage(event.content as string)
        }
        break
      }

      case 'decision': {
        // trace only (legacy)
        break
      }

      case 'tool_call': {
        appendMessage({
          id: `msg-${Date.now()}`,
          role: 'tool_call',
          content: '',
          tool: event.tool,
          args: event.args,
        })
        break
      }

      case 'tool_result': {
        appendMessage({
          id: `msg-${Date.now()}`,
          role: 'tool_result',
          content: event.summary || event.error || '',
          tool: event.tool,
        })
        break
      }

      case 'skill_loaded': {
        break
      }

      case 'graph_update': {
        if (event.snapshot) {
          setGraphSnapshot(event.snapshot)
          setDraftSnapshot('Harness Draft', event.snapshot.nodes, event.snapshot.edges)
          setAllNodeVisuals({
            visualState: 'building',
            visualLabel: 'BUILD',
            statusNote: 'Harness 正在放置节点',
          })
        }
        break
      }

      case 'builder_error': {
        // trace only; red inline shown in status panel
        break
      }

      case 'validator_report': {
        // trace only
        break
      }

      case 'awaiting_user_input': {
        setStatus('awaiting_user')
        if (event.question_id && event.prompt) {
          setOpenQuestion({
            question_id: event.question_id,
            prompt: event.prompt,
            options: event.options || null,
          })
        } else {
          setOpenQuestion(null)
        }
        disconnect()
        break
      }

      case 'user_resumed': {
        setStatus('running')
        setOpenQuestion(null)
        break
      }

      case 'harness_ready': {
        setStatus('ready')
        if (event.snapshot) {
          setGraphSnapshot(event.snapshot)
          setDraftWorkflow('Harness Draft', event.snapshot.nodes, event.snapshot.edges)
        }
        disconnect()
        break
      }

      case 'harness_stuck': {
        setStatus('failed')
        setError(event.reason || 'Harness 陷入循环')
        disconnect()
        break
      }

      case 'session_end': {
        if (event.status === 'failed') {
          setStatus('failed')
          setError(event.reason || 'Session ended with failure')
        } else if (isHarnessStatus(event.status)) {
          setStatus(event.status)
          if (event.status !== 'awaiting_user') {
            setOpenQuestion(null)
          }
        }
        disconnect()
        break
      }
    }
  }, [appendEvent, setStatus, setGoal, setGraphSnapshot, setDraftSnapshot, setOpenQuestion, disconnect, setError, setDraftWorkflow, setAllNodeVisuals, appendMessage, updateLastAgentMessage, finalizeAgentMessage])

  const connect = useCallback((id: string) => {
    disconnect()
    setError(null)

    const es = harnessApi.streamEvents(id)
    activeEventSource = es
    setRunning(true)

    const consume = (raw: MessageEvent<string>) => {
      try {
        const data = JSON.parse(raw.data) as HarnessEvent
        handleEvent(data)
      } catch {
        // ignore malformed events
      }
    }

    es.onmessage = consume
    for (const eventType of HARNESS_EVENT_TYPES) {
      es.addEventListener(eventType, consume as EventListener)
    }

    es.onerror = () => {
      setRunning(false)
      if (useHarnessStore.getState().status === 'running') {
        setError('Harness 事件流连接失败，请重试')
      }
      es.close()
      if (activeEventSource === es) {
        activeEventSource = null
      }
    }
  }, [disconnect, handleEvent, setError, setRunning])

  // Lock/unlock canvas based on harness status
  useEffect(() => {
    const locked = status === 'running' || (status === 'awaiting_user' && Boolean(openQuestion)) || status === 'failed'
    setHarnessLocked(locked)
  }, [status, openQuestion, setHarnessLocked])

  useEffect(() => {
    if (!autoConnect) return
    if (!sessionId) return
    connect(sessionId)
    return () => {
      disconnect()
    }
  }, [autoConnect, sessionId, connect, disconnect])

  const createSession = async (goal: string) => {
    setIsConnecting(true)
    setError(null)
    try {
      const created = await harnessApi.createSession(goal)
      setSessionId(created.session_id)
      setStatus('running')
      setGoal(goal)
      // Add user message to chat
      appendMessage({
        id: `msg-${Date.now()}`,
        role: 'user',
        content: goal,
      })
      return created
    } catch (err) {
      const message = getErrorMessage(err, '创建 Harness 会话失败')
      setError(message)
      throw err
    } finally {
      setIsConnecting(false)
    }
  }

  const resumeSession = async (questionId: string, answer: string) => {
    if (!sessionId) return
    setError(null)
    // Add user answer to chat
    appendMessage({
      id: `msg-${Date.now()}`,
      role: 'user',
      content: answer,
    })
    try {
      await harnessApi.resumeSession(sessionId, questionId, answer)
      setStatus('running')
      setOpenQuestion(null)
      // Reconnect SSE
      connect(sessionId)
    } catch (err) {
      const message = getErrorMessage(err, '恢复会话失败')
      setError(message)
      throw err
    }
  }

  const continueSession = async (messageText: string) => {
    if (!sessionId) return
    setError(null)
    appendMessage({
      id: `msg-${Date.now()}`,
      role: 'user',
      content: messageText,
    })
    try {
      await harnessApi.continueSession(sessionId, messageText)
      setStatus('running')
      setOpenQuestion(null)
      connect(sessionId)
    } catch (err) {
      const message = getErrorMessage(err, '继续会话失败')
      setError(message)
      throw err
    }
  }

  const applySession = async () => {
    if (!sessionId) return null
    try {
      const result = await harnessApi.applySession(sessionId)
      setStatus('applied')
      // Load the persisted workflow into canvas
      setWorkflow(result.workflow_id, 'Harness Workflow', result.graph.nodes as Parameters<typeof setWorkflow>[2], result.graph.edges as Parameters<typeof setWorkflow>[3])
      return result
    } catch (err) {
      const message = getErrorMessage(err, '应用工作流失败')
      setError(message)
      throw err
    }
  }

  const abortSession = async () => {
    if (!sessionId) return
    try {
      await harnessApi.abortSession(sessionId)
      disconnect()
      setStatus('failed')
    } catch {
      // ignore
    }
  }

  return {
    sessionId,
    status,
    events,
    error,
    openQuestion,
    isConnecting,
    createSession,
    resumeSession,
    continueSession,
    applySession,
    abortSession,
    reset,
  }
}
