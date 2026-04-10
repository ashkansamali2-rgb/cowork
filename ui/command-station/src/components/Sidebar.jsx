import React, { useState, useRef } from 'react'

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

function ChatItem({ chat, activeChatId, onSelectChat, onDeleteChat }) {
  const [hovered, setHovered] = useState(false)
  return (
    <div
      className="relative flex items-center group"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <button
        onClick={() => onSelectChat(chat)}
        className={`no-drag flex-1 text-left px-2 py-1.5 text-xs transition-colors ${
          chat.id === activeChatId
            ? 'chat-item-active'
            : 'text-[#1A1A1A] hover:bg-[#EDE9FE]'
        }`}
        style={{
          borderLeft: chat.id === activeChatId ? '2px solid #7C3AED' : '2px solid transparent',
        }}
      >
        <p className="truncate font-medium pr-4">{chat.title || 'Untitled Chat'}</p>
        {chat.updatedAt && (
          <p className="text-[10px] text-[#9CA3AF] mt-0.5">{formatTime(chat.updatedAt)}</p>
        )}
      </button>
      {hovered && onDeleteChat && (
        <button
          onClick={(e) => { e.stopPropagation(); onDeleteChat(chat) }}
          className="no-drag absolute right-1 top-1/2 -translate-y-1/2 w-4 h-4 flex items-center justify-center text-[#9CA3AF] hover:text-[#EF4444] transition-colors"
          title="Delete chat"
        >
          ×
        </button>
      )}
    </div>
  )
}

