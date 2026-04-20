import type { NodeType } from '../../types/workflow'

const NODE_GROUPS = [
  {
    label: '基础节点',
    items: [
      { type: 'start' as NodeType, icon: '入', label: '用户输入', color: 'bg-blue-500' },
      { type: 'end' as NodeType, icon: '⏹', label: '结束', color: 'bg-slate-500' },
    ],
  },
  {
    label: '控制流',
    items: [
      { type: 'if_else' as NodeType, icon: '◈', label: 'If-Else 分支', color: 'bg-amber-500' },
      { type: 'iteration' as NodeType, icon: '↻', label: 'Iteration 循环', color: 'bg-cyan-500' },
    ],
  },
  {
    label: '大模型',
    items: [
      { type: 'llm' as NodeType, icon: '🧠', label: 'LLM 对话', color: 'bg-purple-500' },
    ],
  },
  {
    label: '工具',
    items: [
      { type: 'rag' as NodeType, icon: '📚', label: 'RAG 知识检索', color: 'bg-green-500' },
      { type: 'tts' as NodeType, icon: '🎙', label: 'TTS 音频合成', color: 'bg-yellow-500' },
    ],
  },
]

export function NodeLibrary() {
  const onDragStart = (event: React.DragEvent, nodeType: NodeType) => {
    event.dataTransfer.setData('application/piagent-node', nodeType)
    event.dataTransfer.effectAllowed = 'move'
  }

  return (
    <div className="w-[220px] bg-slate-900 border-r border-slate-800 p-4 overflow-y-auto shrink-0">
      <div className="text-xs text-slate-500 uppercase tracking-wider mb-3">节点库</div>
      {NODE_GROUPS.map((group) => (
        <div key={group.label} className="mb-4">
          <div className="text-xs text-slate-600 mb-1.5">{group.label}</div>
          {group.items.map((item) => (
            <div
              key={item.type}
              draggable
              onDragStart={(e) => onDragStart(e, item.type)}
              className="bg-slate-800 border border-slate-700 rounded-lg p-2.5 mb-1.5 flex items-center gap-2 cursor-grab active:cursor-grabbing hover:border-slate-600"
            >
              <span className={`${item.color} text-white w-6 h-6 rounded flex items-center justify-center text-xs`}>
                {item.icon}
              </span>
              <span className="text-slate-200 text-sm">{item.label}</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}
