import React, { useEffect, useRef, useState } from 'react'
import MessageBubble from './MessageBubble.jsx'

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full pb-24 px-8">
      <div
        className="w-8 h-8 flex items-center justify-center mb-5"
        style={{ background: '#7C3AED' }}
      >
        <svg width="14" height="14" viewBox="0 0 18 18" fill="none">
          <circle cx="9" cy="9" r="6" stroke="white" strokeWidth="1.5" />
          <circle cx="9" cy="9" r="2.5" fill="white" />
        </svg>
      </div>
      <p className="text-sm font-medium text-[#1A1A1A] mb-1">Cowork</p>
      <p className="text-xs text-[#9CA3AF] text-center max-w-[200px] leading-relaxed">
        Type a message below to start.
      </p>
    </div>
  )
}

function AgentProgress({ agentId, steps }) {
  const [collapsed, setCollapsed] = useState(false)
  const isActive = steps.length > 0 && steps[steps.length - 1]?.action !== 'FINAL_ANSWER'

  return (
    <div
      style={{
        border: '1px solid #E5E0D8',
        borderLeft: '3px solid #F59E0B',
        background: '#FFFBF0',
        borderRadius: 2,
        marginBottom: 8,
      }}
    >
      {/* Header */}
      <button
        onClick={() => setCollapsed(c => !c)}
        className="w-full flex items-center justify-between px-3 py-2 text-left"
        style={{ background: 'transparent', border: 'none', cursor: 'pointer' }}
      >
        <span className="flex items-center gap-2">
          {isActive && (
            <span
              style={{
                display: 'inline-block',
                width: 7,
                height: 7,
                borderRadius: '50%',
                background: '#F59E0B',
                animation: 'pulse 1.4s ease-in-out infinite',
              }}
            />
          )}
          <span className="text-xs font-semibold" style={{ color: '#B45309' }}>
            Agent {agentId}
          </span>
          <span className="text-xs" style={{ color: '#9CA3AF' }}>
            {steps.length} step{steps.length !== 1 ? 's' : ''}
          </span>
        </span>
        <span className="text-xs" style={{ color: '#9CA3AF' }}>
          {collapsed ? '▶' : '▼'}
        </span>
      </button>

      {/* Steps timeline */}
      {!collapsed && (
        <div className="px-3 pb-3 space-y-1">
          {steps.map((s, i) => (
            <div key={i} className="flex items-start gap-2">
              {/* Step number pill */}
              <span
                className="flex-shrink-0 text-[10px] font-mono font-bold rounded px-1"
                style={{ background: '#FEF3C7', color: '#B45309', marginTop: 1 }}
              >
                {s.step}
              </span>
              {/* Tool name */}
              <span
                className="text-[11px] font-semibold flex-shrink-0"
                style={{ color: '#92400E', minWidth: 80 }}
              >
                {s.action}
              </span>
              {/* Result preview */}
              {s.observation && (
                <span
                  className="text-[11px] truncate"
                  style={{ color: '#6B7280' }}
                  title={s.observation}
                >
                  → {s.observation.slice(0, 120)}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function ChatArea({ messages, statusText, agentSteps = {} }) {
  const bottomRef = useRef(null)
  const agentIds = Object.keys(agentSteps)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, statusText, agentSteps])

  if (messages.length === 0 && agentIds.length === 0) {
    return (
      <div className="flex-1 overflow-y-auto flex items-center justify-center bg-[#FBF8F4]">
        <EmptyState />
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto bg-[#FBF8F4]">
      <div className="mx-auto w-full px-6 pt-12 pb-6 space-y-10" style={{ maxWidth: 660 }}>
        {messages.map((msg, idx) => (
          <MessageBubble key={msg.id || idx} message={msg} />
        ))}

        {/* Agent progress sections */}
        {agentIds.length > 0 && (
          <div>
            {agentIds.map(aid => (
              <AgentProgress key={aid} agentId={aid} steps={agentSteps[aid] || []} />
            ))}
          </div>
        )}

        {statusText && (
          <div className="pl-9">
            <span className="text-[11px] text-[#9CA3AF] italic">{statusText}</span>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  )
}
