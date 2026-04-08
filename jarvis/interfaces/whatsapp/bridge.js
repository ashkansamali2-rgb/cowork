const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const fetch  = (...a) => import('node-fetch').then(({default:f})=>f(...a));
const API    = 'http://localhost:8000/chat';
let   active = 'general';
let   myNumber = null;
let   processing = false;

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: './session' }),
  puppeteer: { args: ['--no-sandbox','--disable-setuid-sandbox'] }
});

client.on('qr', qr => {
  console.log('\nScan this QR in WhatsApp → Settings → Linked Devices:');
  qrcode.generate(qr, { small: true });
});

client.on('ready', async () => {
  myNumber = client.info.wid._serialized;
  console.log('WhatsApp bridge connected! Your number:', myNumber);
});

client.on('message_create', async msg => {
  if (!msg.fromMe) return;
  if (processing) return; // ignore while we are replying
  const chat = await msg.getChat();
  if (!chat.isGroup && msg.to === myNumber) {
    processing = true;
    await handleMessage(msg);
    setTimeout(() => { processing = false; }, 3000);
  }
});

async function handleMessage(msg) {
  const t = msg.body.trim();
  if (!t) return;
  console.log('You:', t);
  if (t === '/coding')  { active='coding';  return msg.reply('Switched to Coding branch'); }
  if (t === '/cad')     { active='cad';     return msg.reply('Switched to CAD branch'); }
  if (t === '/general') { active='general'; return msg.reply('Switched to General branch'); }
  if (t === '/status')  { return msg.reply(`Branch: ${active}`); }
  try {
    const res = await fetch(API, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({message: t, branch: active})
    });
    const data = await res.json();
    const reply = (data.result||'No response').substring(0,4000);
    await msg.reply(reply);
    console.log('Jarvis:', reply.substring(0,100));
  } catch(e) {
    await msg.reply('Error: '+e.message);
  }
}

client.initialize();
