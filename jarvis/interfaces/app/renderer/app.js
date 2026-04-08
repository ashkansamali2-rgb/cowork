const wsUrl = 'ws://127.0.0.1:8001/ws';
let ws;

const chat = document.getElementById('chat');
const inp = document.getElementById('inp');
const go = document.getElementById('go');
const liveStatus = document.getElementById('live-status');
const liveLog = document.getElementById('live-log');
const wsDot = document.getElementById('ws-dot');

function connectWS() {
  ws = new WebSocket(wsUrl);
  
  ws.onopen = () => {
    wsDot.className = 'dot';
    liveStatus.textContent = 'Agentic engine connected.';
    liveStatus.style.color = '#58A6FF';
  };
  
  ws.onclose = () => {
    wsDot.className = 'dot off';
    liveStatus.textContent = 'Disconnected. Retrying...';
    liveStatus.style.color = '#FF5555';
    setTimeout(connectWS, 3000);
  };
  
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    if (data.type === 'ack') {
      liveStatus.textContent = data.msg;
    } 
    else if (data.type === 'status') {
      liveStatus.textContent = data.msg;
      liveStatus.style.color = '#E6EDF3';
    } 
    else if (data.type === 'log') {
      liveLog.textContent = '> ' + data.msg;
    } 
    else if (data.type === 'final') {
      addMsg('ai', data.msg);
      liveStatus.textContent = 'Task complete. Standing by.';
      liveStatus.style.color = '#00875A';
      liveLog.textContent = '';
      go.disabled = false;
    } 
    else if (data.type === 'error') {
      addMsg('ai error', data.msg);
      liveStatus.textContent = 'Error occurred.';
      liveStatus.style.color = '#FF5555';
      go.disabled = false;
    }
  };
}

function esc(t){ return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') }

function addMsg(role, text){
  const d = document.createElement('div');
  d.className = `msg ${role}`;
  d.innerHTML = esc(text);
  chat.appendChild(d);
  chat.scrollTop = chat.scrollHeight;
}

function send() {
  const msg = inp.value.trim();
  if(!msg || ws.readyState !== WebSocket.OPEN) return;
  
  inp.value = '';
  addMsg('you', msg);
  
  // Send the payload to the WebSocket server
  ws.send(JSON.stringify({ message: msg }));
  
  // Optional: keep button disabled during heavy tasks to prevent spamming
  // Remove this line if you want to test rapid multi-tasking!
  go.disabled = true; 
}

go.addEventListener('click', send);
inp.addEventListener('keydown', e => {
  if(e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
});

// Start connection
connectWS();

// Keep Ollama status polling (using the old endpoint for the green dot)
async function checkOllama(){
  try{
    const res = await fetch('http://localhost:11434/');
    document.getElementById('od').className = res.ok ? 'dot' : 'dot off';
  }catch(e){
    document.getElementById('od').className = 'dot off';
  }
}
setInterval(checkOllama, 5000);
checkOllama();
