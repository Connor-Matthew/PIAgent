import { useEffect, useRef } from 'react'
import { useWorkflowStore } from '../stores/workflowStore'
import { workflowApi } from '../services/api'

const DEBOUNCE_MS = 800

export function useAutoSave() {
  const workflowId = useWorkflowStore((s) => s.workflowId)
  const workflowName = useWorkflowStore((s) => s.workflowName)
  const nodes = useWorkflowStore((s) => s.nodes)
  const edges = useWorkflowStore((s) => s.edges)
  const setSaveStatus = useWorkflowStore((s) => s.setSaveStatus)
  const upsertWorkflowMeta = useWorkflowStore((s) => s.upsertWorkflowMeta)

  const lastSnapshotRef = useRef<string | null>(null)
  const lastSavedIdRef = useRef<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!workflowId) return

    if (lastSavedIdRef.current !== workflowId) {
      lastSavedIdRef.current = workflowId
      lastSnapshotRef.current = null
    }

    const graph = useWorkflowStore.getState().toGraphJSON()
    const snapshot = JSON.stringify({ name: workflowName, graph })

    if (lastSnapshotRef.current === null) {
      lastSnapshotRef.current = snapshot
      return
    }
    if (lastSnapshotRef.current === snapshot) return

    setSaveStatus('dirty')

    if (timerRef.current) clearTimeout(timerRef.current)
    const currentId = workflowId
    timerRef.current = setTimeout(async () => {
      setSaveStatus('saving')
      try {
        await workflowApi.update(currentId, { name: workflowName, graph })
        lastSnapshotRef.current = snapshot
        upsertWorkflowMeta({ id: currentId, name: workflowName })
        if (useWorkflowStore.getState().workflowId === currentId) {
          setSaveStatus('saved')
        }
      } catch {
        setSaveStatus('error')
      }
    }, DEBOUNCE_MS)

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [workflowId, workflowName, nodes, edges, setSaveStatus, upsertWorkflowMeta])
}
