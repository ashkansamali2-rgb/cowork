import React, { useState, useRef, useCallback, useEffect } from 'react'

const TEXT_EXTENSIONS = new Set([
  'txt', 'md', 'py', 'js', 'ts', 'jsx', 'tsx', 'json', 'yaml', 'yml',
  'toml', 'ini', 'env', 'sh', 'bash', 'zsh', 'html', 'css', 'scss',
  'sql', 'rs', 'go', 'java', 'c', 'cpp', 'h', 'rb', 'php', 'swift',
  'kt', 'cs', 'xml', 'csv', 'log', 'conf', 'cfg', 'ts', 'tsx',
])
const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'])

export default function InputBar({ onSend, onStop, isStreaming, connected }) {
  const [text, setText] = useState('')
  const [attachedFiles, setAttachedFiles] = useState([])
  const textareaRef = useRef(null)
  const fileInputRef = useRef(null)

  useEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 160) + 'px'
  }, [text])

  const handleClick = useCallback(() => {
    if (isStreaming) {
      if (onStop) onStop()
      return
    }

    const trimmed = text.trim()
    if (!trimmed && attachedFiles.length === 0) return

    let finalMessage = trimmed
    for (const f of attachedFiles) {
      if (f.type === 'text' && f.contents != null) {
        const ext = f.name.split('.').pop() || ''
        finalMessage += `\n\n[Attached file: ${f.name}]\n\`\`\`${ext}\n${f.contents}\n\`\`\``
      } else if (f.type === 'image') {
        finalMessage += `\n\n[Attached image: ${f.name}]`
      }
    }

    if (!finalMessage.trim()) return
    onSend(finalMessage)
    setText('')
    setAttachedFiles([])
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }, [text, attachedFiles, isStreaming, onSend, onStop])

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleClick()
    }
  }

  const handleAttachClick = () => {
    fileInputRef.current?.click()
  }

  const handleFileChange = async (e) => {
    const files = Array.from(e.target.files || [])
    if (files.length === 0) return
    e.target.value = ''

    const newAttachments = []
    for (const file of files) {
      const ext = file.name.split('.').pop()?.toLowerCase() || ''
      if (IMAGE_EXTENSIONS.has(ext)) {
        const base64 = await new Promise(resolve => {
          const reader = new FileReader()
          reader.onload = ev => resolve(ev.target.result)
          reader.readAsDataURL(file)
        })
        newAttachments.push({ name: file.name, type: 'image', base64, path: file.path })
      } else {
        let contents = ''
        try {
          if (window.jarvis?.readFile && file.path) {
            const result = await window.jarvis.readFile(file.path)
            contents = result.contents
          } else {
            contents = await new Promise(resolve => {
              const reader = new FileReader()
              reader.onload = ev => resolve(ev.target.result)
              reader.readAsText(file)
            })
          }
        } catch (err) {
          console.error('[Attach] failed to read file:', err)
        }
        newAttachments.push({ name: file.name, type: 'text', contents, path: file.path })
      }
    }

    setAttachedFiles(prev => [...prev, ...newAttachments])
  }

  const removeFile = (index) => {
    setAttachedFiles(prev => prev.filter((_, i) => i !== index))
  }

  const canSend = (text.trim().length > 0 || attachedFiles.length > 0) || isStreaming

  return (
    <div
      className="flex-shrink-0 bg-[#FBF8F4]"
      style={{ borderTop: '1px solid #EAE6DF' }}
    >
      <div className="mx-auto px-5 pt-3 pb-4" style={{ maxWidth: 660 }}>

        {/* File chips */}
        {attachedFiles.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {attachedFiles.map((f, i) => (
              <span key={i} className="file-pill">
                {f.type === 'image' ? (
                  <img src={f.base64} alt={f.name} style={{ width: 14, height: 14, objectFit: 'cover', flexShrink: 0 }} />
                ) : (
                  <svg width="11" height="11" viewBox="0 0 12 12" fill="none" style={{ flexShrink: 0 }}>
                    <rect x="1" y="0.5" width="10" height="11" rx="1.5" stroke="#7C3AED" strokeWidth="1" />
                    <path d="M3 4h6M3 6h6M3 8h4" stroke="#7C3AED" strokeWidth="1" strokeLinecap="round" />
                  </svg>
                )}
                {f.name}
                <button onClick={() => removeFile(i)} title="Remove">×</button>
              </span>
            ))}
          </div>
        )}

        {/* Input row */}
        <div
          className="flex items-end gap-2 bg-white px-3 py-2"
          style={{ border: '1px solid #E5E0D8' }}
        >
          {/* Hidden file input — multiple */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
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
            className="flex-1 bg-transparent text-sm text-[#1A1A1A] placeholder-[#C4BFB8] border-none outline-none leading-relaxed py-1 min-h-[24px] max-h-40 disabled:opacity-70"
            style={{ resize: 'none', overflow: 'hidden', fontFamily: 'inherit' }}
          />

          {/* Send/Stop */}
          <button
            onClick={handleClick}
            disabled={!canSend}
            className={`flex-shrink-0 mb-0.5 px-3 py-1 text-xs font-medium transition-colors ${isStreaming ? 'bg-red-500 text-white hover:bg-red-600' : 'btn-purple'
              }`}
            style={{ borderRadius: 0 }}
            title={isStreaming ? 'Stop generation' : 'Send (Enter)'}
          >
            {isStreaming ? 'STOP ⏹' : 'Send'}
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
