const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('jarvis', {
  sendMessage: (msg) => ipcRenderer.invoke('chat:send', msg),
  onStream: (cb) => ipcRenderer.on('chat:stream', (_, data) => cb(data)),
  onStatusMessage: (cb) => ipcRenderer.on('chat:status', (_, data) => cb(data)),
  onBusEvent: (cb) => ipcRenderer.on('bus:event', (_, data) => cb(data)),
  onConnectionStatus: (cb) => ipcRenderer.on('connection:status', (_, data) => cb(data)),
  loadChats: () => ipcRenderer.invoke('chat:load'),
  saveChat: (chat) => ipcRenderer.invoke('chat:save', chat),
  spawnAgent: (task) => ipcRenderer.invoke('agent:spawn', task),
  getConnectionStatus: () => ipcRenderer.invoke('connection:status'),
  minimize: () => ipcRenderer.invoke('window:minimize'),
  close: () => ipcRenderer.invoke('window:close'),
  removeAllListeners: (channel) => ipcRenderer.removeAllListeners(channel),
})
