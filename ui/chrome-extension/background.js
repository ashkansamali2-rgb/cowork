// background.js
let pendingCount = 0;
let offscreenCreated = false;

async function ensureOffscreen() {
  if (await chrome.offscreen.hasDocument()) return;
  await chrome.offscreen.createDocument({
    url: 'offscreen.html',
    reasons: ['WEBSOCKET'],
    justification: 'Maintain WebSocket connection to Jarvis'
  });
  offscreenCreated = true;
}

// Context menu
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: 'ask-jarvis',
    title: 'Ask Jarvis about this',
    contexts: ['selection']
  });
  ensureOffscreen();
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === 'ask-jarvis') {
    // forward to offscreen + open popup
    chrome.runtime.sendMessage({
      type: 'SEND_TO_JARVIS',
      content: `Regarding this selected text: "${info.selectionText}"`,
      context: { url: tab.url, title: tab.title, selection: info.selectionText }
    });
    pendingCount++;
    chrome.action.setBadgeText({ text: String(pendingCount) });
    chrome.action.setBadgeBackgroundColor({ color: '#7C3AED' });
  }
});

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'SEND_TO_JARVIS') {
    ensureOffscreen().then(() => {
      chrome.runtime.sendMessage({ ...msg, target: 'offscreen' });
    });
    pendingCount++;
    chrome.action.setBadgeText({ text: String(pendingCount) });
    chrome.action.setBadgeBackgroundColor({ color: '#7C3AED' });
    sendResponse({ ok: true });
  }

  if (msg.type === 'JARVIS_DONE') {
    pendingCount = Math.max(0, pendingCount - 1);
    chrome.action.setBadgeText({ text: pendingCount > 0 ? String(pendingCount) : '' });

    // Save to storage
    chrome.storage.local.get({ recentTasks: [] }, (data) => {
      const tasks = [{
        id: Date.now(),
        response: msg.full_response,
        timestamp: new Date().toISOString()
      }, ...data.recentTasks].slice(0, 5);
      chrome.storage.local.set({ recentTasks: tasks });
    });

    // Notification
    chrome.notifications.create({
      type: 'basic',
      iconUrl: 'icons/icon48.png',
      title: 'Jarvis',
      message: msg.full_response.slice(0, 100) + (msg.full_response.length > 100 ? '...' : '')
    });
  }

  if (msg.type === 'CONNECTION_STATUS' || msg.type === 'JARVIS_STREAM' || msg.type === 'JARVIS_DONE') {
    // Broadcast to all extension pages (popup)
    chrome.runtime.sendMessage(msg).catch(() => {});
  }

  if (msg.type === 'GET_STATUS') {
    sendResponse({ pendingCount });
  }

  return true;
});
