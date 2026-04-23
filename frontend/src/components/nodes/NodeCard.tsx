import { useEffect, useState } from 'react'
import { Handle, Position } from 'reactflow'

import type { WorkflowNodeData } from '../../types/workflow'


interface NodeCardProps {
  data: WorkflowNodeData
  selected: boolean
  accent: 'blue' | 'purple' | 'green' | 'pink' | 'yellow' | 'slate'
  icon: string
  title: string
  subtitle?: string
  targetHandle?: boolean
  sourceHandle?: boolean
}


const ACCENT_STYLES = {
  blue: {
    border: 'border-gray-800',
    selectedBorder: 'border-black',
    iconBg: 'bg-gray-800',
    handle: '!bg-gray-800',
  },
  purple: {
    border: 'border-gray-800',
    selectedBorder: 'border-black',
    iconBg: 'bg-gray-900',
    handle: '!bg-gray-900',
  },
  green: {
    border: 'border-gray-600',
    selectedBorder: 'border-black',
    iconBg: 'bg-gray-600',
    handle: '!bg-gray-600',
  },
  pink: {
    border: 'border-gray-700',
    selectedBorder: 'border-black',
    iconBg: 'bg-gray-700',
    handle: '!bg-gray-700',
  },
  yellow: {
    border: 'border-gray-500',
    selectedBorder: 'border-black',
    iconBg: 'bg-gray-500',
    handle: '!bg-gray-500',
  },
  slate: {
    border: 'border-gray-400',
    selectedBorder: 'border-black',
    iconBg: 'bg-gray-400',
    handle: '!bg-gray-400',
  },
} as const


function getStateClasses(data: WorkflowNodeData) {
  switch (data.visualState) {
    case 'building':
      return {
        frame: 'ring-2 ring-cyan-400/40 shadow-[0_0_40px_rgba(34,211,238,0.14)]',
        badge: 'border border-cyan-400/30 bg-cyan-400/10 text-cyan-700',
      }
    case 'running':
      return {
        frame: 'ring-2 ring-sky-400/40 shadow-[0_0_36px_rgba(56,189,248,0.18)]',
        badge: 'border border-sky-400/30 bg-sky-400/10 text-sky-700',
      }
    case 'completed':
      return {
        frame: 'ring-2 ring-emerald-400/35 shadow-[0_0_32px_rgba(52,211,153,0.14)]',
        badge: 'border border-emerald-400/30 bg-emerald-400/10 text-emerald-700',
      }
    case 'failed':
      return {
        frame: 'ring-2 ring-rose-400/35 shadow-[0_0_32px_rgba(251,113,133,0.14)]',
        badge: 'border border-rose-400/30 bg-rose-400/10 text-rose-700',
      }
    default:
      return {
        frame: '',
        badge: 'border border-gray-200 bg-white text-gray-600',
      }
  }
}


export function NodeCard({
  data,
  selected,
  accent,
  icon,
  title,
  subtitle,
  targetHandle = true,
  sourceHandle = true,
}: NodeCardProps) {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => setVisible(true))
    return () => window.cancelAnimationFrame(frame)
  }, [])

  const accentStyle = ACCENT_STYLES[accent]
  const stateStyle = getStateClasses(data)
  const effectiveSubtitle = data.statusNote || subtitle

  return (
    <div
      className={[
        'min-w-[170px] border-2 bg-white px-4 py-3 backdrop-blur transition-all duration-300',
        visible ? 'scale-100 opacity-100' : 'scale-95 opacity-0',
        selected ? accentStyle.selectedBorder : accentStyle.border,
        stateStyle.frame,
      ].join(' ')}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className={`${accentStyle.iconBg} flex h-6 w-6 items-center justify-center text-xs text-white`}>
            {icon}
          </span>
          <div>
            <div className="text-sm font-semibold text-gray-900">{title}</div>
            {effectiveSubtitle && (
              <div className="mt-1 max-w-[160px] text-[11px] text-gray-500">
                {effectiveSubtitle}
              </div>
            )}
          </div>
        </div>
        {data.visualLabel && data.visualLabel.trim() && (
          <div className={`px-2 py-1 text-[10px] uppercase tracking-[0.14em] ${stateStyle.badge}`}>
            {data.visualLabel}
          </div>
        )}
      </div>

      {targetHandle && (
        <Handle type="target" position={Position.Left} className={`${accentStyle.handle} !h-3 !w-3`} />
      )}
      {sourceHandle && (
        <Handle type="source" position={Position.Right} className={`${accentStyle.handle} !h-3 !w-3`} />
      )}
    </div>
  )
}