function NewProjectModal({ onClose, onCreate }) {
  const [name, setName] = useState('')
  const [context, setContext] = useState('')

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!name.trim()) return
    onCreate(name.trim(), context.trim())
    onClose()
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.4)' }}
      onClick={onClose}
    >
      <div
        className="bg-[#FBF8F4] border border-[#EAE6DF] p-5 w-80"
        style={{ borderRadius: 0 }}
        onClick={e => e.stopPropagation()}
      >
        <h3 className="text-sm font-bold text-[#1A1A1A] mb-4">New Project</h3>
        <form onSubmit={handleSubmit}>
          <label className="block text-xs text-[#6B7280] mb-1">Project Name</label>
          <input
            autoFocus
            value={name}
            onChange={e => setName(e.target.value)}
            className="w-full border border-[#EAE6DF] bg-white px-2 py-1.5 text-xs text-[#1A1A1A] mb-3 focus:outline-none focus:border-[#7C3AED]"
            style={{ borderRadius: 0 }}
            placeholder="my-project"
          />
          <label className="block text-xs text-[#6B7280] mb-1">Context (injected at start of chats)</label>
          <textarea
            value={context}
            onChange={e => setContext(e.target.value)}
            className="w-full border border-[#EAE6DF] bg-white px-2 py-1.5 text-xs text-[#1A1A1A] mb-4 focus:outline-none focus:border-[#7C3AED] resize-none"
            style={{ borderRadius: 0, height: 80 }}
            placeholder="This project is about..."
          />
          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-1.5 text-xs text-[#6B7280] border border-[#EAE6DF] hover:bg-[#F5F1EB]"
              style={{ borderRadius: 0 }}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-3 py-1.5 text-xs font-medium text-white bg-[#7C3AED] hover:bg-[#6D28D9]"
              style={{ borderRadius: 0 }}
            >
              Create
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function Sidebar({
  chats,
  activeChatId,
  agentStatuses,
  connections,
  onNewChat,
  onSelectChat,
  onDeleteChat,
  projects,
  activeProject,
  onNewProjectChat,
  onCreateProject,
  onDeleteProject,
  projectChats,
  projectFiles,
  onAddProjectFile,
  onRemoveProjectFile,
  onExpandProject,
  onClearAllChats,
}) {
  const [expandedProjects, setExpandedProjects] = useState({})
  const [showNewProject, setShowNewProject] = useState(false)
  const [contextMenuProject, setContextMenuProject] = useState(null)
  const [contextMenuPos, setContextMenuPos] = useState({ x: 0, y: 0 })
  const projectFileInputRef = useRef(null)
  const addFileForProject = useRef(null)

  const toggleProject = (name, project) => {
    const willExpand = !expandedProjects[name]
    setExpandedProjects(prev => ({ ...prev, [name]: !prev[name] }))
    if (willExpand && onExpandProject && project) onExpandProject(project)
  }

  const handleAddFileClick = (projectName) => {
    addFileForProject.current = projectName
    projectFileInputRef.current?.click()
  }

  const handleProjectFileChange = (e) => {
    const files = Array.from(e.target.files || [])
    e.target.value = ''
    const projName = addFileForProject.current
    if (!projName || !onAddProjectFile) return
    for (const file of files) {
      if (file.path) onAddProjectFile(projName, file.path)
    }
  }

  const handleProjectRightClick = (e, projectName) => {
    e.preventDefault()
    setContextMenuProject(projectName)
    setContextMenuPos({ x: e.clientX, y: e.clientY })
  }

  const handleDeleteProject = () => {
    if (contextMenuProject && onDeleteProject) {
      onDeleteProject(contextMenuProject)
    }
    setContextMenuProject(null)
  }

  const handleCreateProject = (name, context) => {
    if (onCreateProject) onCreateProject(name, context)
  }

  return (
    <aside
      className="flex flex-col flex-shrink-0 overflow-hidden border-r border-[#EAE6DF]"
      style={{ width: 200, background: '#F5F1EB' }}
      onClick={() => contextMenuProject && setContextMenuProject(null)}
    >
      {/* Traffic lights space (macOS frameless) */}
      <div className="h-10 flex-shrink-0 drag-region" />

      {/* Wordmark */}
      <div className="px-4 pb-3 flex-shrink-0">
        <span className="text-sm font-bold text-[#7C3AED] tracking-tight">Cowork</span>
      </div>

      {/* New Chat */}
      <div className="px-3 pb-2 flex-shrink-0">
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

        {/* PROJECTS section */}
        <div className="flex items-center justify-between mb-1 mt-1">
          <p className="text-[10px] font-semibold text-[#9CA3AF] uppercase tracking-wider px-1">
            Projects
          </p>
          <button
            onClick={() => setShowNewProject(true)}
            className="no-drag text-[10px] text-[#7C3AED] hover:text-[#6D28D9] px-1"
            title="New Project"
          >
            +
          </button>
        </div>

        {(!projects || projects.length === 0) ? (
          <p className="px-1 py-1 text-xs text-[#9CA3AF] mb-3">No projects yet</p>
        ) : (
          <div className="mb-4 space-y-px">
            {projects.map(project => (
              <div key={project.name}>
                {/* Project header */}
                <div
                  className="flex items-center gap-1 cursor-pointer select-none px-1 py-1 hover:bg-[#EDE9FE] group"
                  onClick={() => toggleProject(project.name, project)}
                  onContextMenu={(e) => handleProjectRightClick(e, project.name)}
                  style={{
                    borderLeft: activeProject === project.name ? '2px solid #7C3AED' : '2px solid transparent',
                  }}
                >
                  <span className="text-[9px] text-[#9CA3AF]">
                    {expandedProjects[project.name] ? '▼' : '▶'}
                  </span>
                  <span className="text-xs font-medium text-[#1A1A1A] truncate flex-1">
                    {project.name}
                  </span>
                </div>

                {/* Project chats + files (expanded) */}
                {expandedProjects[project.name] && (
                  <div className="pl-3">
                    <button
                      onClick={() => onNewProjectChat && onNewProjectChat(project)}
                      className="no-drag w-full text-left px-2 py-1 text-[10px] text-[#7C3AED] hover:bg-[#EDE9FE]"
                    >
                      + New Chat
                    </button>
                    {(projectChats && projectChats[project.name] || []).map(chat => (
                      <ChatItem
                        key={chat.id}
                        chat={chat}
                        activeChatId={activeChatId}
                        onSelectChat={onSelectChat}
                        onDeleteChat={onDeleteChat}
                      />
                    ))}

                    {/* Project Files */}
                    <div className="mt-1.5 mb-1">
                      <div className="flex items-center justify-between px-2 py-0.5">
                        <span className="text-[9px] font-semibold text-[#9CA3AF] uppercase tracking-wider">
                          Project Files
                        </span>
                        <button
                          onClick={() => handleAddFileClick(project.name)}
                          className="no-drag text-[10px] text-[#7C3AED] hover:text-[#6D28D9]"
                          title="Add file to project"
                        >
                          +
                        </button>
                      </div>
                      {(projectFiles && projectFiles[project.name] || []).length === 0 ? (
                        <p className="px-2 text-[10px] text-[#C4BFB8]">No files</p>
                      ) : (
                        (projectFiles[project.name] || []).map(filename => (
                          <div
                            key={filename}
                            className="flex items-center gap-1 px-2 py-0.5 text-[10px] text-[#6B7280] hover:bg-[#EDE9FE] group"
                          >
                            <span className="truncate flex-1">{filename}</span>
                            <button
                              onClick={() => onRemoveProjectFile && onRemoveProjectFile(project.name, filename)}
                              className="no-drag opacity-0 group-hover:opacity-100 text-[#9CA3AF] hover:text-[#EF4444] flex-shrink-0"
                              title="Remove file"
                            >
                              ×
                            </button>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* CHATS section */}
        <p className="text-[10px] font-semibold text-[#9CA3AF] uppercase tracking-wider px-1 mb-1">
          Chats
        </p>

        {chats.length === 0 ? (
          <p className="px-1 py-2 text-xs text-[#9CA3AF]">No chats yet</p>
        ) : (
          <div className="space-y-px mb-4">
            {chats.map(chat => (
              <ChatItem
                key={chat.id}
                chat={chat}
                activeChatId={activeChatId}
                onSelectChat={onSelectChat}
                onDeleteChat={onDeleteChat}
              />
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

      {/* Clear all chats */}
      {onClearAllChats && (
        <div className="flex-shrink-0 px-3 pb-2">
          <button
            onClick={onClearAllChats}
            className="no-drag w-full py-1 text-[10px] text-[#9CA3AF] hover:text-[#EF4444] border border-[#EAE6DF] hover:border-[#EF4444] transition-colors"
            style={{ borderRadius: 0 }}
          >
            Clear all chats
          </button>
        </div>
      )}

      {/* Connection status — bottom */}
      <div className="flex-shrink-0 border-t border-[#EAE6DF] px-4 py-2.5">
        <p
          className="text-[11px]"
          style={{ color: connections.jarvis ? '#9CA3AF' : '#EF4444' }}
        >
          {connections.jarvis ? '● Connected' : '○ Offline'}
        </p>
      </div>

      {/* Hidden file input for project files */}
      <input
        ref={projectFileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={handleProjectFileChange}
      />

      {/* New Project Modal */}
      {showNewProject && (
        <NewProjectModal
          onClose={() => setShowNewProject(false)}
          onCreate={handleCreateProject}
        />
      )}

      {/* Right-click context menu */}
      {contextMenuProject && (
        <div
          className="fixed z-50 bg-white border border-[#EAE6DF] shadow-sm py-1"
          style={{ top: contextMenuPos.y, left: contextMenuPos.x, minWidth: 140, borderRadius: 0 }}
          onClick={e => e.stopPropagation()}
        >
          <button
            onClick={handleDeleteProject}
            className="w-full text-left px-3 py-1.5 text-xs text-[#EF4444] hover:bg-[#FEF2F2]"
          >
            Delete Project
          </button>
        </div>
      )}
    </aside>
  )
}
