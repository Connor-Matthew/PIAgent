import { describe, expect, test } from 'bun:test'

import { getAdditionalConfigEntries } from './nodeConfigUtils'

describe('getAdditionalConfigEntries', () => {
  test('returns saved config fields that are not rendered by the node-specific form', () => {
    const entries = getAdditionalConfigEntries(
      {
        provider_id: 1,
        model: 'gpt-4o',
        prompt_template: 'Question: {{start_1.question}}',
        customDebug: { enabled: true },
      },
      ['provider_id', 'model'],
    )

    expect(entries).toEqual([
      ['prompt_template', 'Question: {{start_1.question}}'],
      ['customDebug', { enabled: true }],
    ])
  })
})
