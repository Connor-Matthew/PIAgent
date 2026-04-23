import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, test } from 'bun:test'

function source(path: string) {
  return readFileSync(join(import.meta.dir, path), 'utf8')
}

describe('ProvidersPage notifications UX', () => {
  test('uses in-app dialogs instead of browser alert APIs', () => {
    const providersPage = source('Providers.tsx')

    expect(providersPage).not.toContain('alert(')
    expect(providersPage).toContain('AppNoticeDialog')
  })
})
