import { useEffect, useState } from 'react'
import { useWorkflowStore } from '../../stores/workflowStore'
import { useDebugStore } from '../../stores/debugStore'
import { NodeConfig } from './NodeConfig'
import { DebugRunPanel } from '../debug/DebugRunPanel'

type TabKey = 'config' | 'run'

export function RightPanel() {
  const [manualTab, setManualTab] = useState<TabKey>('config')
  const selectedNodeId = useWorkflowStore((s) => s.selectedNodeId)
  const debugIsRunning = useDebugStore((s) => s.isRunning)
  const debugIsOpen = useDebugStore((s) => s.isOpen)

  useEffect(() => {
    let hadRunActivity = useDebugStore.getState().isRunning
    const switchToRunOnFirstActivity = () => {
      const nextRunActivity = useDebugStore.getState().isRunning
      if (nextRunActivity && !hadRunActivity) {
        setManualTab('run')
      }
      hadRunActivity = nextRunActivity
    }

    const unsubscribeDebug = useDebugStore.subscribe(switchToRunOnFirstActivity)

    return () => {
      unsubscribeDebug()
    }
  }, [])

  const activeTab: TabKey = manualTab

  useEffect(() => {
    if (selectedNodeId) {
      setManualTab('config')
    }
  }, [selectedNodeId])

  const tabs: { key: TabKey; label: string; badge?: boolean }[] = [
    { key: 'config', label: '节点配置', badge: !!selectedNodeId },
    { key: 'run', label: '运行', badge: debugIsRunning || debugIsOpen },
  ]

  return (
    <div className="w-[380px] bg-white border-l border-gray-200 shrink-0 flex flex-col overflow-hidden">
      {/* Tabs */}
      <div className="flex border-b border-gray-200">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setManualTab(tab.key)}
            className={`flex-1 px-3 py-3 text-xs font-medium transition-colors relative ${
              activeTab === tab.key
                ? 'text-black bg-gray-50'
                : 'text-gray-400 hover:text-gray-700 hover:bg-gray-50/50'
            }`}
          >
            {tab.label}
            {tab.badge && (
              <span
                className={`ml-1.5 inline-block w-1.5 h-1.5 ${
                  activeTab === tab.key ? 'bg-red-600' : 'bg-gray-300'
                }`}
              />
            )}
            {activeTab === tab.key && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-red-600" />
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'config' && <NodeConfig />}
        {activeTab === 'run' && <DebugRunPanel />}
      </div>
    </div>
  )
}
