import { useNavigate } from 'react-router-dom'
import { useWorkflowStore, createDefaultGraph } from '../../stores/workflowStore'
import { workflowApi } from '../../services/api'

export function WorkflowTabs() {
  const navigate = useNavigate()
  const workflowId = useWorkflowStore((s) => s.workflowId)
  const workflows = useWorkflowStore((s) => s.workflows)
  const openTabIds = useWorkflowStore((s) => s.openTabIds)
  const closeTab = useWorkflowStore((s) => s.closeTab)
  const upsertWorkflowMeta = useWorkflowStore((s) => s.upsertWorkflowMeta)
  const openTab = useWorkflowStore((s) => s.openTab)

  const workflowMap = new Map(workflows.map((w) => [w.id, w]))

  const handleCloseTab = (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    const fallback = closeTab(id)
    if (workflowId === id) {
      if (fallback) {
        navigate(`/workflow/${fallback}`)
      } else {
        navigate('/')
      }
    }
  }

  const handleCreate = async () => {
    const wf = await workflowApi.create({
      name: '未命名工作流',
      graph: createDefaultGraph(),
    })
    upsertWorkflowMeta({ id: wf.id, name: wf.name })
    openTab(wf.id)
    navigate(`/workflow/${wf.id}`)
  }

  return (
    <div className="flex items-center bg-white border-b border-gray-200 h-9 shrink-0 overflow-x-auto">
      {openTabIds.map((id) => {
        const meta = workflowMap.get(id)
        if (!meta) return null
        const active = workflowId === id
        return (
          <div
            key={id}
            onClick={() => navigate(`/workflow/${id}`)}
            className={`group flex items-center gap-2 px-3 h-full border-r border-gray-200 text-xs cursor-pointer select-none ${
              active ? 'bg-gray-100 text-black' : 'text-gray-600 hover:bg-gray-50'
            }`}
          >
            <span className="max-w-[160px] truncate">{meta.name}</span>
            <button
              onClick={(e) => handleCloseTab(e, id)}
              className="opacity-40 hover:opacity-100 hover:text-red-500 text-xs w-4 h-4 flex items-center justify-center"
              aria-label="关闭标签"
            >
              ×
            </button>
          </div>
        )
      })}
      <button
        onClick={handleCreate}
        className="px-3 h-full text-xs text-gray-500 hover:bg-gray-50 hover:text-black"
        aria-label="新建工作流"
      >
        +
      </button>
    </div>
  )
}
