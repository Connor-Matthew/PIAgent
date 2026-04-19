import { create } from 'zustand'
import type { NodeExecutionState, SSEEvent, StreamProgressDelta } from '../types/workflow'

type DebugMode = 'simple' | 'detailed'

interface DebugState {
  isOpen: boolean
  mode: DebugMode
  isRunning: boolean
  workflowId: string | null
  runId: string | null
  inputText: string
  runInputs: Record<string, unknown>
  nodeStates: Map<string, NodeExecutionState>
  audioUrl: string | null
  totalDuration: number | null
  finalAnswer: string | null
  finalOutputs: Record<string, unknown> | null

  toggleDrawer: () => void
  openDrawer: () => void
  closeDrawer: () => void
  setMode: (mode: DebugMode) => void
  setInputText: (text: string) => void
  setRunInput: (name: string, value: unknown) => void
  setRunInputs: (inputs: Record<string, unknown>) => void
  startRun: () => void
  attachRun: (workflowId: string, runId: string) => void
  finishRun: (patch?: {
    duration?: number | null
    finalAnswer?: string | null
    finalOutputs?: Record<string, unknown> | null
  }) => void
  markStopped: (message?: string) => void
  handleSSEEvent: (event: SSEEvent) => void
  reset: () => void
}

export const useDebugStore = create<DebugState>((set, get) => ({
  isOpen: false,
  mode: 'detailed',
  isRunning: false,
  workflowId: null,
  runId: null,
  inputText: '',
  runInputs: {},
  nodeStates: new Map(),
  audioUrl: null,
  totalDuration: null,
  finalAnswer: null,
  finalOutputs: null,

  toggleDrawer: () => set({ isOpen: !get().isOpen }),

  openDrawer: () => set({ isOpen: true }),

  closeDrawer: () => set({ isOpen: false }),

  setMode: (mode) => set({ mode }),

  setInputText: (text) => set({ inputText: text }),

  setRunInput: (name, value) =>
    set({ runInputs: { ...get().runInputs, [name]: value } }),

  setRunInputs: (inputs) => set({ runInputs: inputs }),

  startRun: () =>
    set({
      isRunning: true,
      workflowId: null,
      runId: null,
      nodeStates: new Map(),
      audioUrl: null,
      totalDuration: null,
      finalAnswer: null,
      finalOutputs: null,
    }),

  attachRun: (workflowId, runId) =>
    set({
      workflowId,
      runId,
    }),

  finishRun: (patch) =>
    set({
      isRunning: false,
      workflowId: null,
      runId: null,
      totalDuration: patch?.duration ?? get().totalDuration,
      finalAnswer: patch?.finalAnswer ?? get().finalAnswer,
      finalOutputs: patch?.finalOutputs ?? get().finalOutputs,
    }),

  markStopped: (message) =>
    set({
      isRunning: false,
      workflowId: null,
      runId: null,
      finalAnswer: message ?? '已手动停止执行',
      finalOutputs: null,
    }),

  handleSSEEvent: (event) => {
    const states = new Map(get().nodeStates)

    if (event.type === 'node_start' && event.node_id) {
      states.set(event.node_id, {
        nodeId: event.node_id,
        nodeType: event.node_type,
        status: 'running',
        chunks: [],
      })
      set({ nodeStates: states })
    }

    if (event.type === 'node_stream' && event.node_id) {
      const existing = states.get(event.node_id) ?? {
        nodeId: event.node_id,
        nodeType: event.node_type,
        status: 'running' as const,
        chunks: [],
      }

      if (typeof event.seq === 'number' && typeof existing.lastSeq === 'number' && event.seq <= existing.lastSeq) {
        return
      }

      if (typeof event.delta === 'string' && event.delta) {
        existing.chunks.push(event.delta)
      } else if (event.delta && typeof event.delta === 'object') {
        const progress = event.delta as StreamProgressDelta
        existing.progressLabel = progress.message ?? `${progress.current}/${progress.total}`
      }

      if (typeof event.seq === 'number') {
        existing.lastSeq = event.seq
      }

      states.set(event.node_id, { ...existing })
      set({ nodeStates: states })
    }

    if (event.type === 'node_heartbeat' && event.node_id) {
      const existing = states.get(event.node_id) ?? {
        nodeId: event.node_id,
        nodeType: event.node_type,
        status: 'running' as const,
        chunks: [],
      }
      existing.heartbeatElapsed = event.elapsed
      existing.heartbeatMessage = event.message
      states.set(event.node_id, { ...existing })
      set({ nodeStates: states })
    }

    if (event.type === 'node_end' && event.node_id) {
      const existing = states.get(event.node_id) ?? {
        nodeId: event.node_id,
        nodeType: event.node_type,
        status: 'running' as const,
        chunks: [],
      }
      existing.status = event.status === 'failed' ? 'failed' : 'completed'
      existing.duration = event.duration
      existing.heartbeatElapsed = undefined
      existing.heartbeatMessage = undefined
      const output = event.output || {}
      if (output.audio_url) {
        set({ audioUrl: output.audio_url as string })
      }
      if (output.text) {
        existing.output = String(output.text)
      } else if (output.context) {
        existing.output = String(output.context)
      } else if (output.audio_url) {
        existing.output = `audio: ${output.audio_url}`
      } else if (output.answer) {
        existing.output = String(output.answer)
      }
      states.set(event.node_id, { ...existing })
      set({ nodeStates: states })
    }

    if (event.type === 'workflow_end') {
      const isCancelled = event.status === 'cancelled'
      set({
        isRunning: false,
        workflowId: null,
        runId: null,
        totalDuration: event.duration ?? null,
        finalAnswer: isCancelled ? (event.message ?? '已手动停止执行') : (event.answer ?? null),
        finalOutputs: isCancelled ? null : (event.outputs ?? null),
      })
      // Also derive audio_url from final outputs if present
      if (event.outputs?.audio_url) {
        set({ audioUrl: event.outputs.audio_url as string })
      }
    }
  },

  reset: () =>
    set({
      isRunning: false,
      workflowId: null,
      runId: null,
      nodeStates: new Map(),
      audioUrl: null,
      totalDuration: null,
      finalAnswer: null,
      finalOutputs: null,
    }),
}))
