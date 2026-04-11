const { app, BrowserWindow, ipcMain, shell, Menu } = require('electron')
const path = require('path')
const fs = require('fs')
const os = require('os')
const WebSocket = require('ws')

const isDev = process.env.NODE_ENV !== 'production'
const CHATS_DIR = path.join(__dirname, 'chats')
const PROJECTS_DIR = path.join(os.homedir(), 'cowork', 'projects')
const JARVIS_WS_URL = 'ws://127.0.0.1:8001/ws'
const BUS_WS_URL = 'ws://127.0.0.1:8002'

let mainWindow = null
let jarvisWs = null
let busWs = null
let jarvisConnected = false
let busConnected = false

// Ensure chats and projects directories exist
if (!fs.existsSync(CHATS_DIR)) {
  fs.mkdirSync(CHATS_DIR, { recursive: true })
}
if (!fs.existsSync(PROJECTS_DIR)) {
  fs.mkdirSync(PROJECTS_DIR, { recursive: true })
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    frame: false,
    titleBarStyle: 'hidden',
    trafficLightPosition: { x: 16, y: 16 },
    backgroundColor: '#FBF8F4',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
    show: false,
  })

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173')
    // mainWindow.webContents.openDevTools()
  } else {
    mainWindow.loadFile(path.join(__dirname, 'dist', 'index.html'))
  }

  mainWindow.once('ready-to-show', () => {
    mainWindow.show()
    connectJarvis()
    connectBus()
  })

  mainWindow.on('closed', () => {
    mainWindow = null
    if (jarvisWs) jarvisWs.close()
    if (busWs) busWs.close()
  })
}

// ── Jarvis WebSocket ──────────────────────────────────────────────────────────
function connectJarvis() {
  if (jarvisWs && (jarvisWs.readyState === WebSocket.OPEN || jarvisWs.readyState === WebSocket.CONNECTING)) return

  try {
    jarvisWs = new WebSocket(JARVIS_WS_URL)

    jarvisWs.on('open', () => {
      jarvisConnected = true
      // Identify this connection so responses are isolated to this client
      jarvisWs.send(JSON.stringify({ register: 'desktop', client: 'command-station' }))
      sendToRenderer('connection:status', { service: 'jarvis', connected: true })
    })

    jarvisWs.on('message', (data) => {
      try {
        const msg = JSON.parse(data.toString())
        // Strip ANSI escape codes from the message text
        const raw = msg.msg || msg.content || ''
        const clean = raw.replace(/\x1b\[[0-9;]*m/g, '').trim()

        if (msg.type === 'final') {
          // Forward with type intact so App.jsx agent-done handler fires
          sendToRenderer('chat:stream', { type: 'final', msg: clean })
        } else if (msg.type === 'status') {
          sendToRenderer('chat:status', { text: clean })
        } else if (msg.type === 'ack') {
          sendToRenderer('chat:stream', { type: 'ack', msg: clean })
        } else if (msg.type === 'stream') {
          sendToRenderer('chat:stream', { content: clean, done: false })
        } else if (msg.type === 'agent_start' || msg.type === 'agent_update') {
          // Forward agent events to renderer for agent panel
          sendToRenderer('chat:stream', msg)
        }
      } catch {
        // Non-JSON: ignore
      }
    })

    jarvisWs.on('close', () => {
      jarvisConnected = false
      sendToRenderer('connection:status', { service: 'jarvis', connected: false })
      setTimeout(connectJarvis, 3000)
    })

    jarvisWs.on('error', (err) => {
      console.error('[Jarvis WS] error:', err.message)
      jarvisConnected = false
      sendToRenderer('connection:status', { service: 'jarvis', connected: false })
    })
  } catch (err) {
    console.error('[Jarvis WS] connect error:', err.message)
    setTimeout(connectJarvis, 3000)
  }
}

// ── Bus WebSocket ─────────────────────────────────────────────────────────────
function connectBus() {
  if (busWs && (busWs.readyState === WebSocket.OPEN || busWs.readyState === WebSocket.CONNECTING)) return

  try {
    busWs = new WebSocket(BUS_WS_URL)

    busWs.on('open', () => {
      busConnected = true
      sendToRenderer('connection:status', { service: 'bus', connected: true })
    })

    busWs.on('message', (data) => {
      try {
        const msg = JSON.parse(data.toString())
        sendToRenderer('bus:event', msg)
      } catch {
        sendToRenderer('bus:event', { raw: data.toString() })
      }
    })

    busWs.on('close', () => {
      busConnected = false
      sendToRenderer('connection:status', { service: 'bus', connected: false })
      setTimeout(connectBus, 3000)
    })

    busWs.on('error', (err) => {
      console.error('[Bus WS] error:', err.message)
      busConnected = false
      sendToRenderer('connection:status', { service: 'bus', connected: false })
    })
  } catch (err) {
    console.error('[Bus WS] connect error:', err.message)
    setTimeout(connectBus, 3000)
  }
}

function sendToRenderer(channel, data) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(channel, data)
  }
}

