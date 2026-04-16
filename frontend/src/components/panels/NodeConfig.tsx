import { useCallback, useEffect, useRef, useState } from 'react'
import { useWorkflowStore } from '../../stores/workflowStore'
import type { EndOutputField, InputFieldType, NodeType, StartInputField } from '../../types/workflow'
import { providerApi } from '../../services/api'
import type { Provider } from '../../types/provider'

const NODE_OUTPUT_FIELDS: Record<NodeType, string[]> = {
  start: [], // dynamic
  llm: ['text'],
  rag: ['context', 'documents'],
  agent: ['text', 'steps'],
  tts: ['audio_url', 'duration'],
  end: [],
}

const NODE_REFERENCE_PATTERN = /^\{\{([^\s.]+)\./
const NODE_FIELD_REFERENCE_PATTERN = /^\{\{([^\s.]+)\.([^\s}]+)\}\}$/

export function NodeConfig() {
  const { nodes, selectedNodeId, updateNodeData } = useWorkflowStore()
  const selectedNode = nodes.find((n) => n.id === selectedNodeId)

  if (!selectedNode) {
    return (
      <div className="h-full flex flex-col p-4">
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

  const updateConfigBatch = (patch: Record<string, unknown>) => {
    updateNodeData(selectedNode.id, {
      config: { ...config, ...patch },
    })
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="text-xs text-slate-500 uppercase tracking-wider mb-4">节点配置</div>
      <div className="text-sm text-slate-200 font-semibold mb-4 flex items-center gap-2">
        {data.label}
        {data.locked && <span className="text-[10px] bg-slate-700 text-slate-300 px-1.5 py-0.5 rounded">锁定</span>}
      </div>

      {data.nodeType === 'start' && (
        <StartNodeConfig config={config} updateConfig={updateConfig} />
      )}

      {data.nodeType === 'end' && (
        <EndNodeConfig config={config} updateConfig={updateConfig} currentNodeId={selectedNode.id} />
      )}

      {data.nodeType === 'llm' && (
        <LlmNodeConfig config={config} updateConfig={updateConfig} updateConfigBatch={updateConfigBatch} />
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
        <TtsNodeConfig config={config} updateConfig={updateConfig} updateConfigBatch={updateConfigBatch} />
      )}

      {data.nodeType === 'agent' && (
        <AgentNodeConfig config={config} updateConfig={updateConfig} updateConfigBatch={updateConfigBatch} />
      )}
    </div>
  )
}

function StartNodeConfig({
  config,
  updateConfig,
}: {
  config: Record<string, unknown>
  updateConfig: (key: string, value: unknown) => void
}) {
  const inputs = (config.inputs as StartInputField[]) || []

  const addField = () => {
    updateConfig('inputs', [
      ...inputs,
      { name: `field_${inputs.length + 1}`, type: 'text', required: false },
    ])
  }

  const removeField = (idx: number) => {
    const next = [...inputs]
    next.splice(idx, 1)
    updateConfig('inputs', next)
  }

  const updateField = (idx: number, patch: Partial<StartInputField>) => {
    const next = [...inputs]
    next[idx] = { ...next[idx], ...patch }
    updateConfig('inputs', next)
  }

  return (
    <div className="space-y-4">
      <div className="text-xs text-slate-400">输入字段配置</div>
      {inputs.map((field, idx) => (
        <div key={idx} className="bg-slate-800 border border-slate-700 rounded-md p-2.5 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-500">字段 {idx + 1}</span>
            <button
              onClick={() => removeField(idx)}
              className="text-[10px] text-red-400 hover:text-red-300"
            >
              删除
            </button>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="text-[10px] text-slate-400 block">名称</span>
              <input
                value={field.name}
                onChange={(e) => updateField(idx, { name: e.target.value })}
                className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200"
              />
            </label>
            <label className="block">
              <span className="text-[10px] text-slate-400 block">类型</span>
              <select
                value={field.type}
                onChange={(e) => updateField(idx, { type: e.target.value as InputFieldType })}
                className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200"
              >
                <option value="text">文本</option>
                <option value="number">数字</option>
                <option value="select">下拉</option>
                <option value="file">文件</option>
              </select>
            </label>
          </div>
          {field.type === 'select' && (
            <label className="block">
              <span className="text-[10px] text-slate-400 block">选项（逗号分隔）</span>
              <input
                value={(field.options || []).join(',')}
                onChange={(e) => updateField(idx, { options: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })}
                className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200"
              />
            </label>
          )}
          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="text-[10px] text-slate-400 block">默认值</span>
              <input
                value={(field.default as string | number) ?? ''}
                onChange={(e) => updateField(idx, { default: e.target.value })}
                className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200"
              />
            </label>
            <label className="flex items-center gap-2 pt-4">
              <input
                type="checkbox"
                checked={!!field.required}
                onChange={(e) => updateField(idx, { required: e.target.checked })}
                className="rounded border-slate-600"
              />
              <span className="text-[10px] text-slate-400">必填</span>
            </label>
          </div>
        </div>
      ))}
      <button
        onClick={addField}
        className="w-full py-1.5 text-xs border border-dashed border-slate-600 text-slate-400 rounded hover:border-slate-500 hover:text-slate-300"
      >
        + 添加输入字段
      </button>
    </div>
  )
}

function EndNodeConfig({
  config,
  updateConfig,
  currentNodeId,
}: {
  config: Record<string, unknown>
  updateConfig: (key: string, value: unknown) => void
  currentNodeId: string
}) {
  const { nodes } = useWorkflowStore()
  const outputs = (config.outputs as EndOutputField[]) || []
  const answer = (config.answer as string) || ''
  const answerRef = useRef<HTMLTextAreaElement>(null)

  const upstreamNodes = nodes.filter((n) => n.id !== currentNodeId && n.data.nodeType !== 'end')

  const getNodeFields = (nodeType: string, nodeId: string): string[] => {
    if (nodeType === 'start') {
      const startInputs = (nodes.find((n) => n.id === nodeId)?.data.config.inputs as StartInputField[]) || []
      return startInputs.map((i) => i.name)
    }
    return NODE_OUTPUT_FIELDS[nodeType as keyof typeof NODE_OUTPUT_FIELDS] || []
  }

  const addOutput = () => {
    updateConfig('outputs', [
      ...outputs,
      { name: `out_${outputs.length + 1}`, source: 'input', value: '' },
    ])
  }

  const removeOutput = (idx: number) => {
    const next = [...outputs]
    next.splice(idx, 1)
    updateConfig('outputs', next)
  }

  const updateOutput = (idx: number, patch: Partial<EndOutputField>) => {
    const next = [...outputs]
    next[idx] = { ...next[idx], ...patch }
    updateConfig('outputs', next)
  }

  const insertAtCursor = (text: string) => {
    const el = answerRef.current
    if (!el) return
    const start = el.selectionStart
    const end = el.selectionEnd
    const newValue = answer.slice(0, start) + text + answer.slice(end)
    updateConfig('answer', newValue)
    setTimeout(() => {
      el.selectionStart = el.selectionEnd = start + text.length
      el.focus()
    }, 0)
  }

  const localVars = outputs.map((o) => o.name)

  return (
    <div className="space-y-4">
      <div className="text-xs text-slate-400">输出变量配置</div>
      {outputs.map((out, idx) => (
        <div key={idx} className="bg-slate-800 border border-slate-700 rounded-md p-2.5 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-500">变量 {idx + 1}</span>
            <button
              onClick={() => removeOutput(idx)}
              className="text-[10px] text-red-400 hover:text-red-300"
            >
              删除
            </button>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="text-[10px] text-slate-400 block">参数名</span>
              <input
                value={out.name}
                onChange={(e) => updateOutput(idx, { name: e.target.value })}
                className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200"
              />
            </label>
            <label className="block">
              <span className="text-[10px] text-slate-400 block">类型</span>
              <select
                value={out.source}
                onChange={(e) =>
                  updateOutput(idx, { source: e.target.value as EndOutputField['source'], value: '' })
                }
                className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200"
              >
                <option value="input">输入（字面量）</option>
                <option value="reference">引用</option>
              </select>
            </label>
          </div>
          {out.source === 'reference' ? (
            <div className="grid grid-cols-[1fr,1fr] gap-2">
              <select
                value={(() => {
                  const m = out.value.match(NODE_REFERENCE_PATTERN)
                  return m ? m[1] : ''
                })()}
                onChange={(e) => {
                  const nodeId = e.target.value
                  if (!nodeId) return
                  const node = upstreamNodes.find((n) => n.id === nodeId)
                  if (!node) return
                  const fields = getNodeFields(node.data.nodeType, nodeId)
                  const field = fields[0] || ''
                  updateOutput(idx, { value: `{{${nodeId}.${field}}}` })
                }}
                className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200"
              >
                <option value="">选择节点</option>
                {upstreamNodes.map((n) => (
                  <option key={n.id} value={n.id}>
                    {n.data.label} ({n.id})
                  </option>
                ))}
              </select>
              <select
                value={(() => {
                  const m = out.value.match(NODE_FIELD_REFERENCE_PATTERN)
                  return m ? m[2] : ''
                })()}
                onChange={(e) => {
                  const nodeIdMatch = out.value.match(NODE_REFERENCE_PATTERN)
                  const nodeId = nodeIdMatch ? nodeIdMatch[1] : ''
                  if (!nodeId) return
                  updateOutput(idx, { value: `{{${nodeId}.${e.target.value}}}` })
                }}
                className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200"
              >
                <option value="">选择字段</option>
                {(() => {
                  const nodeIdMatch = out.value.match(NODE_REFERENCE_PATTERN)
                  const nodeId = nodeIdMatch ? nodeIdMatch[1] : ''
                  const node = upstreamNodes.find((n) => n.id === nodeId)
                  if (!node) return null
                  return getNodeFields(node.data.nodeType, nodeId).map((f) => (
                    <option key={f} value={f}>{f}</option>
                  ))
                })()}
              </select>
            </div>
          ) : (
            <input
              value={out.value}
              onChange={(e) => updateOutput(idx, { value: e.target.value })}
              placeholder="字面量值"
              className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200"
            />
          )}
        </div>
      ))}
      <button
        onClick={addOutput}
        className="w-full py-1.5 text-xs border border-dashed border-slate-600 text-slate-400 rounded hover:border-slate-500 hover:text-slate-300"
      >
        + 添加输出变量
      </button>

      <div className="pt-2 border-t border-slate-800">
        <div className="text-xs text-slate-400 mb-2">回答内容模板</div>
        <textarea
          ref={answerRef}
          value={answer}
          onChange={(e) => updateConfig('answer', e.target.value)}
          rows={4}
          placeholder="例如：🎧 {{title}} 已生成，链接：{{audio_url}}"
          className="w-full bg-slate-900 border border-slate-700 rounded-md px-2 py-1.5 text-sm text-slate-200 resize-none"
        />
        <div className="mt-2 flex flex-wrap gap-2">
          <span className="text-[10px] text-slate-500 self-center">插入：</span>
          {localVars.length > 0 && (
            <>
              {localVars.map((v) => (
                <button
                  key={v}
                  onClick={() => insertAtCursor(`{{${v}}}`)}
                  className="text-[10px] bg-blue-500/20 text-blue-300 px-1.5 py-0.5 rounded hover:bg-blue-500/30"
                >
                  {`{{${v}}}`}
                </button>
              ))}
            </>
          )}
          {upstreamNodes.map((n) =>
            getNodeFields(n.data.nodeType, n.id).map((f) => (
              <button
                key={`${n.id}.${f}`}
                onClick={() => insertAtCursor(`{{${n.id}.${f}}}`)}
                className="text-[10px] bg-slate-700 text-slate-300 px-1.5 py-0.5 rounded hover:bg-slate-600"
              >
                {`{{${n.id}.${f}}}`}
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  )
}


function useProviders() {
  const [providers, setProviders] = useState<Provider[]>([])
  useEffect(() => {
    providerApi.list().then((list) => {
      setProviders(list.filter((p) => p.enabled))
    }).catch(() => setProviders([]))
  }, [])
  return providers
}

function useProviderModels(providerId: number | undefined) {
  const [models, setModels] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const load = useCallback(async (refresh = false) => {
    if (!providerId) {
      setModels([])
      return
    }
    setLoading(true)
    try {
      const res = await providerApi.models(providerId, refresh)
      const available = res.selected_models?.length ? res.selected_models : (res.models || [])
      setModels(available)
    } catch {
      setModels([])
    } finally {
      setLoading(false)
    }
  }, [providerId])
  useEffect(() => {
    void load()
  }, [load])
  return { models, loading, refresh: () => load(true) }
}

function LlmNodeConfig({
  config,
  updateConfig,
  updateConfigBatch,
}: {
  config: Record<string, unknown>
  updateConfig: (key: string, value: unknown) => void
  updateConfigBatch: (patch: Record<string, unknown>) => void
}) {
  const providers = useProviders()
  const providerId = config.provider_id as number | undefined
  const { models, loading, refresh } = useProviderModels(providerId)

  const handleProviderChange = (id: number | undefined) => {
    updateConfigBatch({ provider_id: id, model: '' })
  }

  const hasModels = models.length > 0

  return (
    <>
      <label className="block mb-3">
        <span className="text-xs text-slate-400 block mb-1">Provider 实例</span>
        <select
          value={providerId != null ? String(providerId) : ''}
          onChange={(e) => {
            const val = e.target.value ? parseInt(e.target.value, 10) : undefined
            handleProviderChange(val)
          }}
          className="w-full bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5 text-sm text-slate-200"
        >
          <option value="">请选择 Provider</option>
          {providers.map((p) => (
            <option key={p.id} value={String(p.id)}>
              {p.name} ({p.type})
            </option>
          ))}
        </select>
      </label>

      <label className="block mb-3">
        <span className="text-xs text-slate-400 block mb-1">模型</span>
        <div className="flex items-center gap-2">
          {hasModels ? (
            <select
              value={(config.model as string) || ''}
              onChange={(e) => updateConfig('model', e.target.value)}
              disabled={!providerId || loading}
              className="flex-1 bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5 text-sm text-slate-200 disabled:opacity-50"
            >
              <option value="">{loading ? '加载中...' : '请选择模型'}</option>
              {models.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          ) : (
            <input
              value={(config.model as string) || ''}
              onChange={(e) => updateConfig('model', e.target.value)}
              disabled={!providerId}
              placeholder={providerId ? (loading ? '加载中...' : '无可用模型，手动输入') : '请先选择 Provider'}
              className="flex-1 bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5 text-sm text-slate-200 disabled:opacity-50"
            />
          )}
          <button
            type="button"
            onClick={refresh}
            disabled={!providerId || loading}
            title="刷新模型列表"
            className="px-2 py-1.5 text-sm border border-slate-600 rounded-md hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            🔄
          </button>
        </div>
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
  )
}

function TtsNodeConfig({
  config,
  updateConfig,
  updateConfigBatch,
}: {
  config: Record<string, unknown>
  updateConfig: (key: string, value: unknown) => void
  updateConfigBatch: (patch: Record<string, unknown>) => void
}) {
  const [ttsProviders, setTtsProviders] = useState<Provider[]>([])
  useEffect(() => {
    providerApi.list('tts').then((list) => {
      setTtsProviders(list.filter((p) => p.enabled))
    }).catch(() => setTtsProviders([]))
  }, [])

  const providerId = config.provider_id as number | undefined
  const selectedProvider = ttsProviders.find((p) => p.id === providerId)
  const isMiniMax = selectedProvider?.type === 'minimax_tts'

  const minimaxModels = ['speech-2.8-hd', 'speech-2.5-hd']
  const emotions = ['happy', 'sad', 'angry', 'neutral']

  return (
    <>
      <label className="block mb-3">
        <span className="text-xs text-slate-400 block mb-1">Provider 实例</span>
        <select
          value={providerId != null ? String(providerId) : ''}
          onChange={(e) => {
            const val = e.target.value ? parseInt(e.target.value, 10) : undefined
            const provider = ttsProviders.find((p) => p.id === val)
            updateConfigBatch({
              provider_id: val,
              model: provider?.type === 'minimax_tts' ? 'speech-2.8-hd' : '',
            })
          }}
          className="w-full bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5 text-sm text-slate-200"
        >
          <option value="">请选择 Provider</option>
          {ttsProviders.map((p) => (
            <option key={p.id} value={String(p.id)}>
              {p.name} ({p.type})
            </option>
          ))}
        </select>
      </label>

      {isMiniMax && (
        <label className="block mb-3">
          <span className="text-xs text-slate-400 block mb-1">模型</span>
          <select
            value={(config.model as string) || 'speech-2.8-hd'}
            onChange={(e) => updateConfig('model', e.target.value)}
            className="w-full bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5 text-sm text-slate-200"
          >
            {minimaxModels.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </label>
      )}

      <label className="block mb-3">
        <span className="text-xs text-slate-400 block mb-1">音色 ID (voice_id)</span>
        <input
          value={(config.voice_id as string) || ''}
          onChange={(e) => updateConfig('voice_id', e.target.value)}
          placeholder={isMiniMax ? '例如 male-qn-qingse' : '例如 default'}
          className="w-full bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5 text-sm text-slate-200"
        />
      </label>

      {isMiniMax && (
        <>
          <label className="block mb-3">
            <span className="text-xs text-slate-400 block mb-1">情感</span>
            <select
              value={(config.emotion as string) || 'happy'}
              onChange={(e) => updateConfig('emotion', e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5 text-sm text-slate-200"
            >
              {emotions.map((em) => (
                <option key={em} value={em}>{em}</option>
              ))}
            </select>
          </label>

          <label className="block mb-3">
            <span className="text-xs text-slate-400 block mb-1">
              语速: {((config.speed as number) ?? 1.0).toFixed(1)}
            </span>
            <input
              type="range"
              min={0.5}
              max={2.0}
              step={0.1}
              value={(config.speed as number) ?? 1.0}
              onChange={(e) => updateConfig('speed', parseFloat(e.target.value))}
              className="w-full"
            />
          </label>
        </>
      )}
    </>
  )
}

function AgentNodeConfig({
  config,
  updateConfig,
  updateConfigBatch,
}: {
  config: Record<string, unknown>
  updateConfig: (key: string, value: unknown) => void
  updateConfigBatch: (patch: Record<string, unknown>) => void
}) {
  const providers = useProviders()
  const providerId = config.provider_id as number | undefined
  const { models, loading, refresh } = useProviderModels(providerId)

  const handleProviderChange = (id: number | undefined) => {
    updateConfigBatch({ provider_id: id, model: '' })
  }

  const hasModels = models.length > 0

  return (
    <>
      <label className="block mb-3">
        <span className="text-xs text-slate-400 block mb-1">Provider 实例</span>
        <select
          value={providerId != null ? String(providerId) : ''}
          onChange={(e) => {
            const val = e.target.value ? parseInt(e.target.value, 10) : undefined
            handleProviderChange(val)
          }}
          className="w-full bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5 text-sm text-slate-200"
        >
          <option value="">请选择 Provider</option>
          {providers.map((p) => (
            <option key={p.id} value={String(p.id)}>
              {p.name} ({p.type})
            </option>
          ))}
        </select>
      </label>

      <label className="block mb-3">
        <span className="text-xs text-slate-400 block mb-1">模型</span>
        <div className="flex items-center gap-2">
          {hasModels ? (
            <select
              value={(config.model as string) || ''}
              onChange={(e) => updateConfig('model', e.target.value)}
              disabled={!providerId || loading}
              className="flex-1 bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5 text-sm text-slate-200 disabled:opacity-50"
            >
              <option value="">{loading ? '加载中...' : '请选择模型'}</option>
              {models.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          ) : (
            <input
              value={(config.model as string) || ''}
              onChange={(e) => updateConfig('model', e.target.value)}
              disabled={!providerId}
              placeholder={providerId ? (loading ? '加载中...' : '无可用模型，手动输入') : '请先选择 Provider'}
              className="flex-1 bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5 text-sm text-slate-200 disabled:opacity-50"
            />
          )}
          <button
            type="button"
            onClick={refresh}
            disabled={!providerId || loading}
            title="刷新模型列表"
            className="px-2 py-1.5 text-sm border border-slate-600 rounded-md hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            🔄
          </button>
        </div>
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
  )
}
