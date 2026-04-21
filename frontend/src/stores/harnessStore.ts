import { create } from 'zustand'
import type { HarnessEvent, HarnessOpenQuestion, HarnessStatus } from '../types/harness'
import type { WorkflowGraph } from '../types/workflow'

export interface ChatMessage {
  id: string
  role: 'user' | 'agent' | 'tool_call' | 'tool_result'
  content: string
  tool?: string
  args?: Record<string, unknown>
  tool_call_id?: string
  collapsed?: boolean
}

interface HarnessState {
  sessionId: string | null
  status: HarnessStatus
  goal: string
  events: HarnessEvent[]
  messages: ChatMessage[]
  graphSnapshot: WorkflowGraph | null
  openQuestion: HarnessOpenQuestion | null
  error: string | null
  isRunning: boolean

  setSessionId: (id: string | null) => void
  setStatus: (status: HarnessStatus) => void
  setGoal: (goal: string) => void
  appendEvent: (event: HarnessEvent) => void
  appendMessage: (message: ChatMessage) => void
  updateLastAgentMessage: (content: string) => void
  finalizeAgentMessage: (content: string) => void
  setGraphSnapshot: (graph: WorkflowGraph | null) => void
  setOpenQuestion: (q: HarnessOpenQuestion | null) => void
  setError: (error: string | null) => void
  setRunning: (running: boolean) => void
  reset: () => void
}

let _msgId = 0
function nextId() {
  return `msg-${++_msgId}`
}

export const useHarnessStore = create<HarnessState>((set) => ({
  sessionId: null,
  status: 'idle',
  goal: '',
  events: [],
  messages: [],
  graphSnapshot: null,
  openQuestion: null,
  error: null,
  isRunning: false,

  setSessionId: (id) => set({ sessionId: id }),
  setStatus: (status) => set({ status }),
  setGoal: (goal) => set({ goal }),
  appendEvent: (event) => set((state) => ({ events: [...state.events, event] })),
  appendMessage: (message) => set((state) => ({ messages: [...state.messages, message] })),
  updateLastAgentMessage: (content) =>
    set((state) => {
      const msgs = [...state.messages]
      const last = msgs[msgs.length - 1]
      if (last && last.role === 'agent') {
        last.content += content
        return { messages: msgs }
      }
      return { messages: [...msgs, { id: nextId(), role: 'agent', content }] }
    }),
  finalizeAgentMessage: (content) =>
    set((state) => {
      const msgs = [...state.messages]
      const last = msgs[msgs.length - 1]
      if (last && last.role === 'agent') {
        msgs[msgs.length - 1] = { ...last, content }
        return { messages: msgs }
      }
      return { messages: [...msgs, { id: nextId(), role: 'agent', content }] }
    }),
  setGraphSnapshot: (graph) => set({ graphSnapshot: graph }),
  setOpenQuestion: (q) => set({ openQuestion: q }),
  setError: (error) => set({ error }),
  setRunning: (running) => set({ isRunning: running }),
  reset: () =>
    set({
      sessionId: null,
      status: 'idle',
      goal: '',
      events: [],
      messages: [],
      graphSnapshot: null,
      openQuestion: null,
      error: null,
      isRunning: false,
    }),
}))
