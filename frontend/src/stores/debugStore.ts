import { create } from 'zustand'
import type { NodeExecutionState, SSEEvent } from '../types/workflow'

type DebugMode = 'simple' | 'detailed'

interface DebugState {
  isOpen: boolean
  mode: DebugMode
  isRunning: boolean
  inputText: string
  nodeStates: Map<string, NodeExecutionState>
  audioUrl: string | null
  totalDuration: number | null

  toggleDrawer: () => void
  setMode: (mode: DebugMode) => void
  setInputText: (text: string) => void
  startRun: () => void
  handleSSEEvent: (event: SSEEvent) => void
  reset: () => void
}

export const useDebugStore = create<DebugState>((set, get) => ({
  isOpen: false,
  mode: 'detailed',
  isRunning: false,
  inputText: '',
  nodeStates: new Map(),
  audioUrl: null,
  totalDuration: null,

  toggleDrawer: () => set({ isOpen: !get().isOpen }),

  setMode: (mode) => set({ mode }),

  setInputText: (text) => set({ inputText: text }),

  startRun: () =>
    set({ isRunning: true, nodeStates: new Map(), audioUrl: null, totalDuration: null }),

  handleSSEEvent: (event) => {
    const states = new Map(get().nodeStates)

    if (event.type === 'node_start' && event.node_id) {
      states.set(event.node_id, {
        nodeId: event.node_id,
        status: 'running',
        chunks: [],
      })
      set({ nodeStates: states })
    }

    if (event.type === 'node_stream' && event.node_id) {
      const existing = states.get(event.node_id)
      if (existing && event.chunk) {
        existing.chunks.push(event.chunk)
        states.set(event.node_id, { ...existing })
        set({ nodeStates: states })
      }
    }

    if (event.type === 'node_end' && event.node_id) {
      const existing = states.get(event.node_id)
      if (existing) {
        existing.status = event.status === 'failed' ? 'failed' : 'completed'
        existing.duration = event.duration
        if (event.output?.audio_url) {
          set({ audioUrl: event.output.audio_url as string })
        }
        if (event.output?.output) {
          existing.output = String(event.output.output)
        }
        states.set(event.node_id, { ...existing })
        set({ nodeStates: states })
      }
    }

    if (event.type === 'workflow_end') {
      set({ isRunning: false, totalDuration: event.duration ?? null })
    }
  },

  reset: () =>
    set({ isRunning: false, nodeStates: new Map(), audioUrl: null, totalDuration: null }),
}))
