import { useEffect, useState } from 'react'
import { useWorkflowStore } from '../../stores/workflowStore'
import { useHarnessStore } from '../../stores/harnessStore'
import { useDebugStore } from '../../stores/debugStore'
import { NodeConfig } from './NodeConfig'
import { AgentStatusPanel } from '../agent/AgentStatusPanel'
import { DebugRunPanel } from '../debug/DebugRunPanel'

type TabKey = 'config' | 'agent' | 'run'

function readAgentActivity() {
  const harness = useHarnessStore.getState()
  const debug = useDebugStore.getState()
  return Boolean(
    harness.sessionId ||
    harness.isRunning ||
    harness.events.length > 0 ||
    debug.isRunning
  )
}

export function RightPanel() {
  const [manualTab, setManualTab] = useState<TabKey>(() => (
    readAgentActivity() ? 'agent' : 'config'
  ))
  const selectedNodeId = useWorkflowStore((s) => s.selectedNodeId)
  const sessionId = useHarnessStore((s) => s.sessionId)
  const isHarnessRunning = useHarnessStore((s) => s.isRunning)
  const harnessEventCount = useHarnessStore((s) => s.events.length)
  const debugIsRunning = useDebugStore((s) => s.isRunning)
  const debugIsOpen = useDebugStore((s) => s.isOpen)
  const agentHasActivity = Boolean(sessionId || isHarnessRunning || harnessEventCount > 0 || debugIsRunning)

  useEffect(() => {
    let hadAgentActivity = readAgentActivity()
    const switchToAgentOnFirstActivity = () => {
      const nextAgentActivity = readAgentActivity()
      if (nextAgentActivity && !hadAgentActivity) {
        setManualTab('agent')
      }
      hadAgentActivity = nextAgentActivity
    }

    const unsubscribeHarness = useHarnessStore.subscribe(switchToAgentOnFirstActivity)
    const unsubscribeDebug = useDebugStore.subscribe(switchToAgentOnFirstActivity)

    return () => {
      unsubscribeHarness()
      unsubscribeDebug()
    }
  }, [])

  const activeTab: TabKey = manualTab

  const tabs: { key: TabKey; label: string; badge?: boolean }[] = [
    { key: 'config', label: '节点配置', badge: !!selectedNodeId },
    { key: 'agent', label: 'Agent', badge: agentHasActivity || debugIsOpen },
    { key: 'run', label: '运行', badge: debugIsRunning || debugIsOpen },
  ]

  return (
    <div className="w-[380px] bg-slate-900 border-l border-slate-800 shrink-0 flex flex-col overflow-hidden">
      {/* Tabs */}
      <div className="flex border-b border-slate-800">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setManualTab(tab.key)}
            className={`flex-1 px-3 py-3 text-xs font-medium transition-colors relative ${
              activeTab === tab.key
                ? 'text-slate-100 bg-slate-800/50'
                : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800/30'
            }`}
          >
            {tab.label}
            {tab.badge && (
              <span
                className={`ml-1.5 inline-block w-1.5 h-1.5 rounded-full ${
                  activeTab === tab.key ? 'bg-blue-400' : 'bg-slate-600'
                }`}
              />
            )}
            {activeTab === tab.key && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-500" />
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'config' && <NodeConfig />}
        {activeTab === 'agent' && <AgentStatusPanel />}
        {activeTab === 'run' && <DebugRunPanel />}
      </div>
    </div>
  )
}
