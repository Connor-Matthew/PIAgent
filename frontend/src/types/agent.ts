import type { SSEEvent, WorkflowGraph } from './workflow'

export interface ClarificationTurn {
  turn_index: number
  dim: string
  question: string
  user_answer?: string | null
}

export interface RecipeIR {
  recipe: string
  goal_summary: string
  audience_level: string
  tone: string
  duration_minutes: number
  script_format: string
  include_code_snippets: boolean
  use_knowledge_base: boolean
  need_audio_output: boolean
  knowledge_base_id?: string | null
  llm_provider_id?: number | null
  tts_provider_id?: number | null
  tts_voice_id?: string | null
}

export interface AgentSession {
  session_id: string
  user_goal: string
  status: 'clarifying' | 'ready' | 'applied' | 'failed' | 'generating'
  clarification_turns: ClarificationTurn[]
  answered_dims: Record<string, unknown>
  recipe_ir?: RecipeIR | null
  generated_graph?: WorkflowGraph | null
  rationale_text?: string | null
  workflow_id?: string | null
}

export type AgentEventType =
  | 'agent_session_started'
  | 'clarify_question'
  | 'clarify_completed'
  | 'recipe_generating'
  | 'recipe_repairing'
  | 'recipe_fallback'
  | 'plan_ready'
  | 'agent_error'

export interface AgentSessionEvent {
  type: AgentEventType
  session_id?: string
  turn_index?: number
  next_dim?: string | null
  question?: string | null
  total_turns?: number
  answered_dims?: Record<string, unknown>
  attempt?: number
  errors?: string[]
  failure_type?: string
  recipe?: RecipeIR
  graph?: WorkflowGraph
  defaults_applied?: boolean
  rationale?: string
  stage?: string
  message?: string
  recoverable?: boolean
}

export type AgentAutoRunEventType =
  | 'planning_start'
  | 'planning_update'
  | 'planner_action'
  | 'planner_observe'
  | 'node_added'
  | 'edge_added'
  | 'node_config_updated'
  | 'workflow_built'
  | 'planning_error'
  | 'plan_ready'

export interface AgentAutoRunEvent {
  type: AgentAutoRunEventType
  goal?: string
  text?: string
  name?: string
  summary?: string
  counts?: Record<string, number>
  node?: WorkflowGraph['nodes'][number]
  edge?: WorkflowGraph['edges'][number]
  node_id?: string
  patch?: Record<string, unknown>
  graph?: WorkflowGraph
  recipe?: RecipeIR
  defaults_applied?: boolean
  rationale?: string
  node_count?: number
  edge_count?: number
  stage?: string
  message?: string
  recoverable?: boolean
}

export type AgentAutoRunStreamEvent = AgentAutoRunEvent | SSEEvent
