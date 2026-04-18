import React, { useState, useEffect, useRef } from 'react'

// ── Helpers ─────────────────────────────────────────────────────────────────────

function elapsed(startTime) {
    if (!startTime) return '0s'
    const secs = Math.floor((Date.now() - startTime) / 1000)
    if (secs < 60) return `${secs}s`
    const mins = Math.floor(secs / 60)
    const rem = secs % 60
    if (mins < 60) return `${mins}m ${rem}s`
    return `${Math.floor(mins / 60)}h ${mins % 60}m`
}

function toolColor(action) {
    const map = {
        web_search: '#60A5FA',
        fetch_url: '#34D399',
        remember: '#A78BFA',
        recall: '#C084FC',
        write_file: '#F59E0B',
        read_file: '#6EE7B7',
        run_shell: '#FB923C',
        run_shell_safe: '#FB923C',
        spawn_subagent: '#F472B6',
        create_document: '#38BDF8',
        create_word_document: '#38BDF8',
        list_dir: '#94A3B8',
        FINAL_ANSWER: '#22C55E',
    }
    return map[action] || '#9CA3AF'
}

function statusBadge(status) {
    if (status === 'running') return { bg: '#7C3AED22', color: '#A78BFA', label: '● RUNNING' }
    if (status === 'done') return { bg: '#22C55E22', color: '#22C55E', label: '✓ DONE' }
    if (status === 'error') return { bg: '#EF444422', color: '#EF4444', label: '✗ ERROR' }
    return { bg: '#6B728022', color: '#6B7280', label: status?.toUpperCase() || 'IDLE' }
}

// ── Step Row ────────────────────────────────────────────────────────────────────

function StepRow({ step, isSelected, onSelect }) {
    const { action, observation } = step
    const color = toolColor(action)

    return (
        <button
            onClick={() => onSelect(step)}
            style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: 10,
                padding: '8px 16px',
                background: isSelected ? '#1A1F2E' : 'transparent',
                border: 'none',
                borderLeft: isSelected ? `2px solid ${color}` : '2px solid transparent',
                cursor: 'pointer',
                width: '100%',
                textAlign: 'left',
                transition: 'background 0.15s',
            }}
            onMouseEnter={e => { if (!isSelected) e.currentTarget.style.background = '#161B22' }}
            onMouseLeave={e => { if (!isSelected) e.currentTarget.style.background = 'transparent' }}
        >
            {/* Step number */}
            <span style={{
                fontFamily: '"JetBrains Mono", "Fira Code", monospace',
                fontSize: 10,
                color: '#6B7280',
                minWidth: 22,
                textAlign: 'right',
                paddingTop: 2,
                flexShrink: 0,
            }}>
                {step.step}
            </span>

            {/* Tool badge */}
            <span style={{
                fontFamily: '"JetBrains Mono", "Fira Code", monospace',
                fontSize: 11,
                fontWeight: 600,
                color,
                minWidth: 130,
                flexShrink: 0,
                paddingTop: 1,
            }}>
                {action}
            </span>

            {/* Observation preview */}
            <span style={{
                fontFamily: '"JetBrains Mono", "Fira Code", monospace',
                fontSize: 11,
                color: '#8B949E',
                lineHeight: 1.5,
                wordBreak: 'break-word',
                flex: 1,
            }}>
                {observation
                    ? `→ ${observation.slice(0, 120)}${observation.length > 120 ? '…' : ''}`
                    : '→ (executing…)'}
            </span>
        </button>
    )
}

// ── Agent Tree Node ─────────────────────────────────────────────────────────────

