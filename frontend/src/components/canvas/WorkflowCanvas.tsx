import ReactFlow, { Background, Controls, MiniMap } from 'reactflow'
import 'reactflow/dist/style.css'
import { useWorkflowStore } from '../../stores/workflowStore'
import { nodeTypes } from '../nodes'
import { useDnD } from '../../hooks/useDnD'
import { CanvasToolbar } from './CanvasToolbar'

export function WorkflowCanvas() {
  const { nodes, edges, onNodesChange, onEdgesChange, onConnect, setSelectedNode } = useWorkflowStore()
  const { onInit, onDragOver, onDrop } = useDnD()

  return (
    <div className="flex-1 relative">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onInit={onInit}
        onDragOver={onDragOver}
        onDrop={onDrop}
        onNodeClick={(_, node) => setSelectedNode(node.id)}
        onPaneClick={() => setSelectedNode(null)}
        nodeTypes={nodeTypes}
        fitView
        className="bg-[#0a0f1a]"
      >
        <Background color="#1e293b" gap={24} size={1} />
        <Controls className="!bg-slate-800 !border-slate-700" />
        <MiniMap className="!bg-slate-900" nodeColor="#334155" />
      </ReactFlow>
      <CanvasToolbar />
    </div>
  )
}
