import React, { useEffect, useRef } from 'react'
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

export default function ChatArea({ messages, statusText }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, statusText])

  if (messages.length === 0) {
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
