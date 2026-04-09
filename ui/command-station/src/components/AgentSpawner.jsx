import React, { useState, useRef, useEffect } from 'react'

const PRESET_REPOS = [
  '~/cowork',
  '~/cowork/jarvis',
  '~/cowork/vision',
]

function ProgressLine({ entry }) {
  const isError = entry.text?.toLowerCase().includes('error') || entry.text?.toLowerCase().includes('failed')
  const isDone  = entry.text?.toLowerCase().includes('done')  || entry.text?.toLowerCase().includes('complete')
  return (
    <div className="flex items-start gap-2 py-1 text-xs" style={{ borderBottom: '1px solid #F4F3F0' }}>
      <span
        className="flex-shrink-0 w-4 font-mono"
        style={{ color: isError ? '#EF4444' : isDone ? '#22C55E' : '#7C3AED' }}
      >
        {isError ? 'x' : isDone ? 'v' : '-'}
      </span>
      <span
        className="flex-1 leading-relaxed font-mono"
        style={{ color: isError ? '#EF4444' : isDone ? '#1A1A1A' : '#6B7280' }}
      >
        {entry.text}
      </span>
      <span className="flex-shrink-0 text-[10px] text-[#6B7280]">
        {new Date(entry.timestamp).toLocaleTimeString(undefined, {
          hour: '2-digit', minute: '2-digit', second: '2-digit',
        })}
      </span>
    </div>
  )
}

