import { useEffect, useState } from 'react'
import { ReactFlowProvider } from 'reactflow'
import { NodeLibrary } from './components/panels/NodeLibrary'
import { WorkflowCanvas } from './components/canvas/WorkflowCanvas'
import { NodeConfig } from './components/panels/NodeConfig'
import { DebugDrawer } from './components/debug/DebugDrawer'
import { useWorkflowStore } from './stores/workflowStore'
import { workflowApi } from './services/api'
import type { WorkflowGraph } from './types/workflow'

export default function App() {
  const { workflowId, workflowName, toGraphJSON, setWorkflow } = useWorkflowStore()
  const [isSaving, setIsSaving] = useState(false)

  // Load workflows on mount and auto-create one if needed
  useEffect(() => {
    workflowApi.list().then((list) => {
      if (list.length > 0 && !workflowId) {
        const first = list[0]
        const graph = first.graph as WorkflowGraph
        setWorkflow(first.id, first.name, (graph.nodes || []) as any, (graph.edges || []) as any)
      } else if (!workflowId) {
        const emptyGraph: WorkflowGraph = { nodes: [], edges: [] }
        workflowApi
          .create({ name: '未命名工作流', graph: emptyGraph })
          .then((wf) => {
            const graph = wf.graph as WorkflowGraph
            setWorkflow(wf.id, wf.name, (graph.nodes || []) as any, (graph.edges || []) as any)
          })
      }
    })
  }, [setWorkflow, workflowId])

  const handleSave = async () => {
    if (!workflowId) return
    setIsSaving(true)
    await workflowApi.update(workflowId, {
      name: workflowName,
      graph: toGraphJSON(),
    })
    setIsSaving(false)
  }

  return (
    <ReactFlowProvider>
      <div className="h-screen flex flex-col">
        {/* Header */}
        <header className="bg-slate-900 border-b border-slate-800 px-4 py-2 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <span className="text-blue-400 font-bold text-lg">PIAgent</span>
            <span className="text-slate-500 text-sm hidden sm:inline">AI Agent 工作流编排平台</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-slate-400 text-sm">{workflowName}</span>
            <button
              onClick={handleSave}
              disabled={isSaving || !workflowId}
              className="bg-slate-700 text-white text-xs px-3 py-1.5 rounded-md hover:bg-slate-600 disabled:opacity-50"
            >
              {isSaving ? '保存中...' : '💾 保存'}
            </button>
          </div>
        </header>

        {/* Main content: 3-column layout */}
        <div className="flex flex-1 overflow-hidden">
          <NodeLibrary />
          <WorkflowCanvas />
          <NodeConfig />
        </div>

        {/* Debug drawer */}
        <DebugDrawer />
      </div>
    </ReactFlowProvider>
  )
}
