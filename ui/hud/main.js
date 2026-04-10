const { app, BrowserWindow, screen } = require('electron');
const path = require('path');

let win;

app.whenReady().then(() => {
  const { width } = screen.getPrimaryDisplay().workAreaSize;

  win = new BrowserWindow({
    width: 600,
    height: 80,
    x: Math.floor((width - 600) / 2),
    y: 0,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    focusable: false,
    hasShadow: false,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
  });

  win.setAlwaysOnTop(true, 'screen-saver');
  win.setVisibleOnAllWorkspaces(true);
  win.setIgnoreMouseEvents(true, { forward: true });
  win.loadFile(path.join(__dirname, 'index.html'));

  // Allow temporary mouse events when the window is interacted with
  win.webContents.on('did-finish-load', () => {
    win.webContents.executeJavaScript(`
      window.electronMain = {
        setIgnoreMouseEvents: (ignore) => {
          // Send message to main process
        }
      };
    `);
  });
});

app.on('window-all-closed', () => app.quit());