export default function AgentSpawner({ taskProgress, connected, onClose }) {
  const [repo, setRepo]               = useState('~/cowork')
  const [customRepo, setCustomRepo]   = useState('')
  const [useCustom, setUseCustom]     = useState(false)
  const [description, setDescription] = useState('')
  const [spawning, setSpawning]       = useState(false)
  const [spawnError, setSpawnError]   = useState(null)
  const [spawnSuccess, setSpawnSuccess] = useState(false)
  const progressBottomRef = useRef(null)

  useEffect(() => {
    if (progressBottomRef.current) {
      progressBottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [taskProgress])

  const handleSpawn = async () => {
    const targetRepo = useCustom ? customRepo.trim() : repo
    if (!targetRepo || !description.trim()) return

    setSpawning(true)
    setSpawnError(null)
    setSpawnSuccess(false)

    try {
      const api = window.jarvis
      if (!api) throw new Error('Jarvis API not available')
      await api.spawnAgent({ repo: targetRepo, description: description.trim() })
      setSpawnSuccess(true)
      setDescription('')
      setTimeout(() => setSpawnSuccess(false), 3000)
    } catch (err) {
      setSpawnError(err.message)
    } finally {
      setSpawning(false)
    }
  }

  const inputStyle = {
    border: '1px solid #E5E4E0',
    background: '#FAFAF8',
    color: '#1A1A1A',
    fontSize: 13,
    padding: '6px 10px',
    outline: 'none',
    width: '100%',
    fontFamily: 'inherit',
    borderRadius: 0,
  }

  const inputFocusStyle = {
    borderColor: '#7C3AED',
  }

  return (
    <aside
      className="flex flex-col flex-shrink-0 overflow-hidden"
      style={{
        width: 280,
        background: '#FAFAF8',
        borderLeft: '1px solid #E5E4E0',
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 flex-shrink-0"
        style={{ height: 44, borderBottom: '1px solid #E5E4E0' }}
      >
        <span className="text-[10px] font-semibold text-[#6B7280] uppercase tracking-wider">
          Agents
        </span>
        <button
          onClick={onClose}
          className="text-[#6B7280] hover:text-[#1A1A1A] transition-colors text-xs"
        >
          Close
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">

        {/* Spawn form */}
        <div className="px-4 py-4" style={{ borderBottom: '1px solid #E5E4E0' }}>

          {/* Bus status */}
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-semibold text-[#1A1A1A]">Cantivia Task</span>
            <span
              className="text-[10px]"
              style={{ color: connected ? '#22C55E' : '#EF4444' }}
            >
              {connected ? 'Bus live' : 'Bus offline'}
            </span>
          </div>

          {/* Target repo */}
          <div className="mb-3">
            <label className="block text-[10px] font-semibold text-[#6B7280] uppercase tracking-wider mb-1">
              Target Repo
            </label>
            {!useCustom ? (
              <div className="flex gap-1">
                <select
                  value={repo}
                  onChange={e => setRepo(e.target.value)}
                  style={{ ...inputStyle, flex: 1 }}
                >
                  {PRESET_REPOS.map(r => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
                <button
                  onClick={() => setUseCustom(true)}
                  className="px-2 text-[10px] text-[#6B7280] hover:text-[#1A1A1A] transition-colors"
                  style={{ border: '1px solid #E5E4E0', background: '#FAFAF8', fontFamily: 'inherit' }}
                  title="Custom path"
                >
                  ...
                </button>
              </div>
            ) : (
              <div className="flex gap-1">
                <input
                  type="text"
                  value={customRepo}
                  onChange={e => setCustomRepo(e.target.value)}
                  placeholder="/path/to/repo"
                  style={{ ...inputStyle, flex: 1 }}
                  onFocus={e => Object.assign(e.target.style, inputFocusStyle)}
                  onBlur={e => (e.target.style.borderColor = '#E5E4E0')}
                />
                <button
                  onClick={() => setUseCustom(false)}
                  className="px-2 text-[10px] text-[#6B7280] hover:text-[#1A1A1A] transition-colors"
                  style={{ border: '1px solid #E5E4E0', background: '#FAFAF8', fontFamily: 'inherit' }}
                >
                  back
                </button>
              </div>
            )}
          </div>

          {/* Task description */}
          <div className="mb-4">
            <label className="block text-[10px] font-semibold text-[#6B7280] uppercase tracking-wider mb-1">
              Task Description
            </label>
            <textarea
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="Describe what Cantivia should do..."
              rows={4}
              style={{ ...inputStyle, overflow: 'auto', resize: 'vertical', minHeight: 80 }}
              onFocus={e => (e.target.style.borderColor = '#7C3AED')}
              onBlur={e => (e.target.style.borderColor = '#E5E4E0')}
            />
          </div>

          {/* Feedback */}
          {spawnError && (
            <p className="mb-3 text-xs text-red-600 py-2 px-3" style={{ background: '#FEF2F2', border: '1px solid #FECACA' }}>
              {spawnError}
            </p>
          )}
          {spawnSuccess && (
            <p className="mb-3 text-xs text-green-700 py-2 px-3" style={{ background: '#F0FDF4', border: '1px solid #BBF7D0' }}>
              Task spawned. Monitor progress below.
            </p>
          )}

          {/* Spawn button */}
          <button
            onClick={handleSpawn}
            disabled={spawning || !description.trim() || (!useCustom ? !repo : !customRepo.trim())}
            className="btn-purple w-full py-2 text-xs font-medium"
            style={{ borderRadius: 0 }}
          >
            {spawning ? 'Spawning...' : 'Spawn Cantivia Task'}
          </button>
        </div>

        {/* Progress log */}
        <div className="px-4 py-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-semibold text-[#6B7280] uppercase tracking-wider">
              Task Progress
            </span>
            {taskProgress.length > 0 && (
              <span className="text-[10px] text-[#6B7280]">{taskProgress.length} events</span>
            )}
          </div>

          {taskProgress.length === 0 ? (
            <p className="text-xs text-[#6B7280] py-4">No tasks running</p>
          ) : (
            <div
              className="max-h-64 overflow-y-auto"
              style={{ border: '1px solid #E5E4E0', background: '#F4F3F0', padding: '8px 10px' }}
            >
              {taskProgress.map(entry => (
                <ProgressLine key={entry.id} entry={entry} />
              ))}
              <div ref={progressBottomRef} />
            </div>
          )}
        </div>

      </div>
    </aside>
  )
}
