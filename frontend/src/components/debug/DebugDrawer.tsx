import { useMemo } from 'react'
import { useDebugStore } from '../../stores/debugStore'
import { useWorkflowStore } from '../../stores/workflowStore'
import { useSSE } from '../../hooks/useSSE'
import { workflowApi } from '../../services/api'
import { ExecutionTimeline } from './ExecutionTimeline'
import { AudioPlayer } from './AudioPlayer'
import type { StartInputField } from '../../types/workflow'

export function DebugDrawer() {
  const {
    isOpen, mode, isRunning, inputText, runInputs,
    finalAnswer, finalOutputs,
    toggleDrawer, setMode, setInputText, setRunInput, startRun,
  } = useDebugStore()
  const { workflowId, workflowName, nodes, toGraphJSON } = useWorkflowStore()
  const { connect } = useSSE()

  const startNode = useMemo(() => {
    return nodes.find((n) => n.data.nodeType === 'start')
  }, [nodes])

  const startInputs = useMemo<StartInputField[]>(() => {
    const config = startNode?.data.config || {}
    const raw = config.inputs
    return Array.isArray(raw) ? (raw as StartInputField[]) : []
  }, [startNode])

  if (!isOpen) return null

  const handleRun = async () => {
    if (!workflowId) return
    startRun()

    // Auto-save workflow before running
    try {
      await workflowApi.update(workflowId, {
        name: workflowName,
        graph: toGraphJSON(),
      })
    } catch (e) {
      // Continue running even if save fails
      console.warn('Auto-save failed:', e)
    }

    let payload: { input?: string; inputs?: Record<string, unknown> }
    if (startInputs.length > 0) {
      // Build inputs dict; include inputText as fallback "input" key
      const inputs: Record<string, unknown> = { ...runInputs }
      if (inputText.trim()) inputs.input = inputText.trim()
      payload = { inputs }
    } else {
      payload = { input: inputText.trim() }
    }

    const result = await workflowApi.run(workflowId, payload)
    connect(workflowId, result.run_id)
  }

  const canRun = startInputs.length > 0
    ? !isRunning && !!workflowId && startInputs.every((f) => !f.required || (runInputs[f.name] !== undefined && runInputs[f.name] !== ''))
    : !isRunning && !!workflowId && !!inputText.trim()

  return (
    <div className="border-t border-gray-200 bg-white shrink-0" style={{ height: '40vh' }}>
      {/* Header */}
      <div className="bg-gray-50 px-5 py-3 flex justify-between items-center border-b border-gray-200">
        <div className="flex items-center gap-3">
          <span className="text-gray-900 text-sm font-semibold">调试运行</span>
          <div className="flex gap-1">
            <button
              onClick={() => setMode('simple')}
              className={`text-xs px-2.5 py-1 ${mode === 'simple' ? 'bg-black text-white' : 'bg-white text-gray-500 border border-gray-200'}`}
            >
              简洁
            </button>
            <button
              onClick={() => setMode('detailed')}
              className={`text-xs px-2.5 py-1 ${mode === 'detailed' ? 'bg-black text-white' : 'bg-white text-gray-500 border border-gray-200'}`}
            >
              详细
            </button>
          </div>
        </div>
        <button onClick={toggleDrawer} className="text-gray-400 hover:text-gray-700 text-lg">✕</button>
      </div>

      {/* Body */}
      <div className="flex h-[calc(100%-48px)]">
        {/* Input Form */}
        <div className="w-[300px] p-4 border-r border-gray-200 overflow-y-auto">
          {startInputs.length === 0 ? (
            <>
              <div className="text-xs text-gray-500 mb-2">输入文本</div>
              <textarea
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                placeholder="请输入播客主题..."
                className="w-full bg-white border border-gray-200 p-3 text-sm text-gray-900 resize-none h-24 focus:border-black focus:outline-none"
              />
            </>
          ) : (
            <>
              <div className="text-xs text-gray-500 mb-2">工作流输入</div>
              <div className="space-y-3">
                {startInputs.map((field) => (
                  <label key={field.name} className="block">
                    <span className="text-xs text-gray-700 block mb-1">
                      {field.name}
                      {field.required && <span className="text-red-600 ml-1">*</span>}
                    </span>
                    {field.type === 'select' ? (
                      <select
                        value={(runInputs[field.name] as string) || (field.default as string) || ''}
                        onChange={(e) => setRunInput(field.name, e.target.value)}
                        className="w-full bg-white border border-gray-200 px-3 py-2 text-sm text-gray-900 focus:border-black focus:outline-none"
                      >
                        <option value="">请选择</option>
                        {(field.options || []).map((opt) => (
                          <option key={opt} value={opt}>{opt}</option>
                        ))}
                      </select>
                    ) : field.type === 'number' ? (
                      <input
                        type="number"
                        value={(runInputs[field.name] as number | string) ?? (field.default ?? '')}
                        onChange={(e) => setRunInput(field.name, e.target.value === '' ? '' : Number(e.target.value))}
                        className="w-full bg-white border border-gray-200 px-3 py-2 text-sm text-gray-900 focus:border-black focus:outline-none"
                      />
                    ) : (
                      <input
                        type={field.type === 'file' ? 'file' : 'text'}
                        value={field.type === 'file' ? undefined : ((runInputs[field.name] as string) ?? (field.default as string) ?? '')}
                        onChange={(e) => setRunInput(field.name, e.target.value)}
                        className="w-full bg-white border border-gray-200 px-3 py-2 text-sm text-gray-900 focus:border-black focus:outline-none"
                      />
                    )}
                  </label>
                ))}
              </div>
              {/* Fallback plain input if user still wants free text */}
              <div className="mt-4 pt-3 border-t border-gray-200">
                <div className="text-xs text-gray-400 mb-1">附加输入（可选）</div>
                <textarea
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  placeholder="额外补充文本..."
                  className="w-full bg-white border border-gray-200 p-2 text-sm text-gray-900 resize-none h-16 focus:border-black focus:outline-none"
                />
              </div>
            </>
          )}
          <button
            onClick={handleRun}
            disabled={!canRun}
            className="w-full mt-3 bg-red-600 text-white py-2 text-sm hover:bg-red-700 disabled:opacity-50"
          >
            {isRunning ? '运行中...' : '▶ 开始运行'}
          </button>
        </div>

        {/* Timeline (detailed mode only) */}
        {mode === 'detailed' && <ExecutionTimeline />}

        {/* Final Output */}
        <div className="w-[320px] p-4 border-l border-gray-200 overflow-y-auto">
          <div className="text-xs text-gray-500 mb-3">最终输出</div>

          {finalAnswer !== null && (
            <div className="bg-white border border-gray-200 p-3 mb-3">
              <div className="text-xs text-gray-400 mb-1">回答内容</div>
              <div className="text-sm text-gray-900 whitespace-pre-wrap">{finalAnswer}</div>
            </div>
          )}

          {finalOutputs !== null && (
            <details className="bg-white border border-gray-200 mb-3 group" open={Object.keys(finalOutputs).length > 0}>
              <summary className="px-3 py-2 text-xs text-gray-500 cursor-pointer select-none hover:text-gray-700">
                结构化输出 (JSON)
              </summary>
              <pre className="px-3 pb-3 text-xs text-gray-700 overflow-x-auto">
                {JSON.stringify(finalOutputs, null, 2)}
              </pre>
            </details>
          )}

          <AudioPlayer />

          {finalAnswer === null && finalOutputs === null && !isRunning && (
            <div className="text-sm text-gray-400 text-center mt-8">等待工作流执行完成...</div>
          )}
        </div>
      </div>
    </div>
  )
}
