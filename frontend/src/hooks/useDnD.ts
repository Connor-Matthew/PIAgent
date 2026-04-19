import { useCallback, useRef } from 'react'
import type { ReactFlowInstance } from 'reactflow'
import type { NodeType, WorkflowNodeData } from '../types/workflow'
import { useWorkflowStore } from '../stores/workflowStore'

let nodeId = 0
const getId = () => `node_${++nodeId}`

export function useDnD() {
  const reactFlowInstance = useRef<ReactFlowInstance | null>(null)
  const addNode = useWorkflowStore((s) => s.addNode)

  const onInit = useCallback((instance: ReactFlowInstance) => {
    reactFlowInstance.current = instance
  }, [])

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault()
      const nodeType = event.dataTransfer.getData('application/piagent-node') as NodeType
      if (!nodeType || !reactFlowInstance.current) return

      const position = reactFlowInstance.current.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      })

      const labels: Record<NodeType, string> = {
        start: '用户输入',
        llm: 'LLM 对话',
        rag: 'RAG 知识检索',
        agent: 'ReAct Agent',
        tts: 'TTS 音频合成',
        end: '结束',
        if_else: 'If-Else 分支',
        iteration: 'Iteration 循环',
      }

      addNode({
        id: getId(),
        type: nodeType,
        position,
        data: {
          label: labels[nodeType],
          nodeType,
          config: {},
        } satisfies WorkflowNodeData,
      })
    },
    [addNode]
  )

  return { onInit, onDragOver, onDrop }
}
