import type { WorkflowGraph } from './workflow'

export type HarnessStatus = 'idle' | 'running' | 'awaiting_user' | 'ready' | 'failed' | 'applied'

export interface HarnessOpenQuestion {
  question_id: string
  prompt: string
  options?: string[] | null
}

export interface HarnessSession {
  session_id: string
  status: HarnessStatus
  goal: string
  workflow_id?: string | null
  graph?: WorkflowGraph | null
}

export type HarnessEventType =
  | 'session_start'
  | 'decision'
  | 'tool_call'
  | 'tool_result'
  | 'skill_loaded'
  | 'graph_update'
  | 'builder_error'
  | 'validator_report'
  | 'awaiting_user_input'
  | 'user_resumed'
  | 'harness_ready'
  | 'harness_stuck'
  | 'llm_error'
  | 'session_end'

export const HARNESS_EVENT_TYPES: HarnessEventType[] = [
  'session_start',
  'decision',
  'tool_call',
  'tool_result',
  'skill_loaded',
  'graph_update',
  'builder_error',
  'validator_report',
  'awaiting_user_input',
  'user_resumed',
  'harness_ready',
  'harness_stuck',
  'llm_error',
  'session_end',
]

export interface HarnessDecisionDetail {
  tool?: string
  args?: Record<string, unknown>
  skill?: string
  action_kind?: string
  action?: Record<string, unknown>
  summary?: string
  question?: string
  options?: string[] | null
  reason?: string
}

export interface HarnessEvent {
  type: HarnessEventType
  session_id?: string
  goal?: string
  kind?: string
  tool?: string
  args?: Record<string, unknown>
  call_id?: string
  ok?: boolean
  summary?: string
  error?: string
  latency_ms?: number
  skill?: string
  snippet?: string
  snapshot?: WorkflowGraph
  message?: string
  findings?: Array<{
    severity: 'error' | 'warning'
    code: string
    message: string
    node_id?: string | null
  }>
  question_id?: string
  prompt?: string
  options?: string[] | null
  answer?: string
  workflow_id?: string
  reason?: string
  status?: string
  detail?: HarnessDecisionDetail
  action?: Record<string, unknown>
  node_count?: number
  edge_count?: number
  phase?: string
  recoverable?: boolean
}
