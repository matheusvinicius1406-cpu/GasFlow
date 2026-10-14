/**
 * Página de conexão servida em GET /connect.
 * Exibe o QR Code oficial do WhatsApp Web (gerado pelo web.whatsapp.com
 * por meio do whatsapp-web.js), com contagem regressiva, renovação
 * automática quando o WhatsApp rotaciona o código e status da sessão.
 */
export const CONNECT_PAGE_HTML = `<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Conectar WhatsApp</title>
<style>
  :root {
    --bg-dark: #0b141a;
    --panel: #111b21;
    --panel-2: #202c33;
    --green: #25d366;
    --green-dark: #00a884;
    --text: #e9edef;
    --text-dim: #8696a0;
    --danger: #f15c6d;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: "Segoe UI", Helvetica, Arial, sans-serif;
    background: var(--bg-dark);
    color: var(--text);
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
  }
  .card {
    background: var(--panel);
    border-radius: 12px;
    padding: 40px 48px;
    max-width: 460px;
    width: 100%;
    text-align: center;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.45);
  }
  h1 { font-size: 1.35rem; font-weight: 500; margin-bottom: 4px; }
  .subtitle { color: var(--text-dim); font-size: 0.9rem; margin-bottom: 28px; }
  .badge {
    display: inline-flex; align-items: center; gap: 7px;
    background: var(--panel-2); color: var(--text-dim);
    font-size: 0.78rem; letter-spacing: 0.4px; text-transform: uppercase;
    padding: 5px 12px; border-radius: 999px; margin-bottom: 24px;
  }
  .badge .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text-dim); }
  .badge[data-state="connected"] { color: var(--green); }
  .badge[data-state="connected"] .dot { background: var(--green); animation: pulse 1.6s infinite; }
  .badge[data-state="qr_pending"] { color: #f5c04e; }
  .badge[data-state="qr_pending"] .dot { background: #f5c04e; animation: pulse 1.2s infinite; }
  .badge[data-state="connecting"] .dot { animation: pulse 0.9s infinite; }
  @keyframes pulse { 50% { opacity: 0.35; } }

  .qr-wrap {
    position: relative;
    display: inline-block;
    padding: 14px;
    background: #fff;
    border-radius: 10px;
    line-height: 0;
  }
  .qr-wrap img { width: 264px; height: 264px; image-rendering: pixelated; }
  .qr-wrap.expired img { opacity: 0.15; filter: blur(2px); transition: opacity 0.3s; }
  .qr-overlay {
    position: absolute; inset: 0; display: none;
    flex-direction: column; align-items: center; justify-content: center; gap: 10px;
    color: #111b21; font-size: 0.95rem; font-weight: 600; line-height: 1.4;
  }
  .qr-wrap.expired .qr-overlay { display: flex; }
  .spinner {
    width: 34px; height: 34px; border-radius: 50%;
    border: 3px solid rgba(17, 27, 33, 0.15);
    border-top-color: var(--green-dark);
    animation: spin 0.9s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  .timer-bar {
    height: 4px; border-radius: 999px; background: var(--panel-2);
    margin: 20px auto 6px; max-width: 292px; overflow: hidden;
  }
  .timer-bar > div {
    height: 100%; width: 100%; border-radius: inherit;
    background: linear-gradient(90deg, var(--green-dark), var(--green));
    transition: width 1s linear;
  }
  .timer-label { color: var(--text-dim); font-size: 0.82rem; min-height: 1.2em; margin-bottom: 22px; }

  .steps { text-align: left; color: var(--text-dim); font-size: 0.88rem; line-height: 1.55; margin: 0 auto 26px; max-width: 320px; }
  .steps li { margin: 6px 0; list-style: none; display: flex; gap: 10px; }
  .steps .num {
    flex: 0 0 20px; height: 20px; margin-top: 2px;
    background: var(--panel-2); color: var(--green);
    border-radius: 50%; font-size: 0.72rem; font-weight: 700;
    display: inline-flex; align-items: center; justify-content: center;
  }

  button {
    cursor: pointer; border: none; border-radius: 8px;
    font-size: 0.95rem; font-weight: 600; padding: 12px 26px;
    transition: filter 0.15s, transform 0.05s;
  }
  button:hover { filter: brightness(1.08); }
  button:active { transform: scale(0.98); }
  .btn-primary { background: var(--green-dark); color: #fff; }
  .btn-danger { background: transparent; color: var(--danger); border: 1px solid var(--danger); }
  .actions { display: flex; gap: 12px; justify-content: center; }
  .hidden { display: none !important; }
  footer { margin-top: 26px; color: var(--text-dim); font-size: 0.75rem; }
</style>
</head>
<body>
  <main class="card">
    <h1>Marcos Gás — Conectar ao WhatsApp</h1>
    <p class="subtitle">Use o QR Code oficial do WhatsApp Web</p>

    <span class="badge" id="badge" data-state="connecting">
      <span class="dot"></span><span id="badge-text">Conectando…</span>
    </span>

    <div class="qr-wrap expired" id="qr-wrap">
      <img id="qr-img" alt="QR Code do WhatsApp Web" />
      <div class="qr-overlay" id="qr-overlay">
        <div class="spinner"></div>
        <div>Gerando novo QR Code…</div>
      </div>
    </div>

    <div class="timer-bar"><div id="timer-fill"></div></div>
    <p class="timer-label" id="timer-label"></p>

    <ol class="steps">
      <li><span class="num">1</span><span>Abra o WhatsApp no seu celular</span></li>
      <li><span class="num">2</span><span>Toque em <b>Configurações › Aparelhos conectados</b></span></li>
      <li><span class="num">3</span><span>Toque em <b>Conectar um aparelho</b> e aponte para este código</span></li>
    </ol>

    <div class="actions">
      <button class="btn-primary" id="btn-start">Gerar QR Code</button>
      <button class="btn-danger hidden" id="btn-logout">Desconectar</button>
    </div>

    <footer>Marcos Gás — Sessão salva localmente — não será necessário escanear novamente enquanto a sessão for válida.</footer>
  </main>

<script>
  const $ = (id) => document.getElementById(id);
  const badge = $('badge'), badgeText = $('badge-text');
  const qrWrap = $('qr-wrap'), qrImg = $('qr-img');
  const timerFill = $('timer-fill'), timerLabel = $('timer-label');
  const btnStart = $('btn-start'), btnLogout = $('btn-logout');

  const STATE_LABELS = {
    disconnected: 'Desconectado',
    connecting: 'Conectando…',
    qr_pending: 'Aguardando leitura do QR',
    connected: 'Conectado',
  };

  let countdownTimer = null;

  function setState(state) {
    badge.dataset.state = state;
    badgeText.textContent = STATE_LABELS[state] || state;
    btnStart.classList.toggle('hidden', state !== 'disconnected' && state !== 'qr_pending');
    btnLogout.classList.toggle('hidden', state !== 'connected');
    $('qr-wrap').classList.toggle('hidden', state === 'connected' || state === 'disconnected');
  }

  function startCountdown(expiresAtIso) {
    stopCountdown();
    const expiresAt = new Date(expiresAtIso).getTime();
    const total = Math.max(1, Math.round((expiresAt - Date.now()) / 1000) || 60);
    const tick = () => {
      const left = Math.max(0, Math.round((expiresAt - Date.now()) / 1000));
      if (left <= 0) {
        // Expirou: o WhatsApp Web já rotaciona o código sozinho,
        // então apenas esmaecemos até chegar o próximo QR.
        qrWrap.classList.add('expired');
        timerLabel.textContent = 'Renovando QR Code…';
        stopCountdown();
        return;
      }
      timerFill.style.width = (left / total) * 100 + '%';
      timerLabel.textContent = 'QR expira em ' + left + 's';
    };
    tick();
    countdownTimer = setInterval(tick, 1000);
  }

  function stopCountdown() {
    if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null; }
  }

  async function fetchQr() {
    try {
      const res = await fetch('/api/whatsapp/qr');
      if (!res.ok) return;
      const data = await res.json();
      if (qrImg.dataset.qr !== data.qr) {
        qrImg.src = data.dataUrl;
        qrImg.dataset.qr = data.qr;
        qrWrap.classList.remove('expired');
      }
      if (data.expiresIn > 0) startCountdown(data.expiresAt);
      else qrWrap.classList.add('expired');
    } catch { /* tenta de novo no próximo ciclo */ }
  }

  async function pollStatus() {
    let state = 'disconnected';
    try {
      const res = await fetch('/api/whatsapp/status');
      const data = await res.json();
      state = data.state;
      if (state === 'qr_pending') void fetchQr();
      else stopCountdown();
    } catch { /* servidor fora — mantém último estado */ }
    setState(state);
  }

  btnStart.addEventListener('click', async () => {
    await fetch('/api/whatsapp/start', { method: 'POST' });
    pollStatus();
  });

  btnLogout.addEventListener('click', async () => {
    await fetch('/api/whatsapp/logout', { method: 'POST' });
    qrImg.removeAttribute('src');
    delete qrImg.dataset.qr;
    pollStatus();
  });

  // Inicia a sessão automaticamente ao abrir a página (se ainda não houver).
  (async function boot() {
    await pollStatus();
    const res = await fetch('/api/whatsapp/status').then((r) => r.json()).catch(() => null);
    if (res && res.state === 'disconnected') {
      await fetch('/api/whatsapp/start', { method: 'POST' });
    }
  })();

  setInterval(pollStatus, 2000);
</script>
</body>
</html>`;
