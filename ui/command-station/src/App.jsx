import React, { useState, useEffect, useCallback, useRef } from 'react'
import Sidebar from './components/Sidebar.jsx'
import TopBar from './components/TopBar.jsx'
import ChatArea from './components/ChatArea.jsx'
import InputBar from './components/InputBar.jsx'
import AgentSpawner from './components/AgentSpawner.jsx'
import KnowledgeGraph from './components/KnowledgeGraph.jsx'

function generateId() {
  return `chat_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

// Strip ANSI escape codes from strings
const stripAnsi = (str) => typeof str === 'string' ? str.replace(/\x1b\[[0-9;]*m/g, '') : str

// Safely convert message content to a displayable string
function safeContent(content) {
  if (content === null || content === undefined) return ''
  if (typeof content === 'string') return stripAnsi(content)
  if (typeof content === 'object') return JSON.stringify(content)
  return String(content)
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
    cantivia: 'idle',
  })
  // Structured agent registry: { [agentId]: { task, status, steps, startTime } }
  const [agents, setAgents] = useState({})
  const agentsRef = useRef({})
  const [agentDone, setAgentDone] = useState(false)
  const [taskProgress, setTaskProgress] = useState([])
  const [spawnerOpen, setSpawnerOpen] = useState(false)
  const [activeTab, setActiveTab] = useState('chat')
  const [showGraph, setShowGraph] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [statusText, setStatusText] = useState('')
  const [isTyping, setIsTyping] = useState(false)

  // Track the last sent user message for agent task labels
  const lastUserMsgRef = useRef('')

  // Projects state
  const [projects, setProjects] = useState([])
  const [activeProject, setActiveProject] = useState(null)
  const [projectChats, setProjectChats] = useState({})
  const [projectFiles, setProjectFiles] = useState({})
  const isFirstMessageRef = useRef(true)
  const projectFilesRef = useRef({})

  const activeChatIdRef = useRef(null)
  activeChatIdRef.current = activeChatId

  const activeProjectRef = useRef(null)
  activeProjectRef.current = activeProject

  projectFilesRef.current = projectFiles

  // ── Setup listeners on mount ────────────────────────────────────────────────
  useEffect(() => {
    const api = window.jarvis
    if (!api) return

    api.loadChats().then(loaded => {
      const chatsLoaded = loaded || []
      setChats(chatsLoaded)
      const savedId = localStorage.getItem('activeChatId')
      const toRestore = savedId
        ? chatsLoaded.find(c => c.id === savedId) || chatsLoaded[0]
        : chatsLoaded[0]
      if (toRestore) {
        setActiveChatId(toRestore.id)
        setMessages(toRestore.messages || [])
        isFirstMessageRef.current = false
        localStorage.setItem('activeChatId', toRestore.id)
      }
    }).catch(console.error)
    api.getConnectionStatus().then(s => setConnections({ jarvis: s.jarvis, bus: s.bus })).catch(() => { })

    // Load projects
    api.listProjects().then(loaded => setProjects(loaded || [])).catch(console.error)

    const handleStream = (data) => {
      console.log('[WS]', data)

      // "ack" type: never add to chat, just show typing indicator
      if (data.type === 'ack') {
        setIsTyping(true)
        return
      }

      // "status" type: update typing indicator only, do NOT add as chat bubble
      if (data.type === 'status') {
        setIsTyping(true)
        if (data.text) setStatusText(data.text)
        return
      }

      // Agent announced → create entry immediately before first step
      if (data.type === 'agent_start') {
        const agentId = data.agent_id || data.agentId
        if (agentId) {
          const newAgents = {
            ...agentsRef.current,
            [agentId]: { task: data.task || lastUserMsgRef.current, status: 'running', steps: [], startTime: Date.now() },
          }
          agentsRef.current = newAgents
          setAgents(newAgents)
          setSpawnerOpen(true)
        }
        return
      }

      // Live agent step update → structured agents state + auto-open panel
      if (data.type === 'agent_update') {
        const agentId = data.agent_id || data.agentId
        const { step, action, observation } = data
        setAgents(prev => {
          const existing = prev[agentId] || { task: data.task || lastUserMsgRef.current, status: 'running', steps: [], startTime: Date.now() }
          const newAgents = {
            ...prev,
            [agentId]: { ...existing, status: 'running', steps: [...existing.steps, { step, action, observation }] },
          }
          agentsRef.current = newAgents
          return newAgents
        })
        setAgents(prev => ({ ...prev }))
        setSpawnerOpen(true)
        return
      }

      // "final" type: add as Jarvis response bubble, clear typing indicator
      if (data.type === 'final') {
        setIsTyping(false)
        setAgents(prev => {
          const updated = { ...prev }
          Object.keys(updated).forEach(id => {
            if (updated[id].status === 'running') updated[id] = { ...updated[id], status: 'done' }
          })
          return updated
        })
        setAgentDone(true)
        setTimeout(() => setAgentDone(false), 3500)
        setIsStreaming(false)
        setStatusText('')
        const msgContent = safeContent(data.msg || data.content || data.text)
        if (msgContent) {
          setMessages(prev => [
            ...prev.filter(m => m.id !== TYPING_ID),
            { id: `msg_${Date.now()}`, role: 'assistant', content: msgContent, timestamp: Date.now() },
          ])
        } else {
          setMessages(prev => prev.filter(m => m.id !== TYPING_ID))
        }
        return
      }

      // "error" type: clear typing, show error bubble
      if (data.type === 'error') {
        setIsTyping(false)
        setIsStreaming(false)
        setStatusText('')
        const errContent = safeContent(data.msg || data.content || data.text || 'An error occurred')
        setMessages(prev => [
          ...prev.filter(m => m.id !== TYPING_ID),
          { id: `msg_${Date.now()}`, role: 'assistant', content: errContent, error: true, timestamp: Date.now() },
        ])
        return
      }

      if (data.done) {
        setIsTyping(false)
        setIsStreaming(false)
        setStatusText('')
        setMessages(prev => {
          const updated = prev.map(m =>
            m.id === TYPING_ID
              ? null
              : m.role === 'assistant' && m.streaming
                ? { ...m, streaming: false }
                : m
          ).filter(Boolean)
          return updated
        })
      } else if (data.content) {
        setIsTyping(false)
        setIsStreaming(true)
        const chunk = safeContent(data.content)
        if (!chunk) return
        setMessages(prev => {
          const withoutTyping = prev.filter(m => m.id !== TYPING_ID)
          const last = withoutTyping[withoutTyping.length - 1]
          if (last && last.role === 'assistant' && last.streaming) {
            return [
              ...withoutTyping.slice(0, -1),
              { ...last, content: last.content + chunk },
            ]
          }
          return [
            ...withoutTyping,
            {
              id: `msg_${Date.now()}`,
              role: 'assistant',
              content: chunk,
              streaming: true,
              timestamp: Date.now(),
            },
          ]
        })
      }
    }

    const handleStatus = (data) => {
      if (data.text) setStatusText(data.text)
    }

    const handleBusEvent = (event) => {
      console.log('[WS bus]', event.type, event)
      if (event.type === 'agent_status') {
        setAgentStatuses(prev => ({ ...prev, [event.agent]: event.status }))
      } else if (event.type === 'AGENT_UPDATE' || event.type === 'agent_update') {
        const agentId = event.agent_id || event.agentId
        const { step, action, observation } = event
        setAgents(prev => {
          const existing = prev[agentId] || { task: event.task || '', status: 'running', steps: [], startTime: Date.now() }
          const newAgents = {
            ...prev,
            [agentId]: { ...existing, status: 'running', steps: [...existing.steps, { step, action, observation }] },
          }
          agentsRef.current = newAgents
          return newAgents
        })
        setAgents(prev => ({ ...prev }))
        setSpawnerOpen(true)
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
    // Only save when there are real user/assistant messages, not streaming, and we have an active chat ID
    if (messages.length === 0 || isStreaming) return
    if (!activeChatIdRef.current) return
    const realMessages = messages.filter(m => m.id !== TYPING_ID && (m.role === 'user' || m.role === 'assistant'))
    if (realMessages.length === 0) return
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
        projectName: activeProjectRef.current?.name || null,
      }
      api.saveChat(chat).then(() => {
        if (activeProjectRef.current) {
          // Update project chats
          setProjectChats(prev => {
            const projName = activeProjectRef.current.name
            const existing = prev[projName] || []
            const idx = existing.findIndex(c => c.id === chat.id)
            if (idx >= 0) {
              const updated = [...existing]
              updated[idx] = chat
              return { ...prev, [projName]: updated }
            }
            return { ...prev, [projName]: [chat, ...existing] }
          })
        } else {
          setChats(prev => {
            const idx = prev.findIndex(c => c.id === activeChatIdRef.current)
            if (idx >= 0) {
              const updated = [...prev]
              updated[idx] = chat
              return updated
            }
            return [chat, ...prev]
          })
        }
      }).catch(console.error)
    }, 1000)
  }, [messages, isStreaming])

  // ── Actions ─────────────────────────────────────────────────────────────────
  const handleNewChat = useCallback(() => {
    const newId = generateId()
    setActiveChatId(newId)
    localStorage.setItem('activeChatId', newId)
    setMessages([])
    setIsStreaming(false)
    setStatusText('')
    setActiveProject(null)
    isFirstMessageRef.current = true
  }, [])

  const handleSelectChat = useCallback((chat) => {
    setActiveChatId(chat.id)
    localStorage.setItem('activeChatId', chat.id)
    setMessages(chat.messages || [])
    setIsStreaming(false)
    setStatusText('')
    isFirstMessageRef.current = false
  }, [])

  const handleClearAllChats = useCallback(async () => {
    const api = window.jarvis
    if (!api) return
    if (!window.confirm('Delete all chats? This cannot be undone.')) return
    try {
      await api.clearAllChats()
      setChats([])
      setActiveChatId(null)
      setMessages([])
      localStorage.removeItem('activeChatId')
    } catch (err) {
      console.error('Failed to clear all chats:', err)
    }
  }, [])

  const handleDeleteChat = useCallback(async (chat) => {
    const api = window.jarvis
    if (!api) return
    if (!window.confirm('Delete this chat?')) return
    try {
      if (chat._filePath) await api.deleteChat(chat._filePath)
      if (activeProject) {
        setProjectChats(prev => {
          const projName = activeProject.name
          return { ...prev, [projName]: (prev[projName] || []).filter(c => c.id !== chat.id) }
        })
      } else {
        setChats(prev => prev.filter(c => c.id !== chat.id))
      }
      if (activeChatId === chat.id) {
        setActiveChatId(null)
        setMessages([])
      }
    } catch (err) {
      console.error('Failed to delete chat:', err)
    }
  }, [activeChatId, activeProject])

  const handleNewProjectChat = useCallback(async (project) => {
    const api = window.jarvis
    const chatId = generateId()
    setActiveChatId(chatId)
    setMessages([])
    setIsStreaming(false)
    setStatusText('')
    setActiveProject(project)
    isFirstMessageRef.current = true

    if (api) {
      if (!projectChats[project.name]) {
        const chats = await api.listProjectChats(project.name).catch(() => [])
        setProjectChats(prev => ({ ...prev, [project.name]: chats }))
      }
      const files = await api.listProjectFiles(project.name).catch(() => [])
      setProjectFiles(prev => ({ ...prev, [project.name]: files }))
    }
  }, [projectChats])

  const handleSelectProjectChatAndLoadChats = useCallback(async (project) => {
    const api = window.jarvis
    if (!api) return
    if (!projectChats[project.name]) {
      const chats = await api.listProjectChats(project.name).catch(() => [])
      setProjectChats(prev => ({ ...prev, [project.name]: chats }))
    }
    const files = await api.listProjectFiles(project.name).catch(() => [])
    setProjectFiles(prev => ({ ...prev, [project.name]: files }))
  }, [projectChats])

  const handleAddProjectFile = useCallback(async (projectName, filePath) => {
    const api = window.jarvis
    if (!api) return
    try {
      await api.addProjectFile(projectName, filePath)
      const files = await api.listProjectFiles(projectName)
      setProjectFiles(prev => ({ ...prev, [projectName]: files }))
    } catch (err) {
      console.error('Failed to add project file:', err)
    }
  }, [])

  const handleRemoveProjectFile = useCallback(async (projectName, filename) => {
    const api = window.jarvis
    if (!api) return
    try {
      await api.removeProjectFile(projectName, filename)
      setProjectFiles(prev => ({
        ...prev,
        [projectName]: (prev[projectName] || []).filter(f => f !== filename),
      }))
    } catch (err) {
      console.error('Failed to remove project file:', err)
    }
  }, [])

  const handleCreateProject = useCallback(async (name, context) => {
    const api = window.jarvis
    if (!api) return
    try {
      await api.createProject(name, context)
      const loaded = await api.listProjects()
      setProjects(loaded || [])
    } catch (err) {
      console.error('Failed to create project:', err)
    }
  }, [])

  const handleDeleteProject = useCallback(async (name) => {
    const api = window.jarvis
    if (!api) return
    if (!window.confirm(`Delete project "${name}" and all its chats?`)) return
    try {
      await api.deleteProject(name)
      setProjects(prev => prev.filter(p => p.name !== name))
      setProjectChats(prev => { const n = { ...prev }; delete n[name]; return n })
      if (activeProject?.name === name) {
        setActiveProject(null)
        setActiveChatId(null)
        setMessages([])
      }
    } catch (err) {
      console.error('Failed to delete project:', err)
    }
  }, [activeProject])

  const handleSendMessage = useCallback(async (text) => {
    if (!text.trim() || isStreaming) return
    const api = window.jarvis
    if (!api) return
    // Track for agent task labels
    lastUserMsgRef.current = text.trim()

    let chatId = activeChatIdRef.current
    if (!chatId) {
      chatId = generateId()
      setActiveChatId(chatId)
      localStorage.setItem('activeChatId', chatId)
    }

    // Inject project context + project files on first message
    let messageToSend = text.trim()
    const proj = activeProjectRef.current
    if (proj && isFirstMessageRef.current) {
      let contextBlock = ''
      if (proj.context) contextBlock += `[Project Context]\n${proj.context}\n\n`
      const files = projectFilesRef.current[proj.name] || []
      for (const filename of files) {
        try {
          const result = await window.jarvis.readProjectFile(proj.name, filename)
          const ext = filename.split('.').pop() || ''
          contextBlock += `[Project File: ${filename}]\n\`\`\`${ext}\n${result.contents}\n\`\`\`\n\n`
        } catch { }
      }
      if (contextBlock) messageToSend = `${contextBlock}[User]\n${text.trim()}`
      isFirstMessageRef.current = false
    } else {
      isFirstMessageRef.current = false
    }

    const userMsg = {
      id: `msg_${Date.now()}`,
      role: 'user',
      content: text.trim(), // display original text, not the injected version
      timestamp: Date.now(),
    }

    const typingBubble = {
      id: TYPING_ID,
      role: 'assistant',
      typing: true,
      timestamp: Date.now(),
    }
    setMessages(prev => [...prev, userMsg, typingBubble])
    setIsStreaming(true)
    setIsTyping(true)

    try {
      await api.sendMessage(messageToSend)
    } catch (err) {
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
      setIsTyping(false)
      setStatusText('')
    }
  }, [isStreaming])

  return (
    <div className="flex flex-col h-screen bg-[#FBF8F4] text-[#1A1A1A] overflow-hidden">
      <TopBar
        connections={connections}
        spawnerOpen={spawnerOpen}
        onToggleSpawner={() => setSpawnerOpen(o => !o)}
        activeAgents={Object.values(agents).filter(a => a.status === 'running').length}
        agentDone={agentDone}
      />
      <div className="flex flex-1 overflow-hidden">
        <div className="flex flex-col border-r border-[#EAE6DF] bg-[#FBF8F4]">
          <Sidebar
            chats={chats}
            activeChatId={activeChatId}
            agentStatuses={agentStatuses}
            connections={connections}
            onNewChat={handleNewChat}
            onSelectChat={handleSelectChat}
            onDeleteChat={handleDeleteChat}
            projects={projects}
            activeProject={activeProject?.name}
            onNewProjectChat={handleNewProjectChat}
            onCreateProject={handleCreateProject}
            onDeleteProject={handleDeleteProject}
            projectChats={projectChats}
            projectFiles={projectFiles}
            onAddProjectFile={handleAddProjectFile}
            onRemoveProjectFile={handleRemoveProjectFile}
            onExpandProject={handleSelectProjectChatAndLoadChats}
            onClearAllChats={handleClearAllChats}
          />
          <div style={{ padding: "4px 12px" }}>
            <div
              onClick={() => setShowGraph(!showGraph)}
              style={{
                cursor: "pointer", color: showGraph ? "#7C3AED" : "#6b7280",
                fontSize: 12, fontWeight: 500, padding: "6px 8px",
                borderRadius: 4, background: showGraph ? "#EDE9FE" : "transparent"
              }}
            >
              Graph {showGraph ? "(active)" : ""}
            </div>
          </div>
        </div>
        <main className="flex flex-col flex-1 overflow-hidden bg-[#FBF8F4]">
          {showGraph ? (
            <div className="flex-1 overflow-hidden">
              <KnowledgeGraph />
            </div>
          ) : (
            <>
              {/* Tab bar */}
              <div
                className="flex flex-shrink-0 border-b border-[#EAE6DF]"
                style={{ background: '#FBF8F4' }}
              >
                <button
                  onClick={() => setActiveTab('chat')}
                  className="px-5 py-2 text-xs font-medium transition-all"
                  style={{
                    borderBottom: activeTab === 'chat' ? '2px solid #7C3AED' : '2px solid transparent',
                    color: activeTab === 'chat' ? '#7C3AED' : '#9CA3AF',
                    background: 'transparent',
                  }}
                >
                  Chat
                </button>
                <button
                  onClick={() => setActiveTab('graph')}
                  className="px-5 py-2 text-xs font-medium transition-all"
                  style={{
                    borderBottom: activeTab === 'graph' ? '2px solid #7C3AED' : '2px solid transparent',
                    color: activeTab === 'graph' ? '#7C3AED' : '#9CA3AF',
                    background: 'transparent',
                  }}
                >
                  Graph
                </button>
              </div>

              {activeTab === 'chat' && (
                <>
                  {activeProject && (
                    <div className="flex-shrink-0 px-4 py-1.5 border-b border-[#EAE6DF] bg-[#F5F1EB]">
                      <span className="text-xs text-[#7C3AED] font-medium">
                        Project: {activeProject.name}
                      </span>
                    </div>
                  )}
                  <ChatArea
                    messages={messages}
                    statusText={statusText}
                    isTyping={isTyping}
                  />
                  <InputBar
                    onSend={handleSendMessage}
                    isStreaming={isStreaming}
                    connected={connections.jarvis}
                  />
                </>
              )}

              {activeTab === 'graph' && (
                <div className="flex-1 overflow-hidden">
                  <KnowledgeGraph />
                </div>
              )}
            </>
          )}
        </main>
        {spawnerOpen && (
          <AgentSpawner
            agents={agents}
            connected={connections.bus}
            onClose={() => setSpawnerOpen(false)}
            onSpawnAgent={async (task) => {
              lastUserMsgRef.current = task
              await handleSendMessage(task)
            }}
          />
        )}
      </div>
    </div>
  )
}
