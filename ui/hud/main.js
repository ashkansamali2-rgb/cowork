const { app, BrowserWindow, screen } = require('electron');
const path = require('path');

let win;

app.whenReady().then(() => {
  const { width } = screen.getPrimaryDisplay().workAreaSize;

  win = new BrowserWindow({
    width: 600,
    height: 100,
    x: Math.floor((width - 600) / 2),
    y: 0,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    focusable: false,
    hasShadow: false,
    show: true,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
  });

  win.setAlwaysOnTop(true, 'screen-saver');
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  win.setIgnoreMouseEvents(true, { forward: true });
  win.loadFile(path.join(__dirname, 'index.html'));
});

app.on('window-all-closed', () => app.quit());
