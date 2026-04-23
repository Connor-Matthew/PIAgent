import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { NodeType } from '../../types/workflow'
import { type WorkflowMeta, useWorkflowStore } from '../../stores/workflowStore'
import { workflowApi } from '../../services/api'
import { getApiErrorMessage } from '../../utils/apiErrors'
import { WorkflowDeleteDialog } from './WorkflowDeleteDialog'

const NODE_GROUPS = [
  {
    label: '基础节点',
    items: [
      { type: 'start' as NodeType, icon: '入', label: '用户输入', color: 'bg-gray-800' },
      { type: 'end' as NodeType, icon: '⏹', label: '结束', color: 'bg-gray-500' },
    ],
  },
  {
    label: '控制流',
    items: [
      { type: 'if_else' as NodeType, icon: '◈', label: 'If-Else 分支', color: 'bg-gray-700' },
      { type: 'iteration' as NodeType, icon: '↻', label: 'Iteration 循环', color: 'bg-gray-700' },
    ],
  },
  {
    label: '大模型',
    items: [
      { type: 'llm' as NodeType, icon: '🧠', label: 'LLM 对话', color: 'bg-gray-900' },
    ],
  },
  {
    label: '工具',
    items: [
      { type: 'rag' as NodeType, icon: '📚', label: 'RAG 知识检索', color: 'bg-gray-600' },
      { type: 'tts' as NodeType, icon: '🎙', label: 'TTS 音频合成', color: 'bg-gray-600' },
    ],
  },
]

export function NodeLibrary() {
  const navigate = useNavigate()
  const workflows = useWorkflowStore((s) => s.workflows)
  const workflowId = useWorkflowStore((s) => s.workflowId)
  const openTab = useWorkflowStore((s) => s.openTab)
  const removeWorkflowMeta = useWorkflowStore((s) => s.removeWorkflowMeta)
  const closeTab = useWorkflowStore((s) => s.closeTab)
  const [pendingDelete, setPendingDelete] = useState<WorkflowMeta | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  const onDragStart = (event: React.DragEvent, nodeType: NodeType) => {
    event.dataTransfer.setData('application/piagent-node', nodeType)
    event.dataTransfer.effectAllowed = 'move'
  }

  const handleOpenWorkflow = (id: string) => {
    openTab(id)
    navigate(`/workflow/${id}`)
  }

  const handleRequestDelete = (e: React.MouseEvent, id: string, name: string) => {
    e.stopPropagation()
    setDeleteError(null)
    setPendingDelete({ id, name })
  }

  const handleConfirmDelete = async () => {
    if (!pendingDelete) return
    const target = pendingDelete
    setIsDeleting(true)
    try {
      await workflowApi.delete(target.id)
      setPendingDelete(null)
    } catch (error) {
      setPendingDelete(null)
      setDeleteError(getApiErrorMessage(error, '删除失败，请稍后重试。'))
      return
    } finally {
      setIsDeleting(false)
    }

    const fallback = closeTab(target.id)
    removeWorkflowMeta(target.id)
    if (workflowId === target.id) {
      if (fallback) navigate(`/workflow/${fallback}`)
      else navigate('/')
    }
  }

  return (
    <div className="w-[220px] bg-white border-r border-gray-200 p-4 overflow-y-auto shrink-0">
      <div className="text-xs text-gray-400 uppercase tracking-wider mb-3">节点库</div>
      {NODE_GROUPS.map((group) => (
        <div key={group.label} className="mb-4">
          <div className="text-xs text-gray-500 mb-1.5">{group.label}</div>
          {group.items.map((item) => (
            <div
              key={item.type}
              draggable
              onDragStart={(e) => onDragStart(e, item.type)}
              className="bg-white border border-gray-200 p-2.5 mb-1.5 flex items-center gap-2 cursor-grab active:cursor-grabbing hover:border-black"
            >
              <span className={`${item.color} text-white w-6 h-6 flex items-center justify-center text-xs`}>
                {item.icon}
              </span>
              <span className="text-gray-900 text-sm">{item.label}</span>
            </div>
          ))}
        </div>
      ))}

      <div className="mt-2 pt-4 border-t border-gray-200">
        <div className="text-xs text-gray-400 uppercase tracking-wider mb-2">我的工作流</div>
        {workflows.length === 0 ? (
          <div className="text-xs text-gray-400 px-1">暂无工作流</div>
        ) : (
          workflows.map((wf) => {
            const active = wf.id === workflowId
            return (
              <div
                key={wf.id}
                onClick={() => handleOpenWorkflow(wf.id)}
                className={`group flex items-center justify-between gap-1 px-2 py-1.5 mb-0.5 cursor-pointer text-sm ${
                  active ? 'bg-gray-100 text-black' : 'text-gray-700 hover:bg-gray-50'
                }`}
              >
                <span className="truncate flex-1" title={wf.name}>{wf.name}</span>
                <button
                  onClick={(e) => handleRequestDelete(e, wf.id, wf.name)}
                  className="opacity-0 group-hover:opacity-60 hover:!opacity-100 hover:text-red-500 text-xs w-4 h-4 flex items-center justify-center shrink-0"
                  aria-label="删除工作流"
                  title="删除"
                >
                  ×
                </button>
              </div>
            )
          })
        )}
      </div>

      {pendingDelete && (
        <WorkflowDeleteDialog
          mode="confirm"
          workflowName={pendingDelete.name}
          isDeleting={isDeleting}
          onCancel={() => setPendingDelete(null)}
          onConfirm={handleConfirmDelete}
        />
      )}

      {deleteError && (
        <WorkflowDeleteDialog
          mode="error"
          errorMessage={deleteError}
          onClose={() => setDeleteError(null)}
        />
      )}
    </div>
  )
}
