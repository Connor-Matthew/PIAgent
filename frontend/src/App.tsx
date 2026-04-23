import { useEffect } from 'react'
import {
  BrowserRouter,
  Routes,
  Route,
  Link,
  useLocation,
  useParams,
  useNavigate,
  Navigate,
} from 'react-router-dom'
import { ReactFlowProvider } from 'reactflow'
import { NodeLibrary } from './components/panels/NodeLibrary'
import { WorkflowCanvas } from './components/canvas/WorkflowCanvas'
import { RightPanel } from './components/panels/RightPanel'
import { WorkflowTabs } from './components/panels/WorkflowTabs'
import {
  useWorkflowStore,
  createDefaultGraph,
  type SaveStatus,
} from './stores/workflowStore'
import { useDebugStore } from './stores/debugStore'
import { workflowApi } from './services/api'
import { useAutoSave } from './hooks/useAutoSave'
import ProvidersPage from './pages/Providers'

function SaveStatusIndicator({ status }: { status: SaveStatus }) {
  const label: Record<SaveStatus, { text: string; color: string }> = {
    idle: { text: '', color: 'text-gray-400' },
    dirty: { text: '未保存', color: 'text-gray-500' },
    saving: { text: '保存中…', color: 'text-gray-500' },
    saved: { text: '已保存', color: 'text-green-600' },
    error: { text: '保存失败', color: 'text-red-500' },
  }
  const { text, color } = label[status]
  if (!text) return null
  return <span className={`text-xs ${color}`}>{text}</span>
}

function WorkflowRoute() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const workflowId = useWorkflowStore((s) => s.workflowId)
  const setWorkflow = useWorkflowStore((s) => s.setWorkflow)
  const openTab = useWorkflowStore((s) => s.openTab)
  const upsertWorkflowMeta = useWorkflowStore((s) => s.upsertWorkflowMeta)
  const setSaveStatus = useWorkflowStore((s) => s.setSaveStatus)
  const debugReset = useDebugStore((s) => s.reset)

  useAutoSave()

  useEffect(() => {
    if (!id) return
    if (workflowId === id) return

    let cancelled = false
    setSaveStatus('idle')
    workflowApi
      .get(id)
      .then((wf) => {
        if (cancelled) return
        setWorkflow(wf.id, wf.name, wf.graph.nodes, wf.graph.edges)
        upsertWorkflowMeta({ id: wf.id, name: wf.name })
        openTab(wf.id)
        debugReset()
      })
      .catch(() => {
        if (cancelled) return
        navigate('/', { replace: true })
      })

    return () => {
      cancelled = true
    }
  }, [id, workflowId, setWorkflow, openTab, upsertWorkflowMeta, setSaveStatus, debugReset, navigate])

  return (
    <div className="flex flex-1 overflow-hidden">
      <WorkflowCanvas />
      <RightPanel />
    </div>
  )
}

function WorkflowIndex() {
  const navigate = useNavigate()
  const openTabIds = useWorkflowStore((s) => s.openTabIds)
  const workflows = useWorkflowStore((s) => s.workflows)
  const upsertWorkflowMeta = useWorkflowStore((s) => s.upsertWorkflowMeta)
  const openTab = useWorkflowStore((s) => s.openTab)

  useEffect(() => {
    const lastOpen = openTabIds[openTabIds.length - 1]
    if (lastOpen && workflows.some((w) => w.id === lastOpen)) {
      navigate(`/workflow/${lastOpen}`, { replace: true })
      return
    }
    if (workflows.length > 0) {
      navigate(`/workflow/${workflows[0].id}`, { replace: true })
      return
    }
    workflowApi
      .create({ name: '未命名工作流', graph: createDefaultGraph() })
      .then((wf) => {
        upsertWorkflowMeta({ id: wf.id, name: wf.name })
        openTab(wf.id)
        navigate(`/workflow/${wf.id}`, { replace: true })
      })
  }, [openTabIds, workflows, navigate, upsertWorkflowMeta, openTab])

  return <div className="flex-1" />
}

function WorkflowShell() {
  const setWorkflows = useWorkflowStore((s) => s.setWorkflows)

  useEffect(() => {
    workflowApi.list().then((list) => {
      setWorkflows(list.map((w) => ({ id: w.id, name: w.name })))
    })
  }, [setWorkflows])

  return (
    <div className="flex flex-1 overflow-hidden">
      <NodeLibrary />
      <div className="flex flex-col flex-1 overflow-hidden">
        <WorkflowTabs />
        <Routes>
          <Route path="/workflow/:id" element={<WorkflowRoute />} />
          <Route path="/" element={<WorkflowIndex />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </div>
  )
}

function AppContent() {
  const location = useLocation()
  const isProviders = location.pathname === '/providers'
  const isWorkflow = !isProviders

  const workflowName = useWorkflowStore((s) => s.workflowName)
  const workflowId = useWorkflowStore((s) => s.workflowId)
  const saveStatus = useWorkflowStore((s) => s.saveStatus)

  return (
    <div className="h-screen flex flex-col">
      <header className="bg-white border-b border-black px-4 py-2 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-4">
          <Link to="/" className="text-black font-bold text-lg hover:text-gray-600">
            PIAgent
          </Link>
          <span className="text-gray-500 text-sm hidden sm:inline">可视化工作流编排平台</span>
          <nav className="flex items-center gap-2 ml-4 border-l border-gray-300 pl-4">
            <Link
              to="/"
              className={`text-xs px-3 py-1.5 transition-colors ${
                isWorkflow
                  ? 'bg-black text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200 hover:text-black'
              }`}
            >
              工作流
            </Link>
            <Link
              to="/providers"
              className={`text-xs px-3 py-1.5 transition-colors ${
                isProviders
                  ? 'bg-black text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200 hover:text-black'
              }`}
            >
              Providers
            </Link>
          </nav>
        </div>
        <div className="flex items-center gap-3">
          {isWorkflow && workflowId && (
            <>
              <span className="text-gray-600 text-sm">{workflowName}</span>
              <SaveStatusIndicator status={saveStatus} />
            </>
          )}
        </div>
      </header>

      <Routes>
        <Route
          path="/providers"
          element={
            <div className="flex-1 overflow-auto">
              <ProvidersPage />
            </div>
          }
        />
        <Route
          path="*"
          element={
            <ReactFlowProvider>
              <WorkflowShell />
            </ReactFlowProvider>
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
