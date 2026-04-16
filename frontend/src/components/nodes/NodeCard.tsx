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
    border: 'border-blue-500',
    selectedBorder: 'border-blue-300',
    iconBg: 'bg-blue-500',
    handle: '!bg-blue-500',
  },
  purple: {
    border: 'border-purple-500',
    selectedBorder: 'border-purple-300',
    iconBg: 'bg-purple-500',
    handle: '!bg-purple-500',
  },
  green: {
    border: 'border-green-500',
    selectedBorder: 'border-green-300',
    iconBg: 'bg-green-500',
    handle: '!bg-green-500',
  },
  pink: {
    border: 'border-pink-500',
    selectedBorder: 'border-pink-300',
    iconBg: 'bg-pink-500',
    handle: '!bg-pink-500',
  },
  yellow: {
    border: 'border-yellow-500',
    selectedBorder: 'border-yellow-300',
    iconBg: 'bg-yellow-500',
    handle: '!bg-yellow-500',
  },
  slate: {
    border: 'border-slate-500',
    selectedBorder: 'border-slate-300',
    iconBg: 'bg-slate-500',
    handle: '!bg-slate-500',
  },
} as const


function getStateClasses(data: WorkflowNodeData) {
  switch (data.visualState) {
    case 'building':
      return {
        frame: 'ring-2 ring-cyan-400/40 shadow-[0_0_40px_rgba(34,211,238,0.14)]',
        badge: 'border border-cyan-400/30 bg-cyan-400/10 text-cyan-100',
      }
    case 'running':
      return {
        frame: 'ring-2 ring-sky-400/40 shadow-[0_0_36px_rgba(56,189,248,0.18)]',
        badge: 'border border-sky-400/30 bg-sky-400/10 text-sky-100',
      }
    case 'completed':
      return {
        frame: 'ring-2 ring-emerald-400/35 shadow-[0_0_32px_rgba(52,211,153,0.14)]',
        badge: 'border border-emerald-400/30 bg-emerald-400/10 text-emerald-100',
      }
    case 'failed':
      return {
        frame: 'ring-2 ring-rose-400/35 shadow-[0_0_32px_rgba(251,113,133,0.14)]',
        badge: 'border border-rose-400/30 bg-rose-400/10 text-rose-100',
      }
    default:
      return {
        frame: '',
        badge: 'border border-slate-700 bg-slate-900/90 text-slate-300',
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
        'min-w-[170px] rounded-xl border-2 bg-slate-800/95 px-4 py-3 backdrop-blur transition-all duration-300',
        visible ? 'scale-100 opacity-100' : 'scale-95 opacity-0',
        selected ? accentStyle.selectedBorder : accentStyle.border,
        stateStyle.frame,
      ].join(' ')}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className={`${accentStyle.iconBg} flex h-6 w-6 items-center justify-center rounded text-xs text-white`}>
            {icon}
          </span>
          <div>
            <div className="text-sm font-semibold text-slate-100">{title}</div>
            {effectiveSubtitle && (
              <div className="mt-1 max-w-[160px] text-[11px] text-slate-400">
                {effectiveSubtitle}
              </div>
            )}
          </div>
        </div>
        {data.visualLabel && data.visualLabel.trim() && (
          <div className={`rounded-full px-2 py-1 text-[10px] uppercase tracking-[0.14em] ${stateStyle.badge}`}>
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
