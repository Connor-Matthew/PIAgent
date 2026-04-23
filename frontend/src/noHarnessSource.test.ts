import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, test } from 'bun:test'

const srcRoot = import.meta.dir

function source(path: string) {
  return readFileSync(join(srcRoot, path), 'utf8')
}

describe('harness removal source contract', () => {
  test('removes builder chat and harness frontend modules', () => {
    const removedPaths = [
      'components/agent/AgentPanel.tsx',
      'components/agent/ApplyDraftButton.tsx',
      'hooks/useHarnessSession.ts',
      'services/harnessApi.ts',
      'stores/harnessStore.ts',
      'types/harness.ts',
      'harness/lockPolicy.ts',
    ]

    for (const path of removedPaths) {
      expect(existsSync(join(srcRoot, path))).toBe(false)
    }
  })

  test('keeps right panel focused on manual config and run controls', () => {
    const rightPanel = source('components/panels/RightPanel.tsx')

    expect(rightPanel).not.toContain('AgentPanel')
    expect(rightPanel).not.toContain('useHarnessStore')
    expect(rightPanel).not.toContain("key: 'agent'")
  })
})
