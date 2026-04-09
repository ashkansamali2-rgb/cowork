import React, { useState, useRef, useCallback, useEffect } from 'react'

export default function InputBar({ onSend, isStreaming, connected }) {
  const [text, setText] = useState('')
  const [attachedFile, setAttachedFile] = useState(null)
  const textareaRef = useRef(null)
  const fileInputRef = useRef(null)

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 160) + 'px'
  }, [text])

  const handleSend = useCallback(() => {
    const trimmed = text.trim()
    if (!trimmed || isStreaming) return
    onSend(trimmed)
    setText('')
    setAttachedFile(null)
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }, [text, isStreaming, onSend])

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleAttachClick = () => {
    fileInputRef.current?.click()
  }

  const handleFileChange = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    console.log('[Attach] file selected:', file.path || file.name)
    setAttachedFile({ name: file.name, path: file.path || file.name })
    // Reset so same file can be re-selected
    e.target.value = ''
  }

  const canSend = text.trim().length > 0 && !isStreaming

  return (
    <div
      className="flex-shrink-0 bg-[#FBF8F4]"
      style={{ borderTop: '1px solid #EAE6DF' }}
    >
      <div className="mx-auto px-5 pt-3 pb-4" style={{ maxWidth: 660 }}>

        {/* File chip — shown when a file is attached */}
        {attachedFile && (
          <div className="mb-2">
            <span className="file-pill">
              <svg width="11" height="11" viewBox="0 0 12 12" fill="none" style={{ flexShrink: 0 }}>
                <rect x="1" y="0.5" width="10" height="11" rx="1.5" stroke="#7C3AED" strokeWidth="1"/>
                <path d="M3 4h6M3 6h6M3 8h4" stroke="#7C3AED" strokeWidth="1" strokeLinecap="round"/>
              </svg>
              {attachedFile.name}
              <button onClick={() => setAttachedFile(null)} title="Remove">×</button>
            </span>
          </div>
        )}

        {/* Input row */}
        <div
          className="flex items-end gap-2 bg-white px-3 py-2"
          style={{ border: '1px solid #E5E0D8' }}
        >
          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            onChange={handleFileChange}
          />

          {/* Attach */}
          <button
            onClick={handleAttachClick}
            className="btn-ghost flex-shrink-0 mb-0.5 px-1.5 py-1 text-xs"
            title="Attach file"
          >
            Attach
          </button>

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              !connected
                ? 'Jarvis offline...'
                : isStreaming
                ? 'Responding...'
                : 'Message Jarvis'
            }
            disabled={isStreaming}
            rows={1}
            className="flex-1 bg-transparent text-sm text-[#1A1A1A] placeholder-[#C4BFB8] border-none outline-none leading-relaxed py-1 min-h-[24px] max-h-40 disabled:opacity-40"
            style={{ resize: 'none', overflow: 'hidden', fontFamily: 'inherit' }}
          />

          {/* Send */}
          <button
            onClick={handleSend}
            disabled={!canSend}
            className="flex-shrink-0 mb-0.5 btn-purple px-3 py-1 text-xs font-medium"
            style={{ borderRadius: 0 }}
            title="Send (Enter)"
          >
            {isStreaming ? '...' : 'Send'}
          </button>
        </div>

        {/* Hint */}
        <p className="text-[10px] text-[#C4BFB8] mt-1.5 text-center">
          Enter to send · Shift+Enter for newline
          {!connected && (
            <span className="ml-2 text-red-400">· Jarvis offline</span>
          )}
        </p>
      </div>
    </div>
  )
}
