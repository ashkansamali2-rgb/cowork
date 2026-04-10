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
  const [agentSteps, setAgentSteps] = useState({}) // { agent_id: [{ step, action, observation }] }
  const [taskProgress, setTaskProgress] = useState([])
  const [spawnerOpen, setSpawnerOpen] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [statusText, setStatusText] = useState('')

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
      // Handle live agent step updates
      if (data.type === 'agent_update') {
        const { agent_id, step, action, observation } = data
        setAgentSteps(prev => ({
          ...prev,
          [agent_id]: [...(prev[agent_id] || []), { step, action, observation }],
        }))
        return
      }

      if (data.done) {
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
        setIsStreaming(true)
        setMessages(prev => {
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

    const handleStatus = (data) => {
      if (data.text) setStatusText(data.text)
    }

    const handleBusEvent = (event) => {
      if (event.type === 'agent_status') {
        setAgentStatuses(prev => ({ ...prev, [event.agent]: event.status }))
      } else if (event.type === 'AGENT_UPDATE' || event.type === 'agent_update') {
        const { agent_id, step, action, observation } = event
        setAgentSteps(prev => ({
          ...prev,
          [agent_id]: [...(prev[agent_id] || []), { step, action, observation }],
        }))
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
        <main className="flex flex-col flex-1 overflow-hidden bg-[#FBF8F4]">
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
            agentSteps={agentSteps}
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
