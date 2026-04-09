import React from 'react'

const AGENT_DEFS = [
  { key: 'gemma',    label: 'Gemma',    desc: 'Vision + reasoning' },
  { key: 'qwen',     label: 'Qwen',     desc: 'Code generation' },
  { key: 'cantivia', label: 'Cantivia', desc: 'Repo automation' },
]

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  const now = new Date()
  const diff = now - d
  if (diff < 60000) return 'just now'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export default function Sidebar({ chats, activeChatId, agentStatuses, connections, onNewChat, onSelectChat }) {
  return (
    <aside
      className="flex flex-col flex-shrink-0 overflow-hidden border-r border-[#EAE6DF]"
      style={{ width: 200, background: '#F5F1EB' }}
    >
      {/* Traffic lights space (macOS frameless) */}
      <div className="h-10 flex-shrink-0 drag-region" />

      {/* Wordmark */}
      <div className="px-4 pb-3 flex-shrink-0">
        <span className="text-sm font-bold text-[#7C3AED] tracking-tight">Cowork</span>
      </div>

      {/* New Chat */}
      <div className="px-3 pb-4 flex-shrink-0">
        <button
          onClick={onNewChat}
          className="btn-purple no-drag w-full py-1.5 text-xs font-medium"
          style={{ borderRadius: 0 }}
        >
          New Chat
        </button>
      </div>

      {/* Scrollable nav */}
      <div className="flex-1 overflow-y-auto min-h-0 px-3 pb-3">

        {/* CHATS section */}
        <p className="text-[10px] font-semibold text-[#9CA3AF] uppercase tracking-wider px-1 mb-1">
          Chats
        </p>

        {chats.length === 0 ? (
          <p className="px-1 py-2 text-xs text-[#9CA3AF]">No chats yet</p>
        ) : (
          <div className="space-y-px mb-4">
            {chats.map(chat => (
              <button
                key={chat.id}
                onClick={() => onSelectChat(chat)}
                className={`no-drag w-full text-left px-2 py-1.5 text-xs transition-colors ${
                  chat.id === activeChatId
                    ? 'chat-item-active'
                    : 'text-[#1A1A1A] hover:bg-[#EDE9FE]'
                }`}
                style={{
                  borderLeft: chat.id === activeChatId ? '2px solid #7C3AED' : '2px solid transparent',
                }}
              >
                <p className="truncate font-medium">{chat.title || 'Untitled Chat'}</p>
                {chat.updatedAt && (
                  <p className="text-[10px] text-[#9CA3AF] mt-0.5">{formatTime(chat.updatedAt)}</p>
                )}
              </button>
            ))}
          </div>
        )}

        {/* AGENTS section */}
        <p className="text-[10px] font-semibold text-[#9CA3AF] uppercase tracking-wider px-1 mb-2 mt-4">
          Agents
        </p>
        <div className="space-y-1 px-1">
          {AGENT_DEFS.map(agent => {
            const status = agentStatuses[agent.key] || 'idle'
            const running = status === 'running' || status === 'active'
            return (
              <div key={agent.key} className="flex items-center gap-2 py-0.5">
                <span
                  className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                  style={{ backgroundColor: running ? '#22C55E' : '#D1D5DB' }}
                />
                <span className="text-xs text-[#1A1A1A] truncate">{agent.label}</span>
                <span className="text-[10px] text-[#9CA3AF] ml-auto">{status}</span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Connection status — bottom */}
      <div className="flex-shrink-0 border-t border-[#EAE6DF] px-4 py-2.5">
        <p
          className="text-[11px]"
          style={{ color: connections.jarvis ? '#9CA3AF' : '#EF4444' }}
        >
          {connections.jarvis ? '● Connected' : '○ Offline'}
        </p>
      </div>
    </aside>
  )
}
