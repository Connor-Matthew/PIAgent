import { agentApi } from '../services/api'
import { useAutoRunStore } from '../stores/autoRunStore'
import { useDebugStore } from '../stores/debugStore'
import { useWorkflowStore } from '../stores/workflowStore'
import type { AgentAutoRunStreamEvent } from '../types/agent'
import type { SSEEvent } from '../types/workflow'


const EXECUTION_EVENT_TYPES = new Set<SSEEvent['type']>([
  'workflow_start',
  'node_start',
  'node_stream',
  'node_heartbeat',
  'node_end',
  'workflow_end',
])


function getErrorMessage(error: unknown, fallback: string) {
  if (error instanceof Error && error.message) {
    return error.message
  }
  return fallback
}


function buildDraftName(goal: string) {
  const trimmed = goal.trim()
  if (trimmed.length <= 32) return trimmed
  return `${trimmed.slice(0, 29)}...`
}


function isExecutionEvent(event: AgentAutoRunStreamEvent): event is SSEEvent {
  return EXECUTION_EVENT_TYPES.has(event.type as SSEEvent['type'])
}


export function useAgentAutoRun() {
  const autoRunEvents = useAutoRunStore((s) => s.events)
  const isAutoRunning = useAutoRunStore((s) => s.isRunning)
  const autoRunError = useAutoRunStore((s) => s.error)
  const startAutoRun = useAutoRunStore((s) => s.start)
  const appendAutoRunEvent = useAutoRunStore((s) => s.appendEvent)
  const setAutoRunError = useAutoRunStore((s) => s.setError)
  const finishAutoRun = useAutoRunStore((s) => s.finish)

  const startDraftBuild = useWorkflowStore((s) => s.startDraftBuild)
  const addNode = useWorkflowStore((s) => s.addNode)
  const addGraphEdge = useWorkflowStore((s) => s.addGraphEdge)
  const patchNodeConfig = useWorkflowStore((s) => s.patchNodeConfig)
  const setAllNodeVisuals = useWorkflowStore((s) => s.setAllNodeVisuals)

  const closeDrawer = useDebugStore((s) => s.closeDrawer)
  const openDrawer = useDebugStore((s) => s.openDrawer)
  const setInputText = useDebugStore((s) => s.setInputText)
  const startRun = useDebugStore((s) => s.startRun)
  const finishRun = useDebugStore((s) => s.finishRun)
  const handleSSEEvent = useDebugStore((s) => s.handleSSEEvent)

  const autoRun = async (goal: string) => {
    const trimmedGoal = goal.trim()
    if (!trimmedGoal) return

    startAutoRun(trimmedGoal)
    startDraftBuild(buildDraftName(trimmedGoal))
    closeDrawer()
    setInputText(trimmedGoal)

    let sawWorkflowEnd = false
    let nodeIndex = 0

    try {
      await agentApi.autoRun(trimmedGoal, (event) => {
        if (isExecutionEvent(event)) {
          if (event.type === 'workflow_start') {
            openDrawer()
            startRun()
            setAllNodeVisuals({
              visualState: 'idle',
              visualLabel: '',
              statusNote: '执行开始',
            })
          }
          handleSSEEvent(event)
          if (event.type === 'workflow_end') {
            sawWorkflowEnd = true
          }
          return
        }

        appendAutoRunEvent(event)

        if (event.type === 'node_added' && event.node) {
          nodeIndex += 1
          addNode({
            ...event.node,
            data: {
              ...(event.node.data || {}),
              visualState: 'building',
              visualLabel: `STEP ${nodeIndex}`,
              statusNote: 'Planner 正在放置节点',
            },
          })
          return
        }

        if (event.type === 'edge_added' && event.edge) {
          addGraphEdge({
            ...event.edge,
            animated: true,
          })
          return
        }

        if (event.type === 'node_config_updated' && event.node_id && event.patch) {
          patchNodeConfig(event.node_id, event.patch)
          return
        }

        if (event.type === 'workflow_built') {
          setAllNodeVisuals({
            visualState: 'idle',
            visualLabel: 'READY',
            statusNote: '图结构已验证',
          })
          return
        }

        if (event.type === 'planning_error') {
          setAllNodeVisuals({
            visualState: 'failed',
            visualLabel: 'ERROR',
            statusNote: event.message || '自动构建工作流失败',
          })
          setAutoRunError(event.message || '自动构建工作流失败')
        }
      })
    } catch (err) {
      setAutoRunError(getErrorMessage(err, '自动构建工作流失败'))
    } finally {
      if (!sawWorkflowEnd) {
        finishRun()
      }
      finishAutoRun()
    }
  }

  return {
    autoRunEvents,
    autoRunError,
    isAutoRunning,
    autoRun,
  }
}
