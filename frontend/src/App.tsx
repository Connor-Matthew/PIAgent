import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom'
import { ReactFlowProvider } from 'reactflow'
import { AgentPanel } from './components/agent/AgentPanel'
import { NodeLibrary } from './components/panels/NodeLibrary'
import { WorkflowCanvas } from './components/canvas/WorkflowCanvas'
import { NodeConfig } from './components/panels/NodeConfig'
import { DebugDrawer } from './components/debug/DebugDrawer'
import { useWorkflowStore, defaultStartNode, defaultEndNode } from './stores/workflowStore'
import { useDebugStore } from './stores/debugStore'
import { workflowApi } from './services/api'
import type { WorkflowGraph } from './types/workflow'
import ProvidersPage from './pages/Providers'

function WorkflowEditor() {
  const { workflowId, isDraft, setWorkflow } = useWorkflowStore()
  // Load workflows on mount and auto-create one if needed
  useEffect(() => {
    if (isDraft) return
    workflowApi.list().then((list) => {
      if (list.length > 0 && !workflowId) {
        const first = list[0]
        workflowApi.get(first.id).then((wf) => {
          const graph = wf.graph as WorkflowGraph
          setWorkflow(wf.id, wf.name, (graph.nodes || []) as any, (graph.edges || []) as any)
        })
      } else if (!workflowId) {
        const defaultGraph: WorkflowGraph = {
          nodes: [defaultStartNode, defaultEndNode] as any,
          edges: [],
        }
        workflowApi
          .create({ name: '未命名工作流', graph: defaultGraph })
          .then((wf) => {
            const graph = wf.graph as WorkflowGraph
            setWorkflow(wf.id, wf.name, (graph.nodes || []) as any, (graph.edges || []) as any)
        })
      }
    })
  }, [isDraft, setWorkflow, workflowId])

  return (
    <>
      {/* Main content: 3-column layout */}
      <div className="flex flex-1 overflow-hidden">
        <NodeLibrary />
        <div className="flex-1 flex flex-col overflow-hidden">
          <AgentPanel />
          <WorkflowCanvas />
          <DebugDrawer />
        </div>
        <NodeConfig />
      </div>
    </>
  )
}

function AppContent() {
  const location = useLocation()
  const isWorkflow = location.pathname === '/'
  const isProviders = location.pathname === '/providers'

  const { workflowId, workflowName, isDraft, toGraphJSON, setWorkflow } = useWorkflowStore()
  const debugReset = useDebugStore((s) => s.reset)
  const [isSaving, setIsSaving] = useState(false)

  const createNewWorkflow = () => {
    const defaultGraph: WorkflowGraph = {
      nodes: [defaultStartNode, defaultEndNode] as any,
      edges: [],
    }
    workflowApi
      .create({ name: '未命名工作流', graph: defaultGraph })
      .then((wf) => {
        const graph = wf.graph as WorkflowGraph
        setWorkflow(wf.id, wf.name, (graph.nodes || []) as any, (graph.edges || []) as any)
        debugReset()
      })
  }

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
    <div className="h-screen flex flex-col">
      {/* Header */}
      <header className="bg-slate-900 border-b border-slate-800 px-4 py-2 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-4">
          <Link to="/" className="text-blue-400 font-bold text-lg hover:text-blue-300">
            PIAgent
          </Link>
          <span className="text-slate-500 text-sm hidden sm:inline">AI Agent 工作流编排平台</span>
          <nav className="flex items-center gap-2 ml-4 border-l border-slate-700 pl-4">
            <Link
              to="/"
              className={`text-xs px-3 py-1.5 rounded-md transition-colors ${
                isWorkflow
                  ? 'bg-blue-500 text-white'
                  : 'bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white'
              }`}
            >
              工作流
            </Link>
            <Link
              to="/providers"
              className={`text-xs px-3 py-1.5 rounded-md transition-colors ${
                isProviders
                  ? 'bg-blue-500 text-white'
                  : 'bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white'
              }`}
            >
              Providers
            </Link>
          </nav>
        </div>
        <div className="flex items-center gap-3">
          {isWorkflow && (
            <>
              <span className="text-slate-400 text-sm">{workflowName}</span>
              {isDraft && (
                <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-200">
                  Agent Draft
                </span>
              )}
              <button
                onClick={createNewWorkflow}
                className="bg-slate-800 text-white text-xs px-3 py-1.5 rounded-md hover:bg-slate-700"
              >
                ➕ 新建
              </button>
              <button
                onClick={handleSave}
                disabled={isSaving || !workflowId || isDraft}
                className="bg-slate-700 text-white text-xs px-3 py-1.5 rounded-md hover:bg-slate-600 disabled:opacity-50"
              >
                {isDraft ? '先 Apply' : isSaving ? '保存中...' : '💾 保存'}
              </button>
            </>
          )}
        </div>
      </header>

      <Routes>
        <Route
          path="/"
          element={
            <div className="flex flex-1 overflow-hidden">
              <ReactFlowProvider>
                <WorkflowEditor />
              </ReactFlowProvider>
            </div>
          }
        />
        <Route
          path="/providers"
          element={
            <div className="flex-1 overflow-auto">
              <ProvidersPage />
            </div>
          }
        />
      </Routes>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  )
}
