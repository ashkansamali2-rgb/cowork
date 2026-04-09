// content.js - injected into all pages
(function() {
  if (window.__jarvisContentLoaded) return;
  window.__jarvisContentLoaded = true;

  // Floating action button
  const fab = document.createElement('div');
  fab.id = 'jarvis-fab';
  fab.innerHTML = `
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
    </svg>
  `;
  document.body.appendChild(fab);

  // Quick command bar overlay
  const overlay = document.createElement('div');
  overlay.id = 'jarvis-overlay';
  overlay.innerHTML = `
    <div id="jarvis-bar">
      <div class="jarvis-logo">J</div>
      <input id="jarvis-input" type="text" placeholder="Ask Jarvis..." autocomplete="off" />
      <button id="jarvis-send">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>
        </svg>
      </button>
      <button id="jarvis-close">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>
    </div>
    <div id="jarvis-response" style="display:none"></div>
  `;
  document.body.appendChild(overlay);

  let overlayOpen = false;

  fab.addEventListener('click', () => {
    overlayOpen = !overlayOpen;
    overlay.style.display = overlayOpen ? 'flex' : 'none';
    if (overlayOpen) document.getElementById('jarvis-input').focus();
  });

  document.getElementById('jarvis-close').addEventListener('click', () => {
    overlay.style.display = 'none';
    overlayOpen = false;
  });

  document.getElementById('jarvis-send').addEventListener('click', sendToJarvis);
  document.getElementById('jarvis-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendToJarvis();
    if (e.key === 'Escape') { overlay.style.display = 'none'; overlayOpen = false; }
  });

  function sendToJarvis() {
    const input = document.getElementById('jarvis-input');
    const val = input.value.trim();
    if (!val) return;
    const responseDiv = document.getElementById('jarvis-response');
    responseDiv.style.display = 'block';
    responseDiv.textContent = '...';
    input.value = '';

    chrome.runtime.sendMessage({
      type: 'SEND_TO_JARVIS',
      content: val,
      context: { url: location.href, title: document.title, selection: window.getSelection().toString() }
    });
  }

  // Listen for stream responses
  chrome.runtime.onMessage.addListener((msg) => {
    if (!overlayOpen) return;
    const responseDiv = document.getElementById('jarvis-response');
    if (msg.type === 'JARVIS_STREAM') {
      if (responseDiv.textContent === '...') responseDiv.textContent = '';
      responseDiv.textContent += msg.content;
    }
    if (msg.type === 'JARVIS_DONE') {
      // Keep showing, don't clear
    }
  });

  // Keyboard shortcut: Ctrl+Shift+J to toggle
  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.shiftKey && e.key === 'J') {
      overlayOpen = !overlayOpen;
      overlay.style.display = overlayOpen ? 'flex' : 'none';
      if (overlayOpen) document.getElementById('jarvis-input').focus();
    }
  });
})();
