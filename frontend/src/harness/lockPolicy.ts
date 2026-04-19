import type { HarnessStatus } from '../types/harness'

export function shouldLockCanvasForHarnessStatus(status: HarnessStatus) {
  return status === 'running' || status === 'awaiting_user'
}
