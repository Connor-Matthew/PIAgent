import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, test } from 'bun:test'

function source(path: string) {
  return readFileSync(join(import.meta.dir, path), 'utf8')
}

describe('NodeLibrary delete workflow UX', () => {
  test('uses in-app dialogs instead of browser confirm or alert APIs', () => {
    const nodeLibrary = source('NodeLibrary.tsx')

    expect(nodeLibrary).not.toContain('window.confirm')
    expect(nodeLibrary).not.toContain('window.alert')
    expect(nodeLibrary).toContain('WorkflowDeleteDialog')
  })
})
