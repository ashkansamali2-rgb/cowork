const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  openURL:       (url)    => ipcRenderer.invoke('open-url', url),
  openApp:       (app)    => ipcRenderer.invoke('open-app', app),
  openFolder:    (path)   => ipcRenderer.invoke('open-folder', path),
  launchTerminal:(cmd)    => ipcRenderer.invoke('launch-terminal', cmd),
  listFiles:     (path)   => ipcRenderer.invoke('list-files', path),
  toggleVoice:   ()       => ipcRenderer.invoke('toggle-voice'),
});
