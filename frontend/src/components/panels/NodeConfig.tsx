import { useWorkflowStore } from '../../stores/workflowStore'

export function NodeConfig() {
  const { nodes, selectedNodeId, updateNodeData } = useWorkflowStore()
  const selectedNode = nodes.find((n) => n.id === selectedNodeId)

  if (!selectedNode) {
    return (
      <div className="w-[260px] bg-slate-900 border-l border-slate-800 p-4 shrink-0">
        <div className="text-xs text-slate-500 uppercase tracking-wider mb-4">节点配置</div>
        <div className="text-sm text-slate-600 text-center mt-8">选择一个节点查看配置</div>
      </div>
    )
  }

  const { data } = selectedNode
  const config = data.config as Record<string, unknown>

  const updateConfig = (key: string, value: unknown) => {
    updateNodeData(selectedNode.id, {
      config: { ...config, [key]: value },
    })
  }

  return (
    <div className="w-[260px] bg-slate-900 border-l border-slate-800 p-4 shrink-0 overflow-y-auto">
      <div className="text-xs text-slate-500 uppercase tracking-wider mb-4">节点配置</div>
      <div className="text-sm text-slate-200 font-semibold mb-4">{data.label}</div>

      {data.nodeType === 'llm' && (
        <>
          <label className="block mb-3">
            <span className="text-xs text-slate-400 block mb-1">模型提供商</span>
            <select
              value={(config.provider as string) || 'openai'}
              onChange={(e) => updateConfig('provider', e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5 text-sm text-slate-200"
            >
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
              <option value="google">Google</option>
              <option value="deepseek">DeepSeek</option>
            </select>
          </label>
          <label className="block mb-3">
            <span className="text-xs text-slate-400 block mb-1">模型</span>
            <input
              value={(config.model as string) || 'gpt-4o'}
              onChange={(e) => updateConfig('model', e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5 text-sm text-slate-200"
            />
          </label>
          <label className="block mb-3">
            <span className="text-xs text-slate-400 block mb-1">Temperature: {(config.temperature as number) ?? 0.7}</span>
            <input
              type="range" min="0" max="1" step="0.1"
              value={(config.temperature as number) ?? 0.7}
              onChange={(e) => updateConfig('temperature', parseFloat(e.target.value))}
              className="w-full"
            />
          </label>
          <label className="block mb-3">
            <span className="text-xs text-slate-400 block mb-1">System Prompt</span>
            <textarea
              value={(config.system_prompt as string) || ''}
              onChange={(e) => updateConfig('system_prompt', e.target.value)}
              rows={4}
              className="w-full bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5 text-sm text-slate-200 resize-none"
            />
          </label>
        </>
      )}

      {data.nodeType === 'rag' && (
        <>
          <label className="block mb-3">
            <span className="text-xs text-slate-400 block mb-1">知识库 ID</span>
            <input
              value={(config.knowledge_base_id as string) || ''}
              onChange={(e) => updateConfig('knowledge_base_id', e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5 text-sm text-slate-200"
            />
          </label>
          <label className="block mb-3">
            <span className="text-xs text-slate-400 block mb-1">Top-K: {(config.top_k as number) ?? 3}</span>
            <input
              type="range" min="1" max="10" step="1"
              value={(config.top_k as number) ?? 3}
              onChange={(e) => updateConfig('top_k', parseInt(e.target.value))}
              className="w-full"
            />
          </label>
        </>
      )}

      {data.nodeType === 'tts' && (
        <>
          <label className="block mb-3">
            <span className="text-xs text-slate-400 block mb-1">TTS 提供商</span>
            <select
              value={(config.provider as string) || 'fish_audio'}
              onChange={(e) => updateConfig('provider', e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5 text-sm text-slate-200"
            >
              <option value="fish_audio">Fish Audio</option>
            </select>
          </label>
          <label className="block mb-3">
            <span className="text-xs text-slate-400 block mb-1">音色 ID</span>
            <input
              value={(config.voice as string) || 'default'}
              onChange={(e) => updateConfig('voice', e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5 text-sm text-slate-200"
            />
          </label>
        </>
      )}

      {data.nodeType === 'agent' && (
        <>
          <label className="block mb-3">
            <span className="text-xs text-slate-400 block mb-1">模型提供商</span>
            <select
              value={(config.provider as string) || 'openai'}
              onChange={(e) => updateConfig('provider', e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5 text-sm text-slate-200"
            >
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
              <option value="google">Google</option>
              <option value="deepseek">DeepSeek</option>
            </select>
          </label>
          <label className="block mb-3">
            <span className="text-xs text-slate-400 block mb-1">System Prompt</span>
            <textarea
              value={(config.system_prompt as string) || ''}
              onChange={(e) => updateConfig('system_prompt', e.target.value)}
              rows={4}
              className="w-full bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5 text-sm text-slate-200 resize-none"
            />
          </label>
        </>
      )}
    </div>
  )
}
