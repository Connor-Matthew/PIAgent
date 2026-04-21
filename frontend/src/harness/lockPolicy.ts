import type { HarnessStatus } from '../types/harness'

export function shouldLockCanvasForHarnessStatus(status: HarnessStatus, hasOpenQuestion = false) {
  return status === 'running' || (status === 'awaiting_user' && hasOpenQuestion)
}
