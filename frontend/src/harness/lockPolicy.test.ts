import { describe, expect, test } from 'bun:test'

import { shouldLockCanvasForHarnessStatus } from './lockPolicy'

describe('shouldLockCanvasForHarnessStatus', () => {
  test('does not lock while waiting for the next normal chat turn', () => {
    expect(shouldLockCanvasForHarnessStatus('waiting')).toBe(false)
  })

  test('locks only when an awaiting_user state has an open question', () => {
    expect(shouldLockCanvasForHarnessStatus('awaiting_user')).toBe(false)
    expect(shouldLockCanvasForHarnessStatus('awaiting_user', true)).toBe(true)
  })
})
