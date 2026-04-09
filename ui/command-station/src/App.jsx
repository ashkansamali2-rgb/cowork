import React, { useState, useEffect, useCallback, useRef } from 'react'
import Sidebar from './components/Sidebar.jsx'
import TopBar from './components/TopBar.jsx'
import ChatArea from './components/ChatArea.jsx'
import InputBar from './components/InputBar.jsx'
import AgentSpawner from './components/AgentSpawner.jsx'

function generateId() {
  return `chat_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

function getChatTitle(messages) {
  const first = messages.find(m => m.role === 'user')
  if (!first) return 'New Chat'
  const text = first.content.slice(0, 40)
  return text.length < first.content.length ? text + '...' : text
}

const TYPING_ID = '__typing__'

export default function App() {
  const [chats, setChats] = useState([])
  const [activeChatId, setActiveChatId] = useState(null)
  const [messages, setMessages] = useState([])
  const [connections, setConnections] = useState({ jarvis: false, bus: false })
  const [agentStatuses, setAgentStatuses] = useState({
    gemma: 'idle', qwen: 'idle', cantivia: 'idle',
  })
  const [taskProgress, setTaskProgress] = useState([])
  const [spawnerOpen, setSpawnerOpen] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [statusText, setStatusText] = useState('')   // subtle status indicator

  const activeChatIdRef = useRef(null)
  activeChatIdRef.current = activeChatId

  // ── Setup listeners on mount ────────────────────────────────────────────────
  useEffect(() => {
    const api = window.jarvis
    if (!api) return

    api.loadChats().then(loaded => setChats(loaded || [])).catch(console.error)
    api.getConnectionStatus().then(s => setConnections({ jarvis: s.jarvis, bus: s.bus })).catch(() => {})

    // Stream handler — only 'final' type messages arrive here (after main.js routing)
    const handleStream = (data) => {
      if (data.done) {
        setIsStreaming(false)
        setStatusText('')
        // Finalize: mark last assistant message as not streaming
        setMessages(prev => {
          const updated = prev.map(m =>
            m.id === TYPING_ID
              ? null  // remove stale typing bubble if final arrived without content
              : m.role === 'assistant' && m.streaming
              ? { ...m, streaming: false }
              : m
          ).filter(Boolean)
          return updated
        })
      } else if (data.content) {
        setIsStreaming(true)
        setMessages(prev => {
          // Replace typing bubble with real content, or append to existing streaming msg
          const withoutTyping = prev.filter(m => m.id !== TYPING_ID)
          const last = withoutTyping[withoutTyping.length - 1]
          if (last && last.role === 'assistant' && last.streaming) {
            return [
              ...withoutTyping.slice(0, -1),
              { ...last, content: last.content + data.content },
            ]
          }
          return [
            ...withoutTyping,
            {
              id: `msg_${Date.now()}`,
              role: 'assistant',
              content: data.content,
              streaming: true,
              timestamp: Date.now(),
            },
          ]
        })
      }
    }

    // Status handler — show as subtle text indicator, not a chat bubble
    const handleStatus = (data) => {
      if (data.text) setStatusText(data.text)
    }

    const handleBusEvent = (event) => {
      if (event.type === 'agent_status') {
        setAgentStatuses(prev => ({ ...prev, [event.agent]: event.status }))
      } else if (event.type === 'task_progress' || event.type === 'spawn_progress') {
        setTaskProgress(prev => [...prev, {
          id: Date.now(),
          text: event.message || event.content || JSON.stringify(event),
          timestamp: Date.now(),
        }])
      }
    }

    const handleConnectionStatus = (data) => {
      setConnections(prev => ({ ...prev, [data.service]: data.connected }))
    }

    api.onStream(handleStream)
    api.onStatusMessage(handleStatus)
    api.onBusEvent(handleBusEvent)
    api.onConnectionStatus(handleConnectionStatus)

    return () => {
      api.removeAllListeners('chat:stream')
      api.removeAllListeners('chat:status')
      api.removeAllListeners('bus:event')
      api.removeAllListeners('connection:status')
    }
  }, [])

  // ── Auto-save ───────────────────────────────────────────────────────────────
  const saveChatRef = useRef(null)
  useEffect(() => {
    if (messages.length === 0 || isStreaming) return
    const api = window.jarvis
    if (!api) return

    clearTimeout(saveChatRef.current)
    saveChatRef.current = setTimeout(() => {
      const chat = {
        id: activeChatIdRef.current,
        title: getChatTitle(messages),
        messages: messages
          .filter(m => m.id !== TYPING_ID)
          .map(m => ({ ...m, streaming: false })),
        updatedAt: Date.now(),
      }
      api.saveChat(chat).then(() => {
        setChats(prev => {
          const idx = prev.findIndex(c => c.id === activeChatIdRef.current)
          if (idx >= 0) {
            const updated = [...prev]
            updated[idx] = chat
            return updated
          }
          return [chat, ...prev]
        })
      }).catch(console.error)
    }, 1000)
  }, [messages, isStreaming])

  // ── Actions ─────────────────────────────────────────────────────────────────
  const handleNewChat = useCallback(() => {
    setActiveChatId(generateId())
    setMessages([])
    setIsStreaming(false)
    setStatusText('')
  }, [])

  const handleSelectChat = useCallback((chat) => {
    setActiveChatId(chat.id)
    setMessages(chat.messages || [])
    setIsStreaming(false)
    setStatusText('')
  }, [])

  const handleSendMessage = useCallback(async (text) => {
    if (!text.trim() || isStreaming) return
    const api = window.jarvis
    if (!api) return

    let chatId = activeChatIdRef.current
    if (!chatId) {
      chatId = generateId()
      setActiveChatId(chatId)
    }

    const userMsg = {
      id: `msg_${Date.now()}`,
      role: 'user',
      content: text.trim(),
      timestamp: Date.now(),
    }

    // Push user message + immediate typing bubble
    const typingBubble = {
      id: TYPING_ID,
      role: 'assistant',
      typing: true,
      timestamp: Date.now(),
    }
    setMessages(prev => [...prev, userMsg, typingBubble])
    setIsStreaming(true)

    try {
      await api.sendMessage(text.trim())
    } catch (err) {
      // Remove typing bubble, show error
      setMessages(prev => [
        ...prev.filter(m => m.id !== TYPING_ID),
        {
          id: `msg_${Date.now()}`,
          role: 'assistant',
          content: `Error: ${err.message}`,
          error: true,
          timestamp: Date.now(),
        },
      ])
      setIsStreaming(false)
      setStatusText('')
    }
  }, [isStreaming])

  return (
    <div className="flex flex-col h-screen bg-[#FBF8F4] text-[#1A1A1A] overflow-hidden">
      <TopBar
        connections={connections}
        spawnerOpen={spawnerOpen}
        onToggleSpawner={() => setSpawnerOpen(o => !o)}
      />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          chats={chats}
          activeChatId={activeChatId}
          agentStatuses={agentStatuses}
          connections={connections}
          onNewChat={handleNewChat}
          onSelectChat={handleSelectChat}
        />
        <main className="flex flex-col flex-1 overflow-hidden bg-[#FBF8F4]">
          <ChatArea
            messages={messages}
            statusText={statusText}
          />
          <InputBar
            onSend={handleSendMessage}
            isStreaming={isStreaming}
            connected={connections.jarvis}
          />
        </main>
        {spawnerOpen && (
          <AgentSpawner
            taskProgress={taskProgress}
            connected={connections.bus}
            onClose={() => setSpawnerOpen(false)}
          />
        )}
      </div>
    </div>
  )
}
