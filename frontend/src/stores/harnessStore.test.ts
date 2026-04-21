import { beforeEach, describe, expect, test } from 'bun:test'

import { useHarnessStore } from './harnessStore'

describe('harnessStore agent messages', () => {
  beforeEach(() => {
    useHarnessStore.getState().reset()
  })

  test('finalizes a streamed agent reply without duplicating it', () => {
    const store = useHarnessStore.getState()

    store.updateLastAgentMessage('Hel')
    store.updateLastAgentMessage('lo')
    useHarnessStore.getState().finalizeAgentMessage('Hello')

    const messages = useHarnessStore.getState().messages
    expect(messages).toHaveLength(1)
    expect(messages[0]).toMatchObject({ role: 'agent', content: 'Hello' })
  })

  test('adds a final agent reply when there was no streamed placeholder', () => {
    useHarnessStore.getState().finalizeAgentMessage('Done')

    const messages = useHarnessStore.getState().messages
    expect(messages).toHaveLength(1)
    expect(messages[0]).toMatchObject({ role: 'agent', content: 'Done' })
  })
})
