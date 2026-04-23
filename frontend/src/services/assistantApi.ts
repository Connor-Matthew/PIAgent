import type { AssistantSSEEvent, AssistantSSEEventName } from '../types/workflow'

interface StreamHandlers {
  onEvent: (event: AssistantSSEEvent) => void
  onError?: (error: Error) => void
}

function parseSSEBlock(block: string): AssistantSSEEvent | null {
  let event: AssistantSSEEventName | null = null
  const dataLines: string[] = []

  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) {
      event = line.slice('event:'.length).trim() as AssistantSSEEventName
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).trim())
    }
  }

  if (!event) return null

  const rawData = dataLines.join('\n')
  const data = rawData ? JSON.parse(rawData) : {}
  return { event, data }
}

export const assistantApi = {
  async streamMessage(
    workflowId: string,
    message: string,
    handlers: StreamHandlers
  ) {
    const response = await fetch(`/api/assistant/sessions/${workflowId}/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    })

    if (!response.ok || !response.body) {
      throw new Error(`Assistant request failed: ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const blocks = buffer.split('\n\n')
        buffer = blocks.pop() ?? ''

        for (const block of blocks) {
          const parsed = parseSSEBlock(block)
          if (parsed) handlers.onEvent(parsed)
        }
      }

      if (buffer.trim()) {
        const parsed = parseSSEBlock(buffer)
        if (parsed) handlers.onEvent(parsed)
      }
    } catch (error) {
      handlers.onError?.(error instanceof Error ? error : new Error(String(error)))
      throw error
    }
  },
}
