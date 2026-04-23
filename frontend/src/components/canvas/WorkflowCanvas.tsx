import { useEffect, useMemo } from 'react'
import ReactFlow, { Background, Controls, MiniMap, MarkerType, useReactFlow } from 'reactflow'
import 'reactflow/dist/style.css'
import { useWorkflowStore } from '../../stores/workflowStore'
import { useDebugStore } from '../../stores/debugStore'
import { nodeTypes } from '../nodes'
import { useDnD } from '../../hooks/useDnD'
import { CanvasToolbar } from './CanvasToolbar'
import { ChatPanel } from '../assistant/ChatPanel'
import { useAssistantStore } from '../../stores/assistantStore'

const DEFAULT_EDGE_OPTIONS = {
  markerEnd: { type: MarkerType.ArrowClosed, color: '#9ca3af' },
}

export function WorkflowCanvas() {
  const { fitView } = useReactFlow()
  const { nodes, edges, workflowId, onNodesChange, onEdgesChange, onConnect, setSelectedNode, deleteEdge, deleteNode } = useWorkflowStore()
  const toggleAssistant = useAssistantStore((s) => s.togglePanel)
  const assistantOpen = useAssistantStore((s) => s.isOpen)
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
      let stroke = '#9ca3af'
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
        onNodeContextMenu={(event, node) => {
          event.preventDefault()
          deleteNode(node.id)
          if (setSelectedNode && node.id) setSelectedNode(null)
        }}
        onPaneClick={() => setSelectedNode(null)}
        onEdgeDoubleClick={(_, edge) => deleteEdge(edge.id)}
        nodeTypes={nodeTypes}
        defaultEdgeOptions={DEFAULT_EDGE_OPTIONS}
        fitView
        className="bg-[#F5F5F5]"
      >
        <Background color="#d4d4d4" gap={24} size={1} />
        <Controls className="!bg-white !border-black" />
        <MiniMap className="!bg-white" nodeColor="#737373" />
      </ReactFlow>
      <CanvasToolbar />
      <button
        type="button"
        onClick={toggleAssistant}
        disabled={!workflowId}
        title="工作流助手"
        className="absolute bottom-4 right-4 z-20 flex h-11 w-11 items-center justify-center border border-black bg-white text-sm font-semibold text-black hover:bg-gray-50 disabled:cursor-not-allowed disabled:text-gray-300"
      >
        AI
      </button>
      {assistantOpen && <ChatPanel workflowId={workflowId} />}
    </div>
  )
}
