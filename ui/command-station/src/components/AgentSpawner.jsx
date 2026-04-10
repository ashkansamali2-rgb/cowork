import React, { useState, useRef, useEffect } from 'react'

// ── Helpers ────────────────────────────────────────────────────────────────────

function elapsed(startTime) {
  if (!startTime) return ''
  const secs = Math.floor((Date.now() - startTime) / 1000)
  if (secs < 60) return `${secs}s`
  return `${Math.floor(secs / 60)}m ${secs % 60}s`
}

function StatusIcon({ status }) {
  if (status === 'running') {
    return (
      <span
        style={{
          display: 'inline-block',
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: '#7C3AED',
          animation: 'pulse 1.4s ease-in-out infinite',
          flexShrink: 0,
        }}
      />
    )
  }
  if (status === 'done') {
    return <span style={{ color: '#22C55E', fontSize: 12, lineHeight: 1 }}>✓</span>
  }
  if (status === 'error') {
    return <span style={{ color: '#EF4444', fontSize: 12, lineHeight: 1 }}>✗</span>
  }
  return null
}

// ── AgentCard ──────────────────────────────────────────────────────────────────

function AgentCard({ agentId, info }) {
  const [expanded, setExpanded] = useState(true)
  const { task = '', status = 'running', steps = [], startTime } = info
  const [tick, setTick] = useState(0)

  // Keep elapsed timer ticking while running
  useEffect(() => {
    if (status !== 'running') return
    const t = setInterval(() => setTick(n => n + 1), 1000)
    return () => clearInterval(t)
  }, [status])

  return (
    <div
      style={{
        border: '1px solid #EAE6DF',
        borderLeft: `3px solid ${status === 'done' ? '#22C55E' : status === 'error' ? '#EF4444' : '#7C3AED'}`,
        background: '#FAFAF8',
        marginBottom: 8,
      }}
    >
      {/* Card header */}
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left"
        style={{ background: 'transparent', border: 'none', cursor: 'pointer' }}
      >
        <StatusIcon status={status} />
        <span className="text-[11px] font-semibold flex-1 truncate" style={{ color: '#1A1A1A' }}>
          {agentId}
        </span>
        {status === 'running' && (
          <span className="text-[10px] flex-shrink-0" style={{ color: '#9CA3AF' }}>
            {elapsed(startTime)}
          </span>
        )}
        <span className="text-[10px] flex-shrink-0" style={{ color: '#9CA3AF' }}>
          {expanded ? '▼' : '▶'}
        </span>
      </button>

      {/* Task description */}
      {task && (
        <p className="px-3 pb-1 text-[10px] truncate" style={{ color: '#6B7280' }}>
          {task.slice(0, 60)}{task.length > 60 ? '…' : ''}
        </p>
      )}

      {/* Steps timeline */}
      {expanded && steps.length > 0 && (
        <div
          className="mx-3 mb-2 overflow-y-auto"
          style={{
            maxHeight: 240,
            borderTop: '1px solid #EAE6DF',
            paddingTop: 6,
          }}
        >
          {steps.map((s, i) => (
            <div key={i} className="flex items-start gap-1.5 mb-1">
              {/* Step number */}
              <span
                className="flex-shrink-0 text-[9px] font-mono font-bold rounded px-1 mt-0.5"
                style={{ background: '#EDE9FE', color: '#7C3AED', minWidth: 20, textAlign: 'center' }}
              >
                {s.step}
              </span>
              {/* Tool */}
              <span
                className="flex-shrink-0 text-[10px] font-semibold"
                style={{ color: '#5B21B6', minWidth: 84 }}
              >
                {s.action}
              </span>
              {/* Observation preview */}
              {s.observation && (
                <span
                  className="text-[10px] leading-relaxed"
                  style={{ color: '#6B7280', wordBreak: 'break-word' }}
                  title={s.observation}
                >
                  → {s.observation.slice(0, 90)}{s.observation.length > 90 ? '…' : ''}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {expanded && steps.length === 0 && status === 'running' && (
        <p className="px-3 pb-2 text-[10px] italic" style={{ color: '#9CA3AF' }}>
          Starting…
        </p>
      )}
    </div>
  )
}

// ── LiveAgentMonitor (main component) ─────────────────────────────────────────

export default function LiveAgentMonitor({ agents = {}, connected, onClose, onSpawnAgent }) {
  const [task, setTask] = useState('')
  const [spawning, setSpawning] = useState(false)
  const [spawnErr, setSpawnErr] = useState(null)
  const bottomRef = useRef(null)

  const agentIds = Object.keys(agents)
  const runningCount = agentIds.filter(id => agents[id]?.status === 'running').length

  // Auto-scroll to bottom when new agents/steps arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [agents])

  const handleSpawn = async () => {
    if (!task.trim()) return
    setSpawning(true)
    setSpawnErr(null)
    try {
      if (onSpawnAgent) await onSpawnAgent(task.trim())
      setTask('')
    } catch (e) {
      setSpawnErr(e.message)
    } finally {
      setSpawning(false)
    }
  }

  return (
    <aside
      className="flex flex-col flex-shrink-0 overflow-hidden"
      style={{ width: 300, background: '#FBF8F4', borderLeft: '1px solid #EAE6DF' }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 flex-shrink-0"
        style={{ height: 44, borderBottom: '1px solid #EAE6DF' }}
      >
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-semibold text-[#6B7280] uppercase tracking-wider">
            AGENTS
          </span>
          {runningCount > 0 && (
            <span
              className="text-[9px] font-medium px-1.5 py-0.5 rounded-full"
              style={{ background: '#EDE9FE', color: '#7C3AED' }}
            >
              {runningCount} running
            </span>
          )}
        </div>
        <button
          onClick={onClose}
          className="text-[#9CA3AF] hover:text-[#1A1A1A] transition-colors text-xs"
        >
          ✕
        </button>
      </div>

      {/* Agent list */}
      <div className="flex-1 overflow-y-auto px-3 py-3">
        {agentIds.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12">
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center mb-3"
              style={{ background: '#F3F0FF' }}
            >
              <span style={{ fontSize: 16 }}>⚡</span>
            </div>
            <p className="text-[11px] text-[#9CA3AF] text-center">
              No agents running
            </p>
            <p className="text-[10px] text-[#C4C0BC] text-center mt-1">
              Use the input below to spawn one
            </p>
          </div>
        ) : (
          agentIds.map(id => (
            <AgentCard key={id} agentId={id} info={agents[id]} />
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {/* Spawn agent input */}
      <div style={{ borderTop: '1px solid #EAE6DF', padding: '10px 12px' }}>
        <p className="text-[9px] font-semibold text-[#9CA3AF] uppercase tracking-wider mb-1.5">
          Spawn Agent
        </p>
        <div className="flex gap-1.5">
          <input
            type="text"
            value={task}
            onChange={e => setTask(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSpawn()}
            placeholder="Research Python gesture libs..."
            className="flex-1 text-[11px] px-2 py-1.5 outline-none"
            style={{
              border: '1px solid #E5E4E0',
              background: '#FAFAF8',
              color: '#1A1A1A',
              fontFamily: 'inherit',
            }}
            onFocus={e => (e.target.style.borderColor = '#7C3AED')}
            onBlur={e => (e.target.style.borderColor = '#E5E4E0')}
          />
          <button
            onClick={handleSpawn}
            disabled={spawning || !task.trim()}
            className="px-3 py-1.5 text-[10px] font-semibold text-white transition-opacity"
            style={{
              background: '#7C3AED',
              border: 'none',
              cursor: spawning || !task.trim() ? 'not-allowed' : 'pointer',
              opacity: spawning || !task.trim() ? 0.5 : 1,
              fontFamily: 'inherit',
            }}
          >
            {spawning ? '…' : 'Go'}
          </button>
        </div>
        {spawnErr && (
          <p className="mt-1 text-[10px]" style={{ color: '#EF4444' }}>{spawnErr}</p>
        )}
        <div
          className="flex items-center gap-1.5 mt-2"
          style={{ color: connected ? '#9CA3AF' : '#EF4444' }}
        >
          <span
            className="w-1.5 h-1.5 rounded-full"
            style={{ background: connected ? '#22C55E' : '#EF4444', flexShrink: 0 }}
          />
          <span className="text-[9px]">{connected ? 'Bus connected' : 'Bus offline'}</span>
        </div>
      </div>
    </aside>
  )
}
