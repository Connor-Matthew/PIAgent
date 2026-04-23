import { create } from 'zustand'
import { assistantApi } from '../services/assistantApi'
import type { AssistantMessage, AssistantSSEEvent } from '../types/workflow'

interface AssistantState {
  isOpen: boolean
  isStreaming: boolean
  error: string | null
  messagesByWorkflow: Record<string, AssistantMessage[]>

  togglePanel: () => void
  openPanel: () => void
  closePanel: () => void
  sendMessage: (workflowId: string, text: string) => Promise<void>
  toggleTrace: (workflowId: string, messageId: string, callId: string) => void
}

function makeId(prefix: string) {
  return `${prefix}_${Date.now()}_${Math.floor(Math.random() * 10000)}`
}

function getMessages(state: AssistantState, workflowId: string) {
  return state.messagesByWorkflow[workflowId] ?? []
}

function updateAssistantMessage(
  state: AssistantState,
  workflowId: string,
  messageId: string,
  update: (message: AssistantMessage) => AssistantMessage
) {
  const messages = getMessages(state, workflowId).map((message) =>
    message.id === messageId ? update(message) : message
  )
  return {
    messagesByWorkflow: {
      ...state.messagesByWorkflow,
      [workflowId]: messages,
    },
  }
}

export const useAssistantStore = create<AssistantState>((set, get) => ({
  isOpen: false,
  isStreaming: false,
  error: null,
  messagesByWorkflow: {},

  togglePanel: () => set({ isOpen: !get().isOpen }),
  openPanel: () => set({ isOpen: true }),
  closePanel: () => set({ isOpen: false }),

  toggleTrace: (workflowId, messageId, callId) =>
    set((state) =>
      updateAssistantMessage(state, workflowId, messageId, (message) => ({
        ...message,
        toolTraces: (message.toolTraces ?? []).map((trace) =>
          trace.callId === callId ? { ...trace, isOpen: !trace.isOpen } : trace
        ),
      }))
    ),

  sendMessage: async (workflowId, text) => {
    const trimmed = text.trim()
    if (!trimmed || get().isStreaming) return

    const userMessage: AssistantMessage = {
      id: makeId('user'),
      role: 'user',
      content: trimmed,
    }
    const assistantMessage: AssistantMessage = {
      id: makeId('assistant'),
      role: 'assistant',
      content: '',
      toolTraces: [],
    }

    set((state) => ({
      isStreaming: true,
      error: null,
      messagesByWorkflow: {
        ...state.messagesByWorkflow,
        [workflowId]: [...getMessages(state, workflowId), userMessage, assistantMessage],
      },
    }))

    const handleEvent = (event: AssistantSSEEvent) => {
      if (event.event === 'tool.call') {
        const callId = String(event.data.call_id ?? '')
        set((state) =>
          updateAssistantMessage(state, workflowId, assistantMessage.id, (message) => ({
            ...message,
            toolTraces: [
              ...(message.toolTraces ?? []),
              {
                callId,
                tool: String(event.data.tool ?? ''),
                args: (event.data.args ?? {}) as Record<string, unknown>,
              },
            ],
          }))
        )
      }

      if (event.event === 'tool.result') {
        const callId = String(event.data.call_id ?? '')
        set((state) =>
          updateAssistantMessage(state, workflowId, assistantMessage.id, (message) => ({
            ...message,
            toolTraces: (message.toolTraces ?? []).map((trace) =>
              trace.callId === callId
                ? { ...trace, summary: String(event.data.summary ?? '') }
                : trace
            ),
          }))
        )
      }

      if (event.event === 'message.delta') {
        const delta = String(event.data.delta ?? '')
        set((state) =>
          updateAssistantMessage(state, workflowId, assistantMessage.id, (message) => ({
            ...message,
            content: message.content + delta,
          }))
        )
      }

      if (event.event === 'error') {
        const message = String(event.data.message ?? 'Assistant error')
        set((state) => ({
          error: message,
          ...updateAssistantMessage(state, workflowId, assistantMessage.id, (assistant) => ({
            ...assistant,
            content: assistant.content || message,
          })),
        }))
      }

      if (event.event === 'message.done') {
        set({ isStreaming: false })
      }
    }

    try {
      await assistantApi.streamMessage(workflowId, trimmed, {
        onEvent: handleEvent,
        onError: (error) => set({ error: error.message }),
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      set((state) => ({
        isStreaming: false,
        error: message,
        ...updateAssistantMessage(state, workflowId, assistantMessage.id, (assistant) => ({
          ...assistant,
          content: assistant.content || message,
        })),
      }))
    } finally {
      set({ isStreaming: false })
    }
  },
}))
