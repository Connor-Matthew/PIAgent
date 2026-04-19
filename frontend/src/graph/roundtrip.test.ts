/**
 * Round-trip tests — guarantee that graph semantics are not lost when
 * a WorkflowGraphV2 is loaded into React Flow and then saved back.
 */

import { describe, it, expect } from 'vitest'
import { loadGraph } from './contract'
import { graphToReactFlow, reactFlowToGraph } from './adapters'

describe('WorkflowGraphV2 round-trip', () => {
  it('preserves linear DAG nodes and edges', () => {
    const original = loadGraph({
      nodes: [
        { id: 'start_1', type: 'start', position: { x: 0, y: 0 }, config: {} },
        { id: 'llm_1', type: 'llm', position: { x: 200, y: 0 }, config: { provider_id: 1 } },
        { id: 'end_1', type: 'end', position: { x: 400, y: 0 }, config: {} },
      ],
      edges: [
        { source: 'start_1', target: 'llm_1' },
        { source: 'llm_1', target: 'end_1' },
      ],
    })

    const { nodes, edges } = graphToReactFlow(original)
    const restored = reactFlowToGraph(nodes, edges)

    expect(restored.version).toBe(2)
    expect(restored.nodes).toHaveLength(3)
    expect(restored.edges).toHaveLength(2)
    expect(restored.nodes[1].config).toEqual({ provider_id: 1 })
  })

  it('preserves if-else parentId and branchId', () => {
    const original = loadGraph({
      nodes: [
        { id: 'start_1', type: 'start', position: { x: 0, y: 0 }, config: {} },
        {
          id: 'if_1',
          type: 'if_else',
          position: { x: 200, y: 0 },
          config: { branches: [{ id: 'true' }, { id: 'false' }] },
        },
        {
          id: 'llm_true',
          type: 'llm',
          position: { x: 200, y: 100 },
          parentId: 'if_1',
          branchId: 'true',
          config: { provider_id: 1 },
        },
        {
          id: 'llm_false',
          type: 'llm',
          position: { x: 200, y: 200 },
          parentId: 'if_1',
          branchId: 'false',
          config: { provider_id: 2 },
        },
        { id: 'end_1', type: 'end', position: { x: 400, y: 0 }, config: {} },
      ],
      edges: [
        { source: 'start_1', target: 'if_1' },
        { source: 'if_1', target: 'end_1' },
      ],
    })

    const { nodes, edges } = graphToReactFlow(original)
    const restored = reactFlowToGraph(nodes, edges)

    const trueNode = restored.nodes.find((n) => n.id === 'llm_true')
    const falseNode = restored.nodes.find((n) => n.id === 'llm_false')

    expect(trueNode?.parentId).toBe('if_1')
    expect(trueNode?.branchId).toBe('true')
    expect(falseNode?.parentId).toBe('if_1')
    expect(falseNode?.branchId).toBe('false')
  })

  it('preserves iteration parentId', () => {
    const original = loadGraph({
      nodes: [
        { id: 'start_1', type: 'start', position: { x: 0, y: 0 }, config: {} },
        {
          id: 'iter_1',
          type: 'iteration',
          position: { x: 200, y: 0 },
          config: { inputRef: '{{start_1.output}}' },
        },
        {
          id: 'llm_body',
          type: 'llm',
          position: { x: 200, y: 100 },
          parentId: 'iter_1',
          config: { provider_id: 1 },
        },
        { id: 'end_1', type: 'end', position: { x: 400, y: 0 }, config: {} },
      ],
      edges: [
        { source: 'start_1', target: 'iter_1' },
        { source: 'iter_1', target: 'end_1' },
      ],
    })

    const { nodes, edges } = graphToReactFlow(original)
    const restored = reactFlowToGraph(nodes, edges)

    const bodyNode = restored.nodes.find((n) => n.id === 'llm_body')
    expect(bodyNode?.parentId).toBe('iter_1')
  })

  it('preserves edge sourceHandle', () => {
    const original = loadGraph({
      nodes: [{ id: 'a', type: 'start', position: { x: 0, y: 0 }, config: {} }],
      edges: [{ source: 'a', target: 'b', sourceHandle: 'true' }],
    })

    const { nodes, edges } = graphToReactFlow(original)
    const restored = reactFlowToGraph(nodes, edges)

    expect(restored.edges[0].sourceHandle).toBe('true')
  })

  it('upgrades v1 graph with data.parentId to v2', () => {
    const v1 = {
      nodes: [
        {
          id: 'child_1',
          type: 'llm',
          position: { x: 0, y: 0 },
          data: { parentId: 'parent_1', provider_id: 1 },
        },
      ],
      edges: [],
    }

    const upgraded = loadGraph(v1)
    expect(upgraded.version).toBe(2)
    expect(upgraded.nodes[0].parentId).toBe('parent_1')
    expect(upgraded.nodes[0].config.provider_id).toBe(1)
  })

  it('does not silently drop if_else or iteration node types', () => {
    const v1 = {
      nodes: [
        { id: 'if_1', type: 'if_else', position: { x: 0, y: 0 }, data: {} },
        { id: 'iter_1', type: 'iteration', position: { x: 0, y: 0 }, data: {} },
      ],
      edges: [],
    }

    const upgraded = loadGraph(v1)
    expect(upgraded.nodes[0].type).toBe('if_else')
    expect(upgraded.nodes[1].type).toBe('iteration')
  })
})
