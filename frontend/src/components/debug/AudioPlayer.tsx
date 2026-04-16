import { useRef, useState, useEffect } from 'react'
import { useDebugStore } from '../../stores/debugStore'

export function AudioPlayer() {
  const audioUrl = useDebugStore((s) => s.audioUrl)
  const audioRef = useRef<HTMLAudioElement>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)

  useEffect(() => {
    if (audioUrl && audioRef.current) {
      audioRef.current.pause()
      audioRef.current.load()
    }
  }, [audioUrl])

  const togglePlay = () => {
    if (!audioRef.current) return
    if (isPlaying) {
      audioRef.current.pause()
    } else {
      void audioRef.current.play().catch(() => undefined)
    }
  }

  const formatTime = (t: number) => {
    const m = Math.floor(t / 60)
    const s = Math.floor(t % 60)
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  if (!audioUrl) return null

  return (
    <div className={`bg-slate-950 border border-slate-700 rounded-xl p-4 ${!audioUrl ? 'opacity-40' : ''}`}>
      <div className="text-sm text-slate-400 mb-3">🎧 AI 播客播放器</div>
      <audio
        ref={audioRef}
        src={audioUrl}
        onLoadStart={() => {
          setIsPlaying(false)
          setCurrentTime(0)
          setDuration(0)
        }}
        onPause={() => setIsPlaying(false)}
        onPlay={() => setIsPlaying(true)}
        onTimeUpdate={() => setCurrentTime(audioRef.current?.currentTime ?? 0)}
        onLoadedMetadata={() => setDuration(audioRef.current?.duration ?? 0)}
        onEnded={() => setIsPlaying(false)}
      />
      <div className="bg-slate-800 rounded-full h-1 mb-3 cursor-pointer"
        onClick={(e) => {
          if (!audioRef.current || !duration) return
          const rect = e.currentTarget.getBoundingClientRect()
          const ratio = (e.clientX - rect.left) / rect.width
          audioRef.current.currentTime = ratio * duration
        }}
      >
        <div
          className="bg-blue-500 rounded-full h-full"
          style={{ width: duration ? `${(currentTime / duration) * 100}%` : '0%' }}
        />
      </div>
      <div className="flex justify-between items-center">
        <span className="text-slate-600 text-xs">{formatTime(currentTime)}</span>
        <button
          onClick={togglePlay}
          disabled={!audioUrl}
          className="bg-blue-500 text-white w-8 h-8 rounded-full flex items-center justify-center disabled:opacity-50"
        >
          {isPlaying ? '⏸' : '▶'}
        </button>
        <span className="text-slate-600 text-xs">{duration ? formatTime(duration) : '--:--'}</span>
      </div>
    </div>
  )
}
