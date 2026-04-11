import React, { useMemo } from 'react'

// Strip ANSI escape codes
const stripAnsi = (str) => typeof str === 'string' ? str.replace(/\x1b\[[0-9;]*m/g, '') : str

function formatContent(content) {
  const parts = content.split(/(```[\s\S]*?```)/g)
  return parts.map((part, i) => {
    if (part.startsWith('```')) {
      const lines = part.split('\n')
      const lang = lines[0].replace('```', '').trim()
      const code = lines.slice(1, -1).join('\n')
      return (
        <pre
          key={i}
          className="overflow-x-auto my-4 text-xs font-mono"
          style={{
            background: '#F4F1EC',
            border: '1px solid #E5E0D8',
            padding: '12px 14px',
          }}
        >
          {lang && (
            <span className="block text-[10px] text-[#9CA3AF] mb-2 font-sans uppercase tracking-wide">
              {lang}
            </span>
          )}
          <code className="text-[#1A1A1A]">{code}</code>
        </pre>
      )
    }
    return (
      <span key={i}>
        {part.split('\n').map((line, li, arr) => (
          <React.Fragment key={li}>
            {line}
            {li < arr.length - 1 && <br />}
          </React.Fragment>
        ))}
      </span>
    )
  })
}

function formatTime(ts) {
  if (!ts) return ''
  return new Date(ts).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

export default function MessageBubble({ message }) {
  const { role, content, streaming, error, typing, timestamp } = message
  const isUser = role === 'user'
  // Safely convert content: strip ANSI, stringify objects
  const safeStr = useMemo(() => {
    if (content === null || content === undefined) return ''
    if (typeof content === 'object') return JSON.stringify(content)
    return stripAnsi(String(content))
  }, [content])
  const formattedContent = useMemo(() => formatContent(safeStr), [safeStr])

  // Typing bubble — three pulsing dots
  if (typing) {
    return (
      <div className="flex items-start gap-3">
        <div
          className="w-6 h-6 flex items-center justify-center flex-shrink-0 text-[11px] font-bold text-white mt-0.5"
          style={{ background: '#7C3AED' }}
        >
          J
        </div>
        <div
          className="flex items-center gap-1.5 px-3"
          style={{ borderLeft: '2px solid #7C3AED', paddingTop: 8, paddingBottom: 8 }}
        >
          {[0, 1, 2].map(i => (
            <span
              key={i}
              className="typing-dot"
              style={{ animationDelay: `${i * 0.18}s` }}
            />
          ))}
        </div>
      </div>
    )
  }

  // User message — right-aligned purple rectangle
  if (isUser) {
    return (
      <div className="flex justify-end">
        <div style={{ maxWidth: '68%' }}>
          <div
            className="px-4 py-3"
            style={{ background: '#7C3AED' }}
          >
            <p className="text-sm text-white leading-relaxed whitespace-pre-wrap">{safeStr}</p>
          </div>
          <p className="text-[10px] text-[#9CA3AF] text-right mt-1.5">{formatTime(timestamp)}</p>
        </div>
      </div>
    )
  }

  // Jarvis — left border accent, open layout
  return (
    <div className="flex items-start gap-3">
      <div
        className="w-6 h-6 flex items-center justify-center flex-shrink-0 text-[11px] font-bold text-white mt-0.5"
        style={{ background: '#7C3AED' }}
      >
        J
      </div>

      <div className="flex-1 min-w-0">
        <div
          className="pl-3 py-0.5"
          style={{
            borderLeft: `2px solid ${error ? '#EF4444' : '#7C3AED'}`,
          }}
        >
          <div
            className={`text-sm leading-relaxed message-content ${error ? 'text-red-600' : 'text-[#1A1A1A]'}`}
          >
            {formattedContent}
            {streaming && (
              <span
                className="inline-block w-px h-4 ml-0.5 align-middle"
                style={{
                  background: '#7C3AED',
                  animation: 'blink 1s step-end infinite',
                }}
              />
            )}
          </div>
        </div>
        <p className="text-[10px] text-[#9CA3AF] mt-2 pl-3">
          {formatTime(timestamp)}
        </p>
      </div>
    </div>
  )
}
