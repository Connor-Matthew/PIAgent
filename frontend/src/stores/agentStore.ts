import { create } from 'zustand'

import type { AgentSession, AgentSessionEvent } from '../types/agent'


interface AgentState {
  sessionId: string | null
  session: AgentSession | null
  events: AgentSessionEvent[]
  eventKeys: string[]
  isBusy: boolean
  isStreaming: boolean
  error: string | null

  setSessionId: (sessionId: string | null) => void
  setSession: (session: AgentSession | null) => void
  appendEvent: (event: AgentSessionEvent) => void
  setBusy: (isBusy: boolean) => void
  setStreaming: (isStreaming: boolean) => void
  setError: (error: string | null) => void
  reset: () => void
}


function buildEventKey(event: AgentSessionEvent) {
  return JSON.stringify(event)
}


export const useAgentStore = create<AgentState>((set, get) => ({
  sessionId: null,
  session: null,
  events: [],
  eventKeys: [],
  isBusy: false,
  isStreaming: false,
  error: null,

  setSessionId: (sessionId) => set({ sessionId }),

  setSession: (session) =>
    set((state) => ({
      session,
      sessionId: session?.session_id ?? state.sessionId,
    })),

  appendEvent: (event) => {
    const eventKey = buildEventKey(event)
    if (get().eventKeys.includes(eventKey)) return
    set((state) => ({
      events: [...state.events, event],
      eventKeys: [...state.eventKeys, eventKey],
    }))
  },

  setBusy: (isBusy) => set({ isBusy }),

  setStreaming: (isStreaming) => set({ isStreaming }),

  setError: (error) => set({ error }),

  reset: () =>
    set({
      sessionId: null,
      session: null,
      events: [],
      eventKeys: [],
      isBusy: false,
      isStreaming: false,
      error: null,
    }),
}))
