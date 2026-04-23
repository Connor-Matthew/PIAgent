import { beforeEach, describe, expect, test } from 'bun:test'

import { defaultEndNode, defaultStartNode, useWorkflowStore } from './workflowStore'

describe('workflowStore graph loading', () => {
  beforeEach(() => {
    useWorkflowStore.setState({
      nodes: [defaultStartNode, defaultEndNode],
      edges: [],
      selectedNodeId: null,
      workflowId: null,
      workflowName: 'Untitled Workflow',
    })
  })

  test('preserves control-flow node types when loading a workflow', () => {
    useWorkflowStore.getState().setWorkflow('wf_1', 'Control Flow', [
      {
        id: 'if_1',
        type: 'if_else',
        position: { x: 0, y: 0 },
        config: { branches: [{ id: 'true' }, { id: 'false' }] },
      },
      {
        id: 'iter_1',
        type: 'iteration',
        position: { x: 200, y: 0 },
        config: { inputRef: '{{start_1.items}}' },
      },
    ], [])

    const nodesById = new Map(useWorkflowStore.getState().nodes.map((node) => [node.id, node]))

    expect(nodesById.get('if_1')?.data.nodeType).toBe('if_else')
    expect(nodesById.get('if_1')?.data.config.branches).toEqual([{ id: 'true' }, { id: 'false' }])
    expect(nodesById.get('iter_1')?.data.nodeType).toBe('iteration')
    expect(nodesById.get('iter_1')?.data.config.inputRef).toBe('{{start_1.items}}')
  })
})
