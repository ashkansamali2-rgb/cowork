const { app, BrowserWindow, ipcMain, shell } = require('electron');
const path = require('path');
const { exec } = require('child_process');
const fs = require('fs');
const os = require('os');

function resolvePath(p) {
  return p.replace('~', os.homedir());
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1100,
    height: 700,
    minWidth: 900,
    minHeight: 600,
    frame: false,
    transparent: false,
    backgroundColor: '#050508',
    titleBarStyle: 'hiddenInset',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: false
    }
  });

  win.loadFile(path.join(__dirname, 'renderer', 'index.html'));
}

app.whenReady().then(() => {
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

ipcMain.handle('open-url', (_, url) => shell.openExternal(url));

ipcMain.handle('open-app', (_, appName) => {
  exec(`open -a "${appName}"`, err => { if (err) console.error(err); });
});

ipcMain.handle('open-folder', (_, folderPath) => {
  shell.openPath(resolvePath(folderPath));
});

ipcMain.handle('launch-terminal', (_, cmd) => {
  if (cmd) {
    exec(`osascript -e 'tell application "Terminal" to do script "${cmd}"' -e 'tell application "Terminal" to activate'`);
  } else {
    exec('open -a Terminal');
  }
});

ipcMain.handle('list-files', (_, folderPath) => {
  try {
    const resolved = resolvePath(folderPath);
    if (!fs.existsSync(resolved)) return [];
    return fs.readdirSync(resolved).filter(f => !f.startsWith('.'));
  } catch(e) { return []; }
});

ipcMain.handle('toggle-voice', () => {
  exec('pkill -USR1 -f voice_daemon');
});
