import { useCallback, useRef } from 'react'
import { useDebugStore } from '../stores/debugStore'
import type { SSEEvent } from '../types/workflow'

let activeEventSource: EventSource | null = null

export function useSSE() {
  const eventSourceRef = useRef<EventSource | null>(activeEventSource)
  const handleEvent = useDebugStore((s) => s.handleSSEEvent)

  const connect = useCallback(
    (workflowId: string, runId: string) => {
      if (activeEventSource) {
        activeEventSource.close()
      }

      const url = `/api/workflows/${workflowId}/runs/${runId}/events`
      const es = new EventSource(url)
      activeEventSource = es
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
        if (activeEventSource === es) {
          activeEventSource = null
        }
        if (eventSourceRef.current === es) {
          eventSourceRef.current = null
        }
      })

      es.onerror = () => {
        es.close()
        if (activeEventSource === es) {
          activeEventSource = null
        }
        if (eventSourceRef.current === es) {
          eventSourceRef.current = null
        }
      }
    },
    [handleEvent]
  )

  const disconnect = useCallback(() => {
    activeEventSource?.close()
    activeEventSource = null
    eventSourceRef.current = null
  }, [])

  return { connect, disconnect }
}
