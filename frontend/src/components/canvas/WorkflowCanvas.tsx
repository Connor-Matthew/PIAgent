import { useEffect, useMemo } from 'react'
import ReactFlow, { Background, Controls, MiniMap, MarkerType, useReactFlow } from 'reactflow'
import 'reactflow/dist/style.css'
import { useWorkflowStore } from '../../stores/workflowStore'
import { useAutoRunStore } from '../../stores/autoRunStore'
import { useDebugStore } from '../../stores/debugStore'
import { nodeTypes } from '../nodes'
import { useDnD } from '../../hooks/useDnD'
import { CanvasToolbar } from './CanvasToolbar'

function describeOverlayEvent(type: string) {
  switch (type) {
    case 'planning_start':
      return 'Planner 开始理解目标'
    case 'planning_update':
      return 'Planner 正在整理步骤'
    case 'planner_action':
      return 'Planner 正在查询能力'
    case 'planner_observe':
      return 'Planner 已拿到环境信息'
    case 'node_added':
      return '画布正在长出新节点'
    case 'edge_added':
      return '正在补全节点之间的连线'
    case 'workflow_built':
      return '工作流图已构建完成'
    case 'plan_ready':
      return '规划完成，准备执行'
    default:
      return '正在更新画布'
  }
}

export function WorkflowCanvas() {
  const { fitView } = useReactFlow()
  const { nodes, edges, onNodesChange, onEdgesChange, onConnect, setSelectedNode, deleteEdge } = useWorkflowStore()
  const autoRunEvents = useAutoRunStore((s) => s.events)
  const autoRunGoal = useAutoRunStore((s) => s.goal)
  const isAutoRunning = useAutoRunStore((s) => s.isRunning)
  const autoRunError = useAutoRunStore((s) => s.error)
  const isExecuting = useDebugStore((s) => s.isRunning)
  const nodeStates = useDebugStore((s) => s.nodeStates)
  const { onInit, onDragOver, onDrop } = useDnD()

  const latestEvent = autoRunEvents[autoRunEvents.length - 1]
  const latestBuiltEdge = [...autoRunEvents].reverse().find((event) => event.type === 'edge_added')?.edge

  const renderedNodes = useMemo(() => {
    return nodes.map((node) => {
      const executionState = nodeStates.get(node.id)
      let visualState = node.data.visualState
      let visualLabel = node.data.visualLabel
      let statusNote = node.data.statusNote

      if (executionState?.status === 'running') {
        visualState = 'running'
        visualLabel = 'RUN'
        statusNote = executionState.progressLabel || executionState.heartbeatMessage || '节点执行中'
      } else if (executionState?.status === 'completed') {
        visualState = 'completed'
        visualLabel = 'DONE'
        statusNote = executionState.output || '节点已完成'
      } else if (executionState?.status === 'failed') {
        visualState = 'failed'
        visualLabel = 'FAIL'
        statusNote = executionState.output || '节点执行失败'
      } else if (isExecuting && node.data.visualState !== 'failed') {
        visualState = 'idle'
        visualLabel = ''
      }

      return {
        ...node,
        data: {
          ...node.data,
          visualState,
          visualLabel,
          statusNote,
        },
      }
    })
  }, [isExecuting, nodeStates, nodes])

  const renderedEdges = useMemo(() => {
    return edges.map((edge) => {
      const sourceStatus = nodeStates.get(edge.source)?.status
      const targetStatus = nodeStates.get(edge.target)?.status
      let stroke = '#475569'
      let strokeWidth = 1.8
      let animated = Boolean(edge.animated)
      let strokeDasharray: string | undefined

      if (sourceStatus === 'running' || targetStatus === 'running') {
        stroke = '#38bdf8'
        strokeWidth = 2.6
        animated = true
      } else if (targetStatus === 'completed') {
        stroke = '#34d399'
        strokeWidth = 2.2
      } else if (targetStatus === 'failed') {
        stroke = '#fb7185'
        strokeWidth = 2.2
      } else if (
        isAutoRunning &&
        latestBuiltEdge &&
        edge.source === latestBuiltEdge.source &&
        edge.target === latestBuiltEdge.target
      ) {
        stroke = '#22d3ee'
        strokeWidth = 2.4
        animated = true
      } else if (isAutoRunning) {
        stroke = 'rgba(34,211,238,0.4)'
        animated = true
        strokeDasharray = '6 6'
      }

      return {
        ...edge,
        animated,
        style: {
          ...(edge.style || {}),
          stroke,
          strokeWidth,
          strokeDasharray,
          transition: 'stroke 220ms ease, stroke-width 220ms ease',
        },
        markerEnd: { type: MarkerType.ArrowClosed, color: stroke },
      }
    })
  }, [edges, isAutoRunning, latestBuiltEdge, nodeStates])

  useEffect(() => {
    if ((!isAutoRunning && !isExecuting) || nodes.length === 0) return

    const timer = window.setTimeout(() => {
      fitView({ padding: 0.2, duration: 350 })
    }, 80)

    return () => window.clearTimeout(timer)
  }, [edges.length, fitView, isAutoRunning, isExecuting, nodes.length])

  const shouldShowOverlay = Boolean(autoRunGoal || isAutoRunning || isExecuting || autoRunError || autoRunEvents.length > 0)
  const phaseLabel = isExecuting ? 'Executing' : isAutoRunning ? 'Building' : autoRunError ? 'Failed' : autoRunEvents.length > 0 ? 'Complete' : 'Idle'
  const phaseTone = isExecuting
    ? 'border-sky-400/30 bg-sky-400/10 text-sky-100'
    : isAutoRunning
      ? 'border-cyan-400/30 bg-cyan-400/10 text-cyan-100'
      : autoRunError
        ? 'border-rose-400/30 bg-rose-400/10 text-rose-100'
        : 'border-emerald-400/30 bg-emerald-400/10 text-emerald-100'

  return (
    <div className="flex-1 relative">
      {shouldShowOverlay && (
        <div className="pointer-events-none absolute left-3 top-3 z-10 w-[260px] rounded-xl border border-slate-700/80 bg-slate-950/90 p-3 shadow-2xl backdrop-blur">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-[11px] uppercase tracking-[0.24em] text-cyan-400/80">Planner Live</div>
              <div className="mt-2 text-sm font-medium text-slate-100">
                {autoRunGoal || '等待新的可视化构建任务'}
              </div>
            </div>
            <div className={`rounded-full border px-2 py-1 text-[11px] ${phaseTone}`}>
              {phaseLabel}
            </div>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
            <div className="rounded-xl border border-slate-800 bg-slate-900/80 px-3 py-2 text-slate-300">
              {nodes.length} nodes
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-900/80 px-3 py-2 text-slate-300">
              {edges.length} edges
            </div>
          </div>

          <div className="mt-3 rounded-xl border border-slate-800 bg-slate-900/80 px-3 py-2 text-xs leading-5 text-slate-300">
            {autoRunError
              ? autoRunError
              : latestEvent?.type
                ? describeOverlayEvent(latestEvent.type)
                : '等待 Planner 开始工作'}
          </div>
        </div>
      )}

      <ReactFlow
        nodes={renderedNodes}
        edges={renderedEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onInit={onInit}
        onDragOver={onDragOver}
        onDrop={onDrop}
        onNodeClick={(_, node) => setSelectedNode(node.id)}
        onPaneClick={() => setSelectedNode(null)}
        onEdgeDoubleClick={(_, edge) => deleteEdge(edge.id)}
        nodeTypes={nodeTypes}
        defaultEdgeOptions={{
          markerEnd: { type: MarkerType.ArrowClosed, color: '#64748b' },
        }}
        fitView
        className="bg-[radial-gradient(circle_at_top_left,_rgba(34,211,238,0.08),_transparent_28%),radial-gradient(circle_at_bottom_right,_rgba(56,189,248,0.06),_transparent_30%),#0a0f1a]"
      >
        <Background color="#1e293b" gap={24} size={1} />
        <Controls className="!bg-slate-800 !border-slate-700" />
        <MiniMap className="!bg-slate-900" nodeColor="#334155" />
      </ReactFlow>
      <CanvasToolbar />
    </div>
  )
}
