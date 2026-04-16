import { create } from 'zustand'

import type { AgentAutoRunEvent } from '../types/agent'


interface AutoRunState {
  goal: string
  isRunning: boolean
  error: string | null
  events: AgentAutoRunEvent[]

  start: (goal: string) => void
  appendEvent: (event: AgentAutoRunEvent) => void
  setError: (error: string | null) => void
  finish: () => void
  reset: () => void
}


export const useAutoRunStore = create<AutoRunState>((set) => ({
  goal: '',
  isRunning: false,
  error: null,
  events: [],

  start: (goal) =>
    set({
      goal,
      isRunning: true,
      error: null,
      events: [],
    }),

  appendEvent: (event) =>
    set((state) => ({
      events: [...state.events, event],
    })),

  setError: (error) => set({ error }),

  finish: () => set({ isRunning: false }),

  reset: () =>
    set({
      goal: '',
      isRunning: false,
      error: null,
      events: [],
    }),
}))
