import { create } from 'zustand'
import type { HarnessEvent, HarnessOpenQuestion, HarnessStatus } from '../types/harness'
import type { WorkflowGraph } from '../types/workflow'

interface HarnessState {
  sessionId: string | null
  status: HarnessStatus
  goal: string
  events: HarnessEvent[]
  graphSnapshot: WorkflowGraph | null
  openQuestion: HarnessOpenQuestion | null
  error: string | null
  isRunning: boolean

  setSessionId: (id: string | null) => void
  setStatus: (status: HarnessStatus) => void
  setGoal: (goal: string) => void
  appendEvent: (event: HarnessEvent) => void
  setGraphSnapshot: (graph: WorkflowGraph | null) => void
  setOpenQuestion: (q: HarnessOpenQuestion | null) => void
  setError: (error: string | null) => void
  setRunning: (running: boolean) => void
  reset: () => void
}

export const useHarnessStore = create<HarnessState>((set) => ({
  sessionId: null,
  status: 'idle',
  goal: '',
  events: [],
  graphSnapshot: null,
  openQuestion: null,
  error: null,
  isRunning: false,

  setSessionId: (id) => set({ sessionId: id }),
  setStatus: (status) => set({ status }),
  setGoal: (goal) => set({ goal }),
  appendEvent: (event) => set((state) => ({ events: [...state.events, event] })),
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
      graphSnapshot: null,
      openQuestion: null,
      error: null,
      isRunning: false,
    }),
}))
