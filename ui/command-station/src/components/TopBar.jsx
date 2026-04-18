import React, { useState, useEffect } from 'react'

export default function TopBar({ connections, spawnerOpen, onToggleSpawner, onStop, activeAgents = 0, agentDone = false }) {
  const connected = connections.jarvis
  const [showDone, setShowDone] = useState(false)
  const [timeLeft, setTimeLeft] = useState(0)

  // Show "Agent done" for 3 seconds after completion
  useEffect(() => {
    if (agentDone) {
      setShowDone(true)
      const t = setTimeout(() => setShowDone(false), 3000)
      return () => clearTimeout(t)
    }
  }, [agentDone])

  // Estimated completion timer
  useEffect(() => {
    if (activeAgents > 0 && timeLeft === 0) {
      // Default to 15 mins for "build/V3" tasks, 5 mins for others
      setTimeLeft(900)
    } else if (activeAgents === 0) {
      setTimeLeft(0)
    }

    if (timeLeft > 0) {
      const t = setInterval(() => setTimeLeft(prev => Math.max(0, prev - 1)), 1000)
      return () => clearInterval(t)
    }
  }, [activeAgents, timeLeft])

  const formatTime = (s) => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`
  const hasRunning = activeAgents > 0

  return (
    <header
      className="drag-region flex items-center flex-shrink-0 border-b border-[#EAE6DF] bg-[#FBF8F4]"
      style={{ height: 44 }}
    >
      {/* macOS traffic lights space */}
      <div className="w-20 flex-shrink-0" />

      <div className="flex-1" />

      {/* Agent status indicator */}
      {(hasRunning || showDone) && (
        <div
          className="no-drag flex items-center gap-1.5 mr-3 px-2.5 py-1 cursor-pointer"
          style={{
            border: `1px solid ${showDone ? '#BBF7D0' : '#DDD6FE'}`,
            background: showDone ? '#F0FDF4' : '#F5F3FF',
          }}
          onClick={onToggleSpawner}
          title="Click to view agent progress"
        >
          {hasRunning && (
            <span
              style={{
                display: 'inline-block',
                width: 6,
                height: 6,
                borderRadius: '50%',
                background: '#7C3AED',
                animation: 'pulse 1.4s ease-in-out infinite',
                flexShrink: 0,
              }}
            />
          )}
          {showDone && !hasRunning && (
            <span style={{ color: '#22C55E', fontSize: 11, lineHeight: 1 }}>✅</span>
          )}
          <span
            className="text-[10px] font-medium"
            style={{ color: showDone && !hasRunning ? '#15803D' : '#7C3AED' }}
          >
            {hasRunning
              ? `Agent running${activeAgents > 1 ? ` (${activeAgents})` : ''}`
              : 'Agent done 🎉'}
          </span>
          {hasRunning && timeLeft > 0 && (
            <span className="text-[9px] font-bold ml-1 px-1.5 py-0.5 rounded bg-[#EDE9FE] text-[#7C3AED]">
              Est: {formatTime(timeLeft)}
            </span>
          )}
        </div>
      )}

      {/* Connection status */}
      <div className="no-drag flex items-center gap-1.5 mr-4 text-[11px]">
        <span
          className="w-1.5 h-1.5 rounded-full flex-shrink-0"
          style={{ backgroundColor: connected ? '#22C55E' : '#D1D5DB' }}
        />
        <span style={{ color: connected ? '#9CA3AF' : '#EF4444' }}>
          {connected ? 'Connected 🔗' : 'Offline ❌'}
        </span>
      </div>

      <div className="flex-1" />

      {/* Agent status indicator */}
      <button
        onClick={onToggleSpawner}
        className="no-drag mr-3 px-3 py-1 text-[11px] font-medium transition-all"
        style={{
          border: '1px solid',
          borderColor: spawnerOpen ? '#7C3AED' : '#DDD6FE',
          background: spawnerOpen ? '#7C3AED' : 'transparent',
          color: spawnerOpen ? '#ffffff' : '#7C3AED',
        }}
        onMouseEnter={e => {
          if (!spawnerOpen) e.currentTarget.style.background = '#EDE9FE'
        }}
        onMouseLeave={e => {
          if (!spawnerOpen) e.currentTarget.style.background = 'transparent'
        }}
      >
        Agents
      </button>
    </header>
  )
}
