import { useEffect, useMemo } from 'react'
import ReactFlow, { Background, Controls, MiniMap, MarkerType, useReactFlow } from 'reactflow'
import 'reactflow/dist/style.css'
import { useWorkflowStore } from '../../stores/workflowStore'
import { useDebugStore } from '../../stores/debugStore'
import { nodeTypes } from '../nodes'
import { useDnD } from '../../hooks/useDnD'
import { CanvasToolbar } from './CanvasToolbar'

const DEFAULT_EDGE_OPTIONS = {
  markerEnd: { type: MarkerType.ArrowClosed, color: '#64748b' },
}

export function WorkflowCanvas() {
  const { fitView } = useReactFlow()
  const { nodes, edges, onNodesChange, onEdgesChange, onConnect, setSelectedNode, deleteEdge } = useWorkflowStore()
  const isExecuting = useDebugStore((s) => s.isRunning)
  const nodeStates = useDebugStore((s) => s.nodeStates)
  const getAggregatedNodeStatus = useDebugStore((s) => s.getAggregatedNodeStatus)
  const { onInit, onDragOver, onDrop } = useDnD()

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
  }, [edges, nodeStates])

  useEffect(() => {
    if (!isExecuting || nodes.length === 0) return

    const timer = window.setTimeout(() => {
      fitView({ padding: 0.2, duration: 350 })
    }, 80)

    return () => window.clearTimeout(timer)
  }, [edges.length, fitView, isExecuting, nodes.length])

  return (
    <div className="flex-1 relative">
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
        defaultEdgeOptions={DEFAULT_EDGE_OPTIONS}
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
