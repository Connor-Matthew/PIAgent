import { ReactFlowProvider } from 'reactflow'
import { NodeLibrary } from './components/panels/NodeLibrary'
import { WorkflowCanvas } from './components/canvas/WorkflowCanvas'
import { NodeConfig } from './components/panels/NodeConfig'
import { DebugDrawer } from './components/debug/DebugDrawer'

export default function App() {
  return (
    <ReactFlowProvider>
      <div className="h-screen flex flex-col">
        {/* Header */}
        <header className="bg-slate-900 border-b border-slate-800 px-4 py-2 flex items-center gap-3 shrink-0">
          <span className="text-blue-400 font-bold text-lg">PIAgent</span>
          <span className="text-slate-500 text-sm">AI Agent 工作流编排平台</span>
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
