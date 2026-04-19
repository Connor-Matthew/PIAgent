import { StartNode } from './StartNode'
import { LLMNode } from './LLMNode'
import { RAGNode } from './RAGNode'
import { AgentNode } from './AgentNode'
import { TTSNode } from './TTSNode'
import { EndNode } from './EndNode'
import { IfElseNode } from './IfElseNode'
import { IterationNode } from './IterationNode'

export const nodeTypes = {
  start: StartNode,
  llm: LLMNode,
  rag: RAGNode,
  agent: AgentNode,
  tts: TTSNode,
  end: EndNode,
  if_else: IfElseNode,
  iteration: IterationNode,
}