function AgentTreeNode({ agentId, info, isActive, onSelect, agents, depth = 0 }) {
    const [expanded, setExpanded] = useState(true)
    const badge = statusBadge(info.status)
    const childIds = Object.keys(agents).filter(id =>
        agents[id].parentId === agentId
    )
    const [tick, setTick] = useState(0)

    useEffect(() => {
        if (info.status !== 'running') return
        const t = setInterval(() => setTick(n => n + 1), 1000)
        return () => clearInterval(t)
    }, [info.status])

    return (
        <div>
            <button
                onClick={() => onSelect(agentId)}
                style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    width: '100%',
                    padding: '6px 12px',
                    paddingLeft: 12 + depth * 16,
                    background: isActive ? '#1A1F2E' : 'transparent',
                    border: 'none',
                    borderLeft: isActive ? '2px solid #A78BFA' : '2px solid transparent',
                    cursor: 'pointer',
                    textAlign: 'left',
                    transition: 'background 0.15s',
                }}
                onMouseEnter={e => { if (!isActive) e.currentTarget.style.background = '#161B22' }}
                onMouseLeave={e => { if (!isActive) e.currentTarget.style.background = 'transparent' }}
            >
                {/* Expand toggle */}
                {childIds.length > 0 && (
                    <span
                        onClick={e => { e.stopPropagation(); setExpanded(x => !x) }}
                        style={{ fontSize: 9, color: '#6B7280', cursor: 'pointer', width: 10 }}
                    >
                        {expanded ? '▼' : '▶'}
                    </span>
                )}

                {/* Status dot */}
                <span style={{
                    width: 6, height: 6, borderRadius: '50%',
                    background: badge.color, flexShrink: 0,
                    boxShadow: info.status === 'running' ? `0 0 6px ${badge.color}` : 'none',
                    animation: info.status === 'running' ? 'pulse 1.4s ease-in-out infinite' : 'none',
                }} />

                {/* Agent ID */}
                <span style={{
                    fontFamily: '"JetBrains Mono", monospace',
                    fontSize: 11, fontWeight: 600, color: '#E6EDF3',
                    flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                    {agentId}
                </span>

                {/* Timer */}
                <span style={{
                    fontFamily: '"JetBrains Mono", monospace',
                    fontSize: 10, color: '#6B7280',
                }}>
                    {elapsed(info.startTime)}
                </span>

                {/* Steps count */}
                <span style={{
                    fontSize: 9, color: badge.color, background: badge.bg,
                    padding: '1px 6px', borderRadius: 3, fontWeight: 600,
                }}>
                    {info.steps?.length || 0}
                </span>
            </button>

            {/* Task preview */}
            {info.task && (
                <div style={{
                    paddingLeft: 38 + depth * 16, paddingRight: 12, paddingBottom: 4,
                    fontSize: 10, color: '#6B7280', fontFamily: '"JetBrains Mono", monospace',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                    {info.task.slice(0, 80)}{info.task.length > 80 ? '…' : ''}
                </div>
            )}

            {/* Children */}
            {expanded && childIds.map(cid => (
                <AgentTreeNode
                    key={cid}
                    agentId={cid}
                    info={agents[cid]}
                    isActive={false}
                    onSelect={onSelect}
                    agents={agents}
                    depth={depth + 1}
                />
            ))}
        </div>
    )
}

// ── Step Detail Drawer ──────────────────────────────────────────────────────────

function StepDetail({ step, onClose }) {
    if (!step) return null
    const color = toolColor(step.action)

    return (
        <div style={{
            position: 'absolute', bottom: 0, left: 0, right: 0,
            maxHeight: '40%', background: '#161B22',
            borderTop: `1px solid ${color}33`,
            display: 'flex', flexDirection: 'column',
            zIndex: 10,
        }}>
            <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '8px 16px', borderBottom: '1px solid #21262D',
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{
                        fontFamily: '"JetBrains Mono", monospace', fontSize: 10,
                        color: '#6B7280',
                    }}>Step {step.step}</span>
                    <span style={{
                        fontFamily: '"JetBrains Mono", monospace', fontSize: 12,
                        fontWeight: 700, color,
                    }}>{step.action}</span>
                </div>
                <button
                    onClick={onClose}
                    style={{
                        background: 'none', border: 'none', color: '#6B7280',
                        cursor: 'pointer', fontSize: 14, padding: '2px 6px',
                    }}
                >✕</button>
            </div>
            <div style={{
                flex: 1, overflow: 'auto', padding: 16,
                fontFamily: '"JetBrains Mono", "Fira Code", monospace',
                fontSize: 11, color: '#C9D1D9', lineHeight: 1.6,
                whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            }}>
                {step.observation || '(no output)'}
            </div>
        </div>
    )
}

// ── Main Component ──────────────────────────────────────────────────────────────

export default function AgentMonitor({ agents = {} }) {
    const [selectedAgentId, setSelectedAgentId] = useState(null)
    const [selectedStep, setSelectedStep] = useState(null)
    const feedRef = useRef(null)

    const agentIds = Object.keys(agents)

    // Auto-select the first or most recent running agent
    useEffect(() => {
        if (agentIds.length > 0 && !selectedAgentId) {
            const running = agentIds.find(id => agents[id]?.status === 'running')
            setSelectedAgentId(running || agentIds[agentIds.length - 1])
        }
    }, [agentIds.length])

    // Auto-scroll feed
    useEffect(() => {
        if (feedRef.current) {
            feedRef.current.scrollTop = feedRef.current.scrollHeight
        }
    }, [agents, selectedAgentId])

    const selectedAgent = selectedAgentId ? agents[selectedAgentId] : null
    const steps = selectedAgent?.steps || []

    // Stats
    const totalSteps = steps.length
    const toolsUsed = [...new Set(steps.map(s => s.action))].length
    const runningCount = agentIds.filter(id => agents[id]?.status === 'running').length
    const doneCount = agentIds.filter(id => agents[id]?.status === 'done').length

    // Find root agents (no parentId)
    const rootIds = agentIds.filter(id => !agents[id]?.parentId)

    return (
        <div style={{
            display: 'flex', flex: 1, height: '100%',
            background: '#0D1117', color: '#C9D1D9',
            fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        }}>
            {/* Left: Agent Hierarchy Tree */}
            <div style={{
                width: 280, flexShrink: 0,
                borderRight: '1px solid #21262D',
                display: 'flex', flexDirection: 'column',
                background: '#0D1117',
            }}>
                {/* Tree header */}
                <div style={{
                    padding: '12px 14px', borderBottom: '1px solid #21262D',
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                }}>
                    <span style={{
                        fontSize: 10, fontWeight: 700, color: '#8B949E',
                        letterSpacing: '0.08em', textTransform: 'uppercase',
                    }}>
                        Agent Hierarchy
                    </span>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        {runningCount > 0 && (
                            <span style={{
                                fontSize: 9, color: '#A78BFA', background: '#7C3AED22',
                                padding: '2px 6px', borderRadius: 3, fontWeight: 600,
                            }}>
                                {runningCount} live
                            </span>
                        )}
                        {doneCount > 0 && (
                            <span style={{
                                fontSize: 9, color: '#22C55E', background: '#22C55E22',
                                padding: '2px 6px', borderRadius: 3, fontWeight: 600,
                            }}>
                                {doneCount} done
                            </span>
                        )}
                    </div>
                </div>

                {/* Tree body */}
                <div style={{ flex: 1, overflowY: 'auto', paddingTop: 4 }}>
                    {agentIds.length === 0 ? (
                        <div style={{
                            display: 'flex', flexDirection: 'column', alignItems: 'center',
                            justifyContent: 'center', height: '100%', gap: 12, padding: 32,
                        }}>
                            <div style={{
                                width: 48, height: 48, borderRadius: '50%',
                                background: '#161B22', display: 'flex',
                                alignItems: 'center', justifyContent: 'center',
                                border: '1px solid #21262D',
                            }}>
                                <span style={{ fontSize: 20 }}>⊘</span>
                            </div>
                            <span style={{ fontSize: 11, color: '#6B7280', textAlign: 'center' }}>
                                No agents active.<br />Send a task in Chat to spawn one.
                            </span>
                        </div>
                    ) : (
                        rootIds.map(id => (
                            <AgentTreeNode
                                key={id}
                                agentId={id}
                                info={agents[id]}
                                isActive={selectedAgentId === id}
                                onSelect={setSelectedAgentId}
                                agents={agents}
                            />
                        ))
                    )}
                </div>
            </div>

            {/* Right: Live Terminal Feed */}
            <div style={{
                flex: 1, display: 'flex', flexDirection: 'column',
                position: 'relative',
            }}>
                {/* Stats bar */}
                <div style={{
                    padding: '10px 16px',
                    borderBottom: '1px solid #21262D',
                    display: 'flex', alignItems: 'center', gap: 20,
                    background: '#0D1117',
                }}>
                    {selectedAgent ? (
                        <>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                <span style={{
                                    width: 6, height: 6, borderRadius: '50%',
                                    background: statusBadge(selectedAgent.status).color,
                                    boxShadow: selectedAgent.status === 'running'
                                        ? `0 0 8px ${statusBadge(selectedAgent.status).color}` : 'none',
                                }} />
                                <span style={{
                                    fontFamily: '"JetBrains Mono", monospace',
                                    fontSize: 11, fontWeight: 700, color: '#E6EDF3',
                                }}>
                                    {selectedAgentId}
                                </span>
                            </div>

                            <div style={{ display: 'flex', gap: 16, marginLeft: 'auto' }}>
                                <StatChip label="Steps" value={totalSteps} color="#A78BFA" />
                                <StatChip label="Tools" value={toolsUsed} color="#60A5FA" />
                                <StatChip label="Time" value={elapsed(selectedAgent.startTime)} color="#34D399" />
                            </div>
                        </>
                    ) : (
                        <span style={{ fontSize: 11, color: '#6B7280' }}>
                            Select an agent to view its live feed
                        </span>
                    )}
                </div>

                {/* Terminal feed */}
                <div
                    ref={feedRef}
                    style={{
                        flex: 1, overflowY: 'auto', overflowX: 'hidden',
                        background: '#0D1117',
                    }}
                >
                    {steps.length === 0 && selectedAgent && (
                        <div style={{
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            height: '100%', color: '#6B7280', fontSize: 12,
                        }}>
                            <div style={{ textAlign: 'center' }}>
                                <div style={{
                                    width: 40, height: 40, borderRadius: '50%',
                                    border: '2px solid #21262D', margin: '0 auto 12px',
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    animation: selectedAgent.status === 'running' ? 'spin 2s linear infinite' : 'none',
                                }}>
                                    <span style={{ fontSize: 16 }}>◎</span>
                                </div>
                                Waiting for first step…
                            </div>
                        </div>
                    )}

                    {steps.map((s, i) => (
                        <StepRow
                            key={i}
                            step={s}
                            isSelected={selectedStep?.step === s.step}
                            onSelect={setSelectedStep}
                        />
                    ))}
                </div>

                {/* Step detail drawer */}
                <StepDetail step={selectedStep} onClose={() => setSelectedStep(null)} />
            </div>

            {/* Keyframe animations */}
            <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
        </div>
    )
}

// ── Stat Chip ───────────────────────────────────────────────────────────────────

function StatChip({ label, value, color }) {
    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{
                fontSize: 9, color: '#6B7280', textTransform: 'uppercase',
                letterSpacing: '0.05em',
            }}>{label}</span>
            <span style={{
                fontFamily: '"JetBrains Mono", monospace',
                fontSize: 12, fontWeight: 700, color,
            }}>{value}</span>
        </div>
    )
}
