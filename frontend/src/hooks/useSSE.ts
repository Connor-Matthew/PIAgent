import { useCallback, useRef } from 'react'
import { useDebugStore } from '../stores/debugStore'
import type { SSEEvent } from '../types/workflow'

export function useSSE() {
  const eventSourceRef = useRef<EventSource | null>(null)
  const handleEvent = useDebugStore((s) => s.handleSSEEvent)

  const connect = useCallback(
    (workflowId: string, runId: string) => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
      }

      const url = `/api/workflows/${workflowId}/runs/${runId}/events`
      const es = new EventSource(url)
      eventSourceRef.current = es

      const handleMessage = () => (event: MessageEvent) => {
        const data: SSEEvent = JSON.parse(event.data)
        handleEvent(data)
      }

      es.addEventListener('node_start', handleMessage())
      es.addEventListener('node_stream', handleMessage())
      es.addEventListener('node_heartbeat', handleMessage())
      es.addEventListener('node_end', handleMessage())
      es.addEventListener('workflow_end', (event) => {
        const data: SSEEvent = JSON.parse(event.data)
        handleEvent(data)
        es.close()
      })

      es.onerror = () => {
        es.close()
      }
    },
    [handleEvent]
  )

  const disconnect = useCallback(() => {
    eventSourceRef.current?.close()
    eventSourceRef.current = null
  }, [])

  return { connect, disconnect }
}
