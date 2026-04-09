// popup.js
let isStreaming = false;
let isRecording = false;
let recognition = null;

const commandInput  = document.getElementById('commandInput');
const sendBtn       = document.getElementById('sendBtn');
const voiceBtn      = document.getElementById('voiceBtn');
const pageContextBtn= document.getElementById('pageContextBtn');
const connStatus    = document.getElementById('connStatus');
const streamArea    = document.getElementById('streamArea');
const streamContent = document.getElementById('streamContent');
const tasksFeed     = document.getElementById('tasksFeed');
const themeToggle   = document.getElementById('themeToggle');
const themeIconDark = document.getElementById('themeIconDark');
const themeIconLight= document.getElementById('themeIconLight');
const htmlEl        = document.documentElement;

// ── Theme toggle ──────────────────────────────────────────────────────────────

function applyTheme(theme) {
  htmlEl.setAttribute('data-theme', theme);
  if (theme === 'light') {
    themeIconDark.style.display = 'none';
    themeIconLight.style.display = '';
  } else {
    themeIconDark.style.display = '';
    themeIconLight.style.display = 'none';
  }
  chrome.storage.local.set({ theme });
}

chrome.storage.local.get({ theme: 'dark', recentTasks: [] }, (data) => {
  applyTheme(data.theme || 'dark');
  renderTasks(data.recentTasks);
});

themeToggle.addEventListener('click', () => {
  const current = htmlEl.getAttribute('data-theme') || 'dark';
  applyTheme(current === 'dark' ? 'light' : 'dark');
});

// ── Connection status ─────────────────────────────────────────────────────────

function setConnected(connected) {
  connStatus.textContent = connected ? '● LIVE' : '○ OFF';
  connStatus.className = 'conn-status' + (connected ? ' live' : '');
}

// ── Runtime message listener ──────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === 'CONNECTION_STATUS') {
    setConnected(msg.connected);
  }
  if (msg.type === 'JARVIS_STREAM') {
    streamArea.style.display = 'block';
    streamContent.textContent += msg.content;
    streamContent.scrollTop = streamContent.scrollHeight;
    isStreaming = true;
  }
  if (msg.type === 'JARVIS_DONE') {
    isStreaming = false;
    streamArea.style.display = 'none';
    streamContent.textContent = '';
    chrome.storage.local.get({ recentTasks: [] }, (data) => {
      renderTasks(data.recentTasks);
    });
  }
});

// Ask background for current status
chrome.runtime.sendMessage({ type: 'GET_STATUS' }).then(resp => {
  if (resp) setConnected(resp.connected || false);
}).catch(() => {});

// ── Send message ──────────────────────────────────────────────────────────────

function sendMessage(content, context) {
  if (!content.trim()) return;
  chrome.runtime.sendMessage({ type: 'SEND_TO_JARVIS', content, context });
  commandInput.value = '';
  streamArea.style.display = 'block';
  streamContent.textContent = '';
}

sendBtn.addEventListener('click', () => {
  sendMessage(commandInput.value);
});

commandInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage(commandInput.value);
  }
});

// ── Page context ──────────────────────────────────────────────────────────────

pageContextBtn.addEventListener('click', () => {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs[0];
    chrome.scripting.executeScript(
      { target: { tabId: tab.id }, func: () => window.getSelection().toString() },
      (results) => {
        const selection = results?.[0]?.result || '';
        const context = { url: tab.url, title: tab.title, selection };
        const content = commandInput.value.trim() ||
          `Summarize this page: ${tab.title} (${tab.url})` +
          (selection ? `. Selected: "${selection}"` : '');
        sendMessage(content, context);
      }
    );
  });
});

// ── Voice input ───────────────────────────────────────────────────────────────

voiceBtn.addEventListener('click', () => {
  if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
    commandInput.placeholder = 'Speech recognition not available';
    return;
  }
  if (isRecording) {
    recognition?.stop();
    return;
  }
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SR();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = 'en-US';

  recognition.onstart = () => {
    isRecording = true;
    voiceBtn.classList.add('recording');
  };
  recognition.onresult = (e) => {
    const transcript = e.results[0][0].transcript;
    commandInput.value = transcript;
    sendMessage(transcript);
  };
  recognition.onend = () => {
    isRecording = false;
    voiceBtn.classList.remove('recording');
  };
  recognition.onerror = () => {
    isRecording = false;
    voiceBtn.classList.remove('recording');
  };
  recognition.start();
});

// ── Render tasks ──────────────────────────────────────────────────────────────

function renderTasks(tasks) {
  if (!tasks || !tasks.length) {
    tasksFeed.innerHTML = '<div class="empty-state">No recent activity</div>';
    return;
  }
  // Newest first
  const sorted = [...tasks].reverse();
  tasksFeed.innerHTML = sorted.map(task => `
    <div class="task-item">
      <div class="task-response">${escapeHtml(task.response || '')}</div>
      <div class="task-time">${formatTime(task.timestamp)}</div>
    </div>
  `).join('');
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatTime(iso) {
  const d = new Date(iso);
  const now = new Date();
  const diff = now - d;
  if (diff < 60000) return 'just now';
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}
