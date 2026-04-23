import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom'
import { ReactFlowProvider } from 'reactflow'
import { NodeLibrary } from './components/panels/NodeLibrary'
import { WorkflowCanvas } from './components/canvas/WorkflowCanvas'
import { RightPanel } from './components/panels/RightPanel'
import { useWorkflowStore, defaultStartNode, defaultEndNode } from './stores/workflowStore'
import { useDebugStore } from './stores/debugStore'
import { workflowApi } from './services/api'
import type { WorkflowGraph } from './types/workflow'
import ProvidersPage from './pages/Providers'

function createDefaultGraph(): WorkflowGraph {
  return {
    version: 2,
    nodes: [
      {
        id: 'start_1',
        type: 'start',
        position: defaultStartNode.position,
        label: defaultStartNode.data.label,
        locked: true,
        config: defaultStartNode.data.config,
      },
      {
        id: 'end_1',
        type: 'end',
        position: defaultEndNode.position,
        label: defaultEndNode.data.label,
        locked: true,
        config: defaultEndNode.data.config,
      },
    ],
    edges: [],
  }
}

function WorkflowEditor() {
  const { workflowId, setWorkflow } = useWorkflowStore()
  // Load workflows on mount and auto-create one if needed
  useEffect(() => {
    workflowApi.list().then((list) => {
      if (list.length > 0 && !workflowId) {
        const first = list[0]
        workflowApi.get(first.id).then((wf) => {
          setWorkflow(wf.id, wf.name, wf.graph.nodes, wf.graph.edges)
        })
      } else if (!workflowId) {
        workflowApi
          .create({ name: '未命名工作流', graph: createDefaultGraph() })
          .then((wf) => {
            setWorkflow(wf.id, wf.name, wf.graph.nodes, wf.graph.edges)
        })
      }
    })
  }, [setWorkflow, workflowId])

  return (
    <>
      {/* Main content: 3-column layout */}
      <div className="flex flex-1 overflow-hidden">
        <NodeLibrary />
        <WorkflowCanvas />
        <RightPanel />
      </div>
    </>
  )
}

function AppContent() {
  const location = useLocation()
  const isWorkflow = location.pathname === '/'
  const isProviders = location.pathname === '/providers'

  const { workflowId, workflowName, toGraphJSON, setWorkflow } = useWorkflowStore()
  const debugReset = useDebugStore((s) => s.reset)
  const [isSaving, setIsSaving] = useState(false)

  const createNewWorkflow = () => {
    workflowApi
      .create({ name: '未命名工作流', graph: createDefaultGraph() })
      .then((wf) => {
        setWorkflow(wf.id, wf.name, wf.graph.nodes, wf.graph.edges)
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
          <span className="text-slate-500 text-sm hidden sm:inline">可视化工作流编排平台</span>
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
              <button
                onClick={createNewWorkflow}
                className="bg-slate-800 text-white text-xs px-3 py-1.5 rounded-md hover:bg-slate-700"
              >
                ➕ 新建
              </button>
              <button
                onClick={handleSave}
                disabled={isSaving || !workflowId}
                className="bg-slate-700 text-white text-xs px-3 py-1.5 rounded-md hover:bg-slate-600 disabled:opacity-50"
              >
                {isSaving ? '保存中...' : '💾 保存'}
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