// ── IPC Handlers ──────────────────────────────────────────────────────────────
ipcMain.handle('chat:send', async (event, message) => {
  if (!jarvisWs || jarvisWs.readyState !== WebSocket.OPEN) {
    throw new Error('Jarvis not connected')
  }
  const payload = JSON.stringify({ message: message })
  jarvisWs.send(payload)
  return { ok: true }
})

ipcMain.handle('chat:save', async (event, chat) => {
  try {
    const filename = `${chat.id || Date.now()}.json`
    let dir = CHATS_DIR
    if (chat.projectName) {
      dir = path.join(PROJECTS_DIR, chat.projectName, 'chats')
      if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true })
    }
    const filepath = path.join(dir, filename)
    fs.writeFileSync(filepath, JSON.stringify(chat, null, 2), 'utf8')
    return { ok: true, filepath }
  } catch (err) {
    throw new Error(`Failed to save chat: ${err.message}`)
  }
})

ipcMain.handle('chat:load', async () => {
  try {
    if (!fs.existsSync(CHATS_DIR)) return []
    const files = fs.readdirSync(CHATS_DIR).filter(f => f.endsWith('.json'))
    const chats = files.map(file => {
      try {
        const filepath = path.join(CHATS_DIR, file)
        const raw = fs.readFileSync(filepath, 'utf8')
        return { ...JSON.parse(raw), _filePath: filepath }
      } catch {
        return null
      }
    }).filter(Boolean)
    chats.sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0))
    return chats
  } catch (err) {
    console.error('[chat:load]', err.message)
    return []
  }
})

ipcMain.handle('chat:clearAll', async () => {
  try {
    if (!fs.existsSync(CHATS_DIR)) return { ok: true }
    const files = fs.readdirSync(CHATS_DIR).filter(f => f.endsWith('.json'))
    for (const file of files) {
      fs.unlinkSync(path.join(CHATS_DIR, file))
    }
    return { ok: true, deleted: files.length }
  } catch (err) {
    throw new Error(`Failed to clear chats: ${err.message}`)
  }
})

ipcMain.handle('chat:delete', async (event, chatPath) => {
  try {
    // Security: only allow deleting files within CHATS_DIR or PROJECTS_DIR
    const resolved = path.resolve(chatPath)
    const inChats = resolved.startsWith(path.resolve(CHATS_DIR))
    const inProjects = resolved.startsWith(path.resolve(PROJECTS_DIR))
    if (!inChats && !inProjects) throw new Error('Path not allowed')
    if (fs.existsSync(resolved)) fs.unlinkSync(resolved)
    return { ok: true }
  } catch (err) {
    throw new Error(`Failed to delete chat: ${err.message}`)
  }
})

ipcMain.handle('projects:list', async () => {
  try {
    if (!fs.existsSync(PROJECTS_DIR)) return []
    const entries = fs.readdirSync(PROJECTS_DIR, { withFileTypes: true })
    return entries
      .filter(e => e.isDirectory())
      .map(e => {
        const contextPath = path.join(PROJECTS_DIR, e.name, 'context.md')
        let context = ''
        try { context = fs.readFileSync(contextPath, 'utf8') } catch {}
        return { name: e.name, context }
      })
  } catch (err) {
    console.error('[projects:list]', err.message)
    return []
  }
})

ipcMain.handle('projects:create', async (event, { name, context }) => {
  try {
    const projectDir = path.join(PROJECTS_DIR, name)
    const chatsDir = path.join(projectDir, 'chats')
    fs.mkdirSync(chatsDir, { recursive: true })
    fs.writeFileSync(path.join(projectDir, 'context.md'), context || '', 'utf8')
    return { ok: true }
  } catch (err) {
    throw new Error(`Failed to create project: ${err.message}`)
  }
})

