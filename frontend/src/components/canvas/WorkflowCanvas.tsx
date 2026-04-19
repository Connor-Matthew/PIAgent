import { useEffect, useMemo } from 'react'
import ReactFlow, { Background, Controls, MiniMap, MarkerType, useReactFlow } from 'reactflow'
import 'reactflow/dist/style.css'
import { useWorkflowStore } from '../../stores/workflowStore'
import { useHarnessStore } from '../../stores/harnessStore'
import { useDebugStore } from '../../stores/debugStore'
import { nodeTypes } from '../nodes'
import { useDnD } from '../../hooks/useDnD'
import { CanvasToolbar } from './CanvasToolbar'

function describeOverlayEvent(type: string) {
  switch (type) {
    case 'session_start':
      return 'Harness 开始理解目标'
    case 'decision':
      return 'Harness 正在做决策'
    case 'tool_call':
      return '正在调用工具收集信息'
    case 'tool_result':
      return '工具已返回结果'
    case 'skill_loaded':
      return '已加载 Skill 参考'
    case 'graph_update':
      return '画布正在更新'
    case 'builder_error':
      return '构建出错，正在修正'
    case 'validator_report':
      return '正在校验图结构'
    case 'awaiting_user_input':
      return '等待用户澄清'
    case 'user_resumed':
      return '用户已回答，继续生成'
    case 'harness_ready':
      return '工作流已生成完毕'
    case 'harness_stuck':
      return 'Harness 遇到循环，已暂停'
    default:
      return '正在更新画布'
  }
}

export function WorkflowCanvas() {
  const { fitView } = useReactFlow()
  const { nodes, edges, onNodesChange, onEdgesChange, onConnect, setSelectedNode, deleteEdge, isHarnessLocked } = useWorkflowStore()
  const harnessEvents = useHarnessStore((s) => s.events)
  const harnessGoal = useHarnessStore((s) => s.goal)
  const isHarnessRunning = useHarnessStore((s) => s.isRunning)
  const harnessStatus = useHarnessStore((s) => s.status)
  const harnessError = useHarnessStore((s) => s.error)
  const isExecuting = useDebugStore((s) => s.isRunning)
  const nodeStates = useDebugStore((s) => s.nodeStates)
  const getAggregatedNodeStatus = useDebugStore((s) => s.getAggregatedNodeStatus)
  const { onInit, onDragOver, onDrop } = useDnD()

  const latestEvent = harnessEvents[harnessEvents.length - 1]

  const renderedNodes = useMemo(() => {
    return nodes.map((node) => {
      const aggregatedStatus = getAggregatedNodeStatus(node.id)
      let visualState = node.data.visualState
      let visualLabel = node.data.visualLabel
      let statusNote = node.data.statusNote

      if (aggregatedStatus === 'running') {
        visualState = 'running'
        visualLabel = 'RUN'
        statusNote = '节点执行中'
      } else if (aggregatedStatus === 'completed') {
        visualState = 'completed'
        visualLabel = 'DONE'
        statusNote = '节点已完成'
      } else if (aggregatedStatus === 'failed') {
        visualState = 'failed'
        visualLabel = 'FAIL'
        statusNote = '节点执行失败'
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
  }, [isExecuting, getAggregatedNodeStatus, nodes])

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
      } else if (isHarnessRunning) {
        stroke = 'rgba(34,211,238,0.4)'
        animated = true
        strokeDasharray = '6 6'
      }

      if (isHarnessLocked && !isExecuting) {
        stroke = 'rgba(34,211,238,0.25)'
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
  }, [edges, isHarnessRunning, isHarnessLocked, isExecuting, nodeStates])

  useEffect(() => {
    if ((!isHarnessRunning && !isExecuting) || nodes.length === 0) return

    const timer = window.setTimeout(() => {
      fitView({ padding: 0.2, duration: 350 })
    }, 80)

    return () => window.clearTimeout(timer)
  }, [edges.length, fitView, isHarnessRunning, isExecuting, nodes.length])

  const shouldShowOverlay = Boolean(harnessGoal || isHarnessRunning || isExecuting || harnessError || harnessEvents.length > 0)
  const phaseLabel = isExecuting ? 'Executing' : isHarnessRunning ? 'Building' : harnessStatus === 'failed' ? 'Failed' : harnessStatus === 'ready' ? 'Ready' : harnessEvents.length > 0 ? 'Complete' : 'Idle'
  const phaseTone = isExecuting
    ? 'border-sky-400/30 bg-sky-400/10 text-sky-100'
    : isHarnessRunning
      ? 'border-cyan-400/30 bg-cyan-400/10 text-cyan-100'
      : harnessStatus === 'failed'
        ? 'border-rose-400/30 bg-rose-400/10 text-rose-100'
        : harnessStatus === 'ready'
          ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-100'
          : 'border-slate-700/50 bg-slate-800/60 text-slate-300'

  return (
    <div className="flex-1 relative">
      {shouldShowOverlay && (
        <div className="pointer-events-none absolute left-3 top-3 z-10 w-[260px] rounded-xl border border-slate-700/80 bg-slate-950/90 p-3 shadow-2xl backdrop-blur">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-[11px] uppercase tracking-[0.24em] text-cyan-400/80">Harness Live</div>
              <div className="mt-2 text-sm font-medium text-slate-100">
                {harnessGoal || '等待新的可视化构建任务'}
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
            {harnessError
              ? harnessError
              : latestEvent?.type
                ? describeOverlayEvent(latestEvent.type)
                : '等待 Harness 开始工作'}
          </div>
        </div>
      )}

      {isHarnessLocked && (
        <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center bg-slate-950/30">
          <div className="rounded-xl border border-cyan-500/20 bg-slate-900/90 px-5 py-3 text-sm text-cyan-100 shadow-2xl backdrop-blur">
            Harness 正在生成工作流，生成完成后可编辑
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
