import React from 'react'

export default function TopBar({ connections, spawnerOpen, onToggleSpawner }) {
  const connected = connections.jarvis

  return (
    <header
      className="drag-region flex items-center flex-shrink-0 border-b border-[#EAE6DF] bg-[#FBF8F4]"
      style={{ height: 44 }}
    >
      {/* macOS traffic lights space */}
      <div className="w-20 flex-shrink-0" />

      <div className="flex-1" />

      {/* Connection status */}
      <div className="no-drag flex items-center gap-1.5 mr-4 text-[11px]">
        <span
          className="w-1.5 h-1.5 rounded-full flex-shrink-0"
          style={{ backgroundColor: connected ? '#22C55E' : '#D1D5DB' }}
        />
        <span style={{ color: connected ? '#9CA3AF' : '#EF4444' }}>
          {connected ? 'Connected' : 'Offline'}
        </span>
      </div>

      {/* Agents panel toggle */}
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
          if (!spawnerOpen) {
            e.currentTarget.style.background = '#EDE9FE'
          }
        }}
        onMouseLeave={e => {
          if (!spawnerOpen) {
            e.currentTarget.style.background = 'transparent'
          }
        }}
      >
        Agents
      </button>
    </header>
  )
}