ipcMain.handle('projects:delete', async (event, name) => {
  try {
    const projectDir = path.join(PROJECTS_DIR, name)
    const resolved = path.resolve(projectDir)
    if (!resolved.startsWith(path.resolve(PROJECTS_DIR))) throw new Error('Path not allowed')
    if (fs.existsSync(resolved)) fs.rmSync(resolved, { recursive: true, force: true })
    return { ok: true }
  } catch (err) {
    throw new Error(`Failed to delete project: ${err.message}`)
  }
})

ipcMain.handle('projects:listChats', async (event, projectName) => {
  try {
    const chatsDir = path.join(PROJECTS_DIR, projectName, 'chats')
    if (!fs.existsSync(chatsDir)) return []
    const files = fs.readdirSync(chatsDir).filter(f => f.endsWith('.json'))
    const chats = files.map(file => {
      try {
        const filepath = path.join(chatsDir, file)
        const raw = fs.readFileSync(filepath, 'utf8')
        return { ...JSON.parse(raw), _filePath: filepath }
      } catch {
        return null
      }
    }).filter(Boolean)
    chats.sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0))
    return chats
  } catch (err) {
    console.error('[projects:listChats]', err.message)
    return []
  }
})

ipcMain.handle('agent:spawn', async (event, task) => {
  if (!busWs || busWs.readyState !== WebSocket.OPEN) {
    throw new Error('Bus not connected')
  }
  const payload = JSON.stringify({
    type: 'spawn_agent',
    agent: 'cantivia',
    repo: task.repo,
    task: task.description,
    timestamp: Date.now(),
  })
  busWs.send(payload)
  return { ok: true }
})

ipcMain.handle('connection:status', async () => {
  return { jarvis: jarvisConnected, bus: busConnected }
})

ipcMain.handle('window:minimize', () => {
  if (mainWindow) mainWindow.minimize()
})

ipcMain.handle('window:close', () => {
  if (mainWindow) mainWindow.close()
})

ipcMain.handle('file:read', async (event, filePath) => {
  try {
    const resolved = path.resolve(filePath)
    const contents = fs.readFileSync(resolved, 'utf8')
    return { ok: true, contents }
  } catch (err) {
    throw new Error(`Failed to read file: ${err.message}`)
  }
})

ipcMain.handle('project:listFiles', async (event, projectName) => {
  try {
    const filesDir = path.join(PROJECTS_DIR, projectName, 'files')
    if (!fs.existsSync(filesDir)) return []
    return fs.readdirSync(filesDir).filter(f => !f.startsWith('.'))
  } catch (err) {
    console.error('[project:listFiles]', err.message)
    return []
  }
})

ipcMain.handle('project:addFile', async (event, { projectName, filePath }) => {
  try {
    const filesDir = path.join(PROJECTS_DIR, projectName, 'files')
    if (!fs.existsSync(filesDir)) fs.mkdirSync(filesDir, { recursive: true })
    const filename = path.basename(filePath)
    const dest = path.join(filesDir, filename)
    fs.copyFileSync(filePath, dest)
    return { ok: true, filename }
  } catch (err) {
    throw new Error(`Failed to add project file: ${err.message}`)
  }
})

ipcMain.handle('project:removeFile', async (event, { projectName, filename }) => {
  try {
    const filesDir = path.join(PROJECTS_DIR, projectName, 'files')
    const resolved = path.resolve(path.join(filesDir, filename))
    if (!resolved.startsWith(path.resolve(filesDir))) throw new Error('Path not allowed')
    if (fs.existsSync(resolved)) fs.unlinkSync(resolved)
    return { ok: true }
  } catch (err) {
    throw new Error(`Failed to remove project file: ${err.message}`)
  }
})

ipcMain.handle('project:readFile', async (event, { projectName, filename }) => {
  try {
    const filesDir = path.join(PROJECTS_DIR, projectName, 'files')
    const resolved = path.resolve(path.join(filesDir, filename))
    if (!resolved.startsWith(path.resolve(filesDir))) throw new Error('Path not allowed')
    const contents = fs.readFileSync(resolved, 'utf8')
    return { ok: true, contents }
  } catch (err) {
    throw new Error(`Failed to read project file: ${err.message}`)
  }
})

// ── App lifecycle ─────────────────────────────────────────────────────────────
app.whenReady().then(createWindow)

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow()
})
