"""Login, QR, and chat page HTML for the web chat channel."""

FONT_LINKS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,560;9..144,700&family=Sora:wght@400;500;600;700&display=swap" rel="stylesheet">
"""

FAVICON_LINKS = """
<link rel="icon" href="/chat/icon.svg" type="image/svg+xml" sizes="any">
<link rel="shortcut icon" href="/chat/icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/chat/apple-touch-icon.png" sizes="180x180">
<meta name="theme-color" content="#00684a">
"""

PWA_META = f"""
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="Orchestrator">
<meta name="format-detection" content="telephone=no">
<link rel="manifest" href="/chat/manifest.webmanifest">
{FAVICON_LINKS}
"""

STYLESHEET = '<link rel="stylesheet" href="/chat/app.css" nonce="__NONCE__">'

_ICON_BUBBLE = """<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M5 8.5c0-2 1.8-3.5 4-3.5h6c2.2 0 4 1.5 4 3.5v4c0 2-1.8 3.5-4 3.5h-2.2L9 19v-3H9c-2.2 0-4-1.5-4-3.5z"/><circle cx="10" cy="10.5" r="1" fill="currentColor" stroke="none"/><circle cx="14" cy="10.5" r="1" fill="currentColor" stroke="none"/></svg>"""

LOGIN_HTML = f"""<!doctype html><html lang="en" data-theme="light" class="h-full overflow-hidden"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,maximum-scale=1">
<title>Orchestrator login</title>
{PWA_META}
{FONT_LINKS}
{STYLESHEET}
</head>
<body class="app-bg grid h-dvh max-h-dvh place-items-center overflow-hidden px-3.5 pt-[max(10px,env(safe-area-inset-top))] pb-[max(10px,env(safe-area-inset-bottom))] font-sans text-ink antialiased [-webkit-tap-highlight-color:transparent]">
<button type="button" class="fixed top-[max(12px,env(safe-area-inset-top))] right-[max(12px,env(safe-area-inset-right))] z-20 inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-line bg-card py-1.5 pr-3 pl-2.5 text-[.78rem] font-semibold text-ink shadow-[0_6px_18px_rgba(18,32,28,.06)] transition hover:-translate-y-px hover:border-accent" id="themeBtn" aria-label="Toggle theme">
  <svg class="size-3.5 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
  <span id="themeLabel">Light</span>
</button>
<div class="no-scrollbar flex w-[min(440px,100%)] max-h-full animate-rise flex-col gap-[clamp(12px,2dvh,20px)] overflow-auto rounded-3xl border border-line bg-card p-[clamp(16px,2.4dvh,28px)] shadow-card h-short:gap-2.5 h-short:rounded-[18px] h-short:p-3.5">
  <div class="text-center">
    <div class="mx-auto mb-3 grid size-14 place-items-center rounded-2xl bg-linear-to-br from-accent to-[#149567] text-white shadow-[0_10px_24px_rgba(11,110,79,.28)] transition hover:scale-[1.04] h-short:mb-2 h-short:size-11 h-short:rounded-xl [&_svg]:size-7 h-short:[&_svg]:size-[22px]" aria-hidden="true">
      {_ICON_BUBBLE}
    </div>
    <h1 class="mb-2 font-display text-[clamp(1.55rem,3.5dvh,2.05rem)] leading-[1.1] tracking-[-.03em]">Cursor Orchestrator</h1>
    <p class="mx-auto max-w-[36ch] text-[clamp(.82rem,1.7dvh,.92rem)] leading-[1.45] text-muted h-tiny:line-clamp-2">Your private AI development assistant. Control your projects from this chat — securely, naturally, and with your approval.</p>
  </div>
  <div class="grid grid-cols-4 gap-2 rounded-[14px] bg-chip px-2 py-2.5 max-[420px]:grid-cols-2 max-[420px]:gap-1.5 h-tiny:hidden" aria-hidden="true">
    <div class="px-0.5 py-1 text-center">
      <svg class="mx-auto mb-1 size-[18px] text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M5 7h14v9H9l-4 3V7z"/><circle cx="9" cy="11.5" r=".9" fill="currentColor" stroke="none"/><circle cx="12" cy="11.5" r=".9" fill="currentColor" stroke="none"/><circle cx="15" cy="11.5" r=".9" fill="currentColor" stroke="none"/></svg>
      <strong class="mb-0.5 block text-[.68rem] font-bold tracking-[.01em]">Private chat</strong><span class="block text-[.62rem] leading-[1.25] text-muted h-short:hidden">Send requirements naturally</span>
    </div>
    <div class="px-0.5 py-1 text-center">
      <svg class="mx-auto mb-1 size-[18px] text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="m8 8-4 4 4 4M16 8l4 4-4 4M13 6l-2 12"/></svg>
      <strong class="mb-0.5 block text-[.68rem] font-bold tracking-[.01em]">AI Coding</strong><span class="block text-[.62rem] leading-[1.25] text-muted h-short:hidden">Cursor works on your code</span>
    </div>
    <div class="px-0.5 py-1 text-center">
      <svg class="mx-auto mb-1 size-[18px] text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M12 3 5 6v5c0 4.2 2.8 7.4 7 8.8 4.2-1.4 7-4.6 7-8.8V6l-7-3z"/><path d="m9.5 12 1.8 1.8L15 10"/></svg>
      <strong class="mb-0.5 block text-[.68rem] font-bold tracking-[.01em]">You Approve</strong><span class="block text-[.62rem] leading-[1.25] text-muted h-short:hidden">Review changes before release</span>
    </div>
    <div class="px-0.5 py-1 text-center">
      <svg class="mx-auto mb-1 size-[18px] text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M5 15c2-1 4-2 7-2s5 1 7 2"/><path d="M12 4v9"/><path d="m9 8 3-4 3 4"/></svg>
      <strong class="mb-0.5 block text-[.68rem] font-bold tracking-[.01em]">Deploy</strong><span class="block text-[.62rem] leading-[1.25] text-muted h-short:hidden">Push to GitHub or server</span>
    </div>
  </div>
  <form id="f" class="grid gap-2.5">
    <label class="text-[.86rem] font-bold text-ink" for="pw">Access Password</label>
    <div class="flex items-center gap-2 rounded-xl border border-line bg-surface py-0.5 pr-1.5 pl-3 transition focus-within:border-accent focus-within:shadow-[0_0_0_3px_rgba(11,110,79,.14)]">
      <span class="grid size-9 shrink-0 place-items-center text-muted" aria-hidden="true">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>
      </span>
      <input id="pw" class="min-w-0 flex-1 border-0 bg-transparent py-3 text-base text-ink outline-none placeholder:text-[#8a9a93]" type="password" placeholder="Enter your password" autocomplete="current-password" autofocus enterkeyhint="go">
      <button class="group grid size-9 shrink-0 cursor-pointer place-items-center rounded-lg border-0 bg-transparent p-0 text-muted hover:bg-accent-soft hover:text-accent" id="togglePw" type="button" aria-label="Show password" title="Show password">
        <svg class="group-[.on]:hidden" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>
        <svg class="hidden group-[.on]:block" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 3l18 18M10.6 10.6a2.5 2.5 0 0 0 3.5 3.5"/><path d="M7 7.4C4.4 9 2.8 11.2 2 12c1.2 1.7 4.7 7 10 7 1.7 0 3.2-.4 4.5-1"/></svg>
      </button>
    </div>
    <label class="flex items-center gap-2 text-[.82rem] text-ink select-none">
      <input class="size-4 accent-accent" type="checkbox" id="remember" checked>
      <span>Keep me signed in on this device</span>
      <span class="inline-grid size-4 cursor-help place-items-center rounded-full border border-line text-[10px] font-bold text-muted" title="Stores a secure session cookie on this device only.">i</span>
    </label>
    <button id="btn" class="group inline-flex min-h-12 w-full cursor-pointer items-center justify-center gap-2 rounded-xl border-0 bg-accent text-[15px] font-bold text-accent-ink shadow-[0_10px_22px_rgba(11,110,79,.22)] transition hover:-translate-y-px hover:brightness-105 hover:shadow-[0_12px_26px_rgba(11,110,79,.28)] active:translate-y-px disabled:translate-y-0 disabled:cursor-wait disabled:opacity-55" type="submit">
      <span class="hidden size-[15px] animate-spin rounded-full border-2 border-white/35 border-t-white group-[.loading]:inline-block" aria-hidden="true"></span>
      <span>Log in</span>
      <svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h12"/><path d="m13 6 6 6-6 6"/></svg>
    </button>
    <p id="err" class="m-0 max-h-0 overflow-hidden text-[.85rem] text-danger opacity-0 transition-[opacity,max-height] duration-200 [&.show]:max-h-12 [&.show]:opacity-100" role="alert" aria-live="polite"></p>
  </form>
  <a class="flex w-full cursor-pointer items-center gap-3 rounded-[14px] border border-line bg-chip p-3 text-left text-inherit no-underline transition hover:-translate-y-px hover:border-accent/30 standalone:hidden!" id="installTip" href="/chat/qr">
    <span class="grid size-9 shrink-0 place-items-center rounded-full bg-accent-soft text-accent" aria-hidden="true">
      <svg class="size-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="8" y="3" width="8" height="18" rx="2"/><path d="M11 18h2"/></svg>
    </span>
    <span class="min-w-0 flex-1">
      <strong class="mb-0.5 block text-[.84rem]">Add to iPhone Home Screen</strong>
      <span class="block text-[.72rem] leading-[1.35] text-muted">For quick access, add this app to your iPhone home screen.</span>
    </span>
    <span class="shrink-0 text-[1.1rem] text-muted" aria-hidden="true">›</span>
  </a>
</div>
<script nonce="__NONCE__">
const root = document.documentElement;
const themeBtn = document.getElementById('themeBtn');
const themeLabel = document.getElementById('themeLabel');
function applyTheme(t) {{
  root.setAttribute('data-theme', t);
  themeLabel.textContent = t === 'dark' ? 'Dark' : 'Light';
  try {{ localStorage.setItem('orch-theme', t); }} catch (e) {{}}
}}
applyTheme((() => {{
  try {{ return localStorage.getItem('orch-theme') || 'light'; }} catch (e) {{ return 'light'; }}
}})());
themeBtn.addEventListener('click', () => {{
  applyTheme(root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
}});
const tip = document.getElementById('installTip');
const isStandalone = window.navigator.standalone || matchMedia('(display-mode: standalone)').matches;
const isLocal = ['127.0.0.1', 'localhost'].includes(location.hostname);
if (isStandalone) tip.style.display = 'none';
else if (!isLocal) {{
  tip.removeAttribute('href');
  tip.addEventListener('click', (e) => {{
    e.preventDefault();
    alert('On iPhone Safari: Share → Add to Home Screen.');
  }});
}}
const pw = document.getElementById('pw');
const togglePw = document.getElementById('togglePw');
togglePw.addEventListener('click', () => {{
  const show = pw.type === 'password';
  pw.type = show ? 'text' : 'password';
  togglePw.classList.toggle('on', show);
  togglePw.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
  togglePw.title = show ? 'Hide password' : 'Show password';
  pw.focus();
}});
document.getElementById('f').addEventListener('submit', async (e) => {{
  e.preventDefault();
  const err = document.getElementById('err');
  const btn = document.getElementById('btn');
  err.textContent = '';
  err.classList.remove('show');
  btn.disabled = true;
  btn.classList.add('loading');
  try {{
    const r = await fetch('/chat/login', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{
        password: pw.value,
        remember: document.getElementById('remember').checked
      }})
    }});
    if (r.ok) {{ location.reload(); return; }}
    const j = await r.json().catch(() => ({{}}));
    err.textContent = j.error || ('Login failed: ' + r.status);
    err.classList.add('show');
    pw.focus();
    pw.select();
  }} finally {{
    btn.disabled = false;
    btn.classList.remove('loading');
  }}
}});
if ('serviceWorker' in navigator) {{
  navigator.serviceWorker.register('/chat/sw.js', {{scope: '/chat/'}}).catch(() => {{}});
}}
</script></body></html>"""

QR_PLACEHOLDER = (
    '<div class="grid size-full place-items-center overflow-hidden rounded-xl border border-dashed '
    'border-line bg-[#f7faf8] px-3 text-center">'
    '<div class="max-w-[12rem]">'
    '<div class="mx-auto mb-2 grid size-10 place-items-center rounded-xl bg-accent-soft '
    'text-accent [&_svg]:size-5" aria-hidden="true">'
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">'
    '<path d="M4 8V5h3M16 5h3v3M20 16v3h-3M8 20H5v-3"/>'
    '<rect x="8" y="8" width="8" height="8" rx="1"/></svg></div>'
    '<strong class="mb-0.5 block text-[.8rem] text-ink">Waiting for tunnel</strong>'
    '<p class="m-0 text-[.68rem] leading-[1.3] text-muted">'
    "QR shows when Cloudflare is connected.</p></div></div>"
)

QR_HTML = f"""<!doctype html><html lang="en" class="h-full"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Connect on iPhone</title>
{FAVICON_LINKS}
{FONT_LINKS}
{STYLESHEET}
</head>
<body class="app-bg h-dvh max-h-dvh overflow-x-hidden overflow-y-auto px-3 pt-[max(8px,env(safe-area-inset-top,0px))] pb-[max(12px,env(safe-area-inset-bottom,0px))] font-sans text-ink antialiased [-webkit-tap-highlight-color:transparent]">
<div class="mx-auto flex min-h-full w-full max-w-[520px] animate-rise flex-col gap-2.5 py-1.5 h-qr:gap-2 h-qr-tiny:gap-1.5">
  <a class="inline-flex shrink-0 items-center gap-1.5 self-start py-0.5 text-[.82rem] font-semibold text-muted no-underline transition hover:text-accent [&_svg]:size-4" href="/chat">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M15 6 9 12l6 6"/></svg>
    Back to login
  </a>
  <div class="shrink-0 text-center">
    <div class="mx-auto mb-1.5 grid size-10 place-items-center rounded-[12px] bg-accent-soft text-accent h-qr:mb-1 h-qr:size-9 h-qr-tiny:size-8 [&_svg]:size-5 h-qr:[&_svg]:size-4" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="8" y="3" width="8" height="18" rx="2"/><path d="M11 18h2"/></svg>
    </div>
    <h1 class="mb-0.5 font-display text-[1.35rem] leading-tight tracking-[-.02em] h-qr:text-[1.2rem] h-qr-tiny:text-[1.1rem]">Connect on iPhone</h1>
    <p class="mx-auto max-w-[40ch] text-[.82rem] leading-[1.35] text-muted h-qr:text-[.76rem] h-qr-tiny:line-clamp-2">Scan with your iPhone Camera, open the chat, then add it to Home Screen.</p>
  </div>
  <div class="hidden shrink-0 rounded-xl border border-[rgba(180,35,24,.22)] bg-[rgba(180,35,24,.06)] px-3 py-2 text-[.78rem] leading-[1.35] text-danger [&.show]:block" id="err" role="status" aria-live="polite" data-has="__HAS_ERROR__">__ERROR__</div>
  <div class="grid shrink-0 justify-items-center gap-2.5 rounded-[18px] border border-line bg-card p-3.5 shadow-[0_14px_40px_rgba(18,32,28,.07)] h-qr:gap-2 h-qr:rounded-[16px] h-qr:p-3 h-qr-tiny:gap-1.5 h-qr-tiny:p-2.5" id="qrCard" data-ready="__READY__">
    <div class="relative aspect-square w-[min(200px,58vw,34dvh)] overflow-hidden rounded-xl h-qr:w-[min(168px,48vw,28dvh)] h-qr-tiny:w-[min(140px,42vw,24dvh)]">
      <div class="grid size-full place-items-center overflow-hidden [&_img]:block [&_img]:h-auto [&_img]:w-full [&_img]:rounded-lg" id="qr">__QR_IMG__</div>
      <div class="pointer-events-none absolute top-1/2 left-1/2 grid size-8 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-[10px] border-[3px] border-white bg-accent text-white shadow-[0_6px_16px_rgba(11,110,79,.3)] h-qr:size-7 [&_svg]:size-4 h-qr:[&_svg]:size-3.5 __BADGE_CLASS__" id="qrBadge" aria-hidden="true">
        {_ICON_BUBBLE}
      </div>
    </div>
    <p class="m-0 w-full text-center text-[.76rem] leading-[1.3] text-muted [&.ready]:hidden" id="waitHint">Cloudflare tunnel is reconnecting. This page updates automatically.</p>
    <div class="flex w-full shrink-0 items-center gap-2 rounded-xl border border-line bg-[#f3f6f4] py-0.5 pr-1 pl-3">
      <input id="url" class="min-w-0 flex-1 border-0 bg-transparent py-2 text-[.76rem] text-ink outline-none placeholder:text-[#8a9a93] h-qr:py-1.5" type="text" readonly value="__CHAT_URL__" placeholder="Tunnel URL appears when Cloudflare is connected" aria-label="Chat URL">
      <button class="grid size-9 shrink-0 cursor-pointer place-items-center rounded-[10px] border-0 bg-transparent text-muted transition hover:bg-accent-soft hover:text-accent disabled:cursor-not-allowed disabled:opacity-40" type="button" id="copyIcon" title="Copy link" aria-label="Copy link" __COPY_DISABLED__>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M4 16V6a2 2 0 0 1 2-2h10"/></svg>
      </button>
    </div>
    <div class="grid w-full shrink-0 grid-cols-1 gap-2 min-[420px]:grid-cols-2">
      <a id="openLink" class="inline-flex min-h-10 w-full cursor-pointer items-center justify-center gap-1.5 rounded-xl bg-accent px-3 text-[.84rem] font-semibold text-accent-ink no-underline shadow-[0_8px_18px_rgba(11,110,79,.2)] transition hover:brightness-105 aria-disabled:pointer-events-none aria-disabled:cursor-not-allowed aria-disabled:opacity-45 h-qr:min-h-9 [&_svg]:size-3.5" href="__OPEN_HREF__" target="_blank" rel="noopener" aria-disabled="__OPEN_DISABLED__">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14 5h5v5"/><path d="M10 14 19 5"/><path d="M19 13v5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/></svg>
        Open on this PC
      </a>
      <button type="button" id="copyBtn" class="inline-flex min-h-10 w-full cursor-pointer items-center justify-center gap-1.5 rounded-xl border border-line bg-white px-3 text-[.84rem] font-semibold text-ink transition hover:border-accent/30 hover:bg-accent-soft hover:text-accent disabled:cursor-not-allowed disabled:opacity-45 h-qr:min-h-9 [&_svg]:size-3.5" __COPY_DISABLED__>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M4 16V6a2 2 0 0 1 2-2h10"/></svg>
        Copy link
      </button>
    </div>
  </div>
  <div class="shrink-0" id="stepsBlock">
    <div class="mb-1 text-[.8rem] font-bold h-qr:mb-0.5">Step by step</div>
    <div class="grid grid-cols-1 gap-1.5 min-[480px]:grid-cols-3">
      <div class="grid gap-0.5 rounded-[12px] border border-line bg-card p-2 h-qr:p-1.5">
        <div class="flex items-center justify-between"><span class="grid size-5 place-items-center rounded-full bg-accent-soft text-[.68rem] font-bold text-accent">1</span>
          <svg class="size-3.5 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M8 8h8v8H8z"/><circle cx="12" cy="12" r="2.2"/><path d="M9 4h6M9 20h6"/></svg>
        </div>
        <strong class="block text-[.76rem] leading-tight">Open Camera</strong>
        <p class="m-0 text-[.66rem] leading-[1.3] text-muted">iPhone Camera app</p>
      </div>
      <div class="grid gap-0.5 rounded-[12px] border border-line bg-card p-2 h-qr:p-1.5">
        <div class="flex items-center justify-between"><span class="grid size-5 place-items-center rounded-full bg-accent-soft text-[.68rem] font-bold text-accent">2</span>
          <svg class="size-3.5 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M4 8V5h3M16 5h3v3M20 16v3h-3M8 20H5v-3"/><rect x="8" y="8" width="8" height="8" rx="1"/></svg>
        </div>
        <strong class="block text-[.76rem] leading-tight">Scan QR</strong>
        <p class="m-0 text-[.66rem] leading-[1.3] text-muted">Point at the code</p>
      </div>
      <div class="grid gap-0.5 rounded-[12px] border border-line bg-card p-2 h-qr:p-1.5">
        <div class="flex items-center justify-between"><span class="grid size-5 place-items-center rounded-full bg-accent-soft text-[.68rem] font-bold text-accent">3</span>
          <svg class="size-3.5 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M12 14V4"/><path d="m8 8 4-4 4 4"/><path d="M5 14v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4"/></svg>
        </div>
        <strong class="block text-[.76rem] leading-tight">Home Screen</strong>
        <p class="m-0 text-[.66rem] leading-[1.3] text-muted">Share → Add</p>
      </div>
    </div>
  </div>
  <p class="m-0 shrink-0 pb-1 text-center text-[.7rem] leading-[1.35] text-muted" id="meta">__META__</p>
</div>
<template id="qrPlaceholder">{QR_PLACEHOLDER}</template>
<script nonce="__NONCE__">
const err = document.getElementById('err');
const qrEl = document.getElementById('qr');
const qrCard = document.getElementById('qrCard');
const waitHint = document.getElementById('waitHint');
const urlEl = document.getElementById('url');
const openLink = document.getElementById('openLink');
const copyBtn = document.getElementById('copyBtn');
const copyIcon = document.getElementById('copyIcon');
const qrBadge = document.getElementById('qrBadge');
const placeholder = document.getElementById('qrPlaceholder').innerHTML;
if (err.dataset.has === '1' && err.textContent.trim()) err.classList.add('show');
function setReady(ready, url, img) {{
  urlEl.value = url || '';
  qrEl.innerHTML = ready && img ? img : placeholder;
  qrBadge.classList.toggle('hidden', !ready);
  qrCard.dataset.ready = ready ? '1' : '0';
  waitHint.classList.toggle('ready', !!ready);
  openLink.href = url || '#';
  openLink.setAttribute('aria-disabled', ready ? 'false' : 'true');
  copyBtn.disabled = !ready;
  copyIcon.disabled = !ready;
}}
async function copyLink() {{
  const text = urlEl.value.trim();
  if (!text) {{
    document.getElementById('meta').textContent = 'No tunnel URL yet';
    return;
  }}
  try {{
    await navigator.clipboard.writeText(text);
    document.getElementById('meta').textContent = 'Link copied';
  }} catch (e) {{
    document.getElementById('meta').textContent = 'Copy failed — select the URL manually';
  }}
}}
copyBtn.addEventListener('click', copyLink);
copyIcon.addEventListener('click', copyLink);
async function refresh() {{
  try {{
    const r = await fetch('/chat/qr.json', {{cache: 'no-store'}});
    const j = await r.json();
    if (!j.ok) {{
      err.textContent = j.error || 'Tunnel unavailable';
      err.classList.add('show');
      setReady(false);
      document.getElementById('meta').textContent = 'Waiting for Cloudflare tunnel…';
      return;
    }}
    err.classList.remove('show');
    setReady(true, j.url, j.img);
    document.getElementById('meta').textContent = 'Updated ' + new Date().toLocaleTimeString();
  }} catch (e) {{
    err.textContent = 'Could not refresh QR — is the orchestrator running?';
    err.classList.add('show');
    setReady(false);
  }}
}}
if (qrCard.dataset.ready !== '1') setReady(false);
else {{
  waitHint.classList.add('ready');
  qrBadge.classList.remove('hidden');
}}
setInterval(refresh, 5000);
</script></body></html>"""

_CHAT_HEAD = f"""<!doctype html><html lang="en" class="h-full overflow-hidden"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,maximum-scale=1,interactive-widget=resizes-content">
<title>Orchestrator</title>
{PWA_META}
{FONT_LINKS}
{STYLESHEET}
</head>"""

CHAT_HTML = _CHAT_HEAD + r"""
<body class="chat-shell flex font-sans text-ink antialiased [-webkit-tap-highlight-color:transparent]">
<div id="sidebarBackdrop" class="fixed inset-0 z-40 hidden bg-ink/30 backdrop-blur-[2px] [&.show]:block min-[900px]:[&.show]:hidden!" aria-hidden="true"></div>
<aside id="sidebar" class="fixed inset-y-0 left-0 z-50 flex w-[min(288px,86vw)] shrink-0 -translate-x-full flex-col border-r border-line bg-sidebar pt-[max(10px,env(safe-area-inset-top,0px))] pb-[max(10px,env(safe-area-inset-bottom,0px))] transition-[transform,opacity] duration-200 ease-out [&.open]:translate-x-0 min-[900px]:relative min-[900px]:w-[272px] min-[900px]:translate-x-0 min-[900px]:[&.collapsed]:pointer-events-none min-[900px]:[&.collapsed]:absolute min-[900px]:[&.collapsed]:-translate-x-full min-[900px]:[&.collapsed]:opacity-0" aria-label="Sidebar">
  <div class="flex items-center justify-between gap-2 px-3.5 pb-1">
    <span class="font-display text-[0.95rem] font-semibold tracking-[-.02em] text-ink">Workspace</span>
    <button type="button" id="sidebarCloseBtn" class="inline-flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-[10px] border border-line bg-white text-ink transition hover:bg-accent-soft" aria-label="Close sidebar" title="Close sidebar">
      <svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/><path d="m16 9-3 3 3 3"/></svg>
    </button>
  </div>
  <div class="flex flex-col gap-3 px-3.5 pb-3">
    <button type="button" id="newChat" class="inline-flex min-h-11 w-full cursor-pointer items-center justify-center gap-2 rounded-full border-0 bg-accent px-4 text-[14px] font-semibold text-white shadow-[0_8px_20px_rgba(0,104,74,.22)] transition hover:brightness-105 active:scale-[.98]">
      <svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M12 5v14M5 12h14"/></svg>
      New Chat
    </button>
    <label class="flex items-center gap-2 rounded-full border border-line bg-white px-3 py-2.5 text-muted focus-within:border-accent/40 focus-within:text-accent">
      <svg class="size-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
      <input id="projectSearch" class="min-w-0 flex-1 border-0 bg-transparent text-[13px] text-ink outline-none placeholder:text-[#8a9a93]" type="search" placeholder="Search chats" autocomplete="off">
    </label>
  </div>
  <div class="min-h-0 flex-1 overflow-y-auto px-2.5 pb-2">
    <button type="button" id="projectsToggle" class="mb-1 flex w-full cursor-pointer items-center justify-between rounded-lg px-2 py-1.5 text-[11px] font-bold tracking-[.04em] text-muted uppercase hover:bg-white/70" aria-expanded="true">
      <span>Projects</span>
      <svg id="projectsChevron" class="size-3.5 transition-transform" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m6 9 6 6 6-6"/></svg>
    </button>
    <div id="projectList" class="flex flex-col gap-0.5">
      <div class="px-2 py-3 text-[12px] text-muted">Loading projects…</div>
    </div>
  </div>
  <div class="mt-auto flex shrink-0 flex-col gap-0.5 border-t border-line px-2.5 pt-2 pb-1">
    <button type="button" id="projectsManageToggle" class="side-nav-btn" title="Manage projects" aria-expanded="false" aria-controls="manageDrawer">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/><path d="M12 11v5M9.5 13.5h5"/></svg>
      Manage
    </button>
  </div>
  <div class="mx-2.5 mt-2 mb-1 flex shrink-0 items-center gap-2.5 rounded-2xl border border-line bg-white px-3 py-2.5 shadow-[0_4px_14px_rgba(18,32,28,.04)]">
    <div class="relative grid size-9 shrink-0 place-items-center" aria-hidden="true">
      <svg class="size-9 -rotate-90 text-line" viewBox="0 0 36 36"><circle cx="18" cy="18" r="15" fill="none" stroke="currentColor" stroke-width="3"/><circle id="statusRing" cx="18" cy="18" r="15" fill="none" stroke="var(--accent)" stroke-width="3" stroke-linecap="round" stroke-dasharray="94" stroke-dashoffset="18"/></svg>
      <span class="absolute size-2 rounded-full bg-ok"></span>
    </div>
    <div class="min-w-0 flex-1">
      <strong id="statusProjects" class="block truncate text-[12.5px] font-semibold text-ink">— projects active</strong>
      <span id="statusDetail" class="block truncate text-[11px] text-muted">Checking agent…</span>
    </div>
    <svg class="size-4 shrink-0 text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m9 6 6 6-6 6"/></svg>
  </div>
</aside>
<div id="manageDrawerBackdrop" class="fixed inset-0 z-[60] hidden bg-ink/35 backdrop-blur-[2px] [&.show]:block" aria-hidden="true"></div>
<aside id="manageDrawer" class="fixed inset-y-0 left-0 z-[70] flex w-[min(340px,92vw)] -translate-x-full flex-col border-r border-line bg-surface pt-[max(8px,env(safe-area-inset-top,0px))] pb-[max(8px,env(safe-area-inset-bottom,0px))] shadow-[8px_0_32px_rgba(18,32,28,.12)] transition-transform duration-200 ease-out [&.open]:translate-x-0" aria-label="Manage projects" aria-hidden="true">
  <div class="flex shrink-0 items-center justify-between gap-2 border-b border-line px-3 py-2">
    <div class="min-w-0">
      <strong class="block font-display text-[0.95rem] font-semibold tracking-[-.02em] text-ink">Manage projects</strong>
      <span class="block text-[11px] text-muted">Scan a folder and register projects.</span>
    </div>
    <button type="button" id="manageDrawerClose" class="inline-flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-lg border border-line bg-white text-ink transition hover:bg-accent-soft" aria-label="Close manage" title="Close">
      <svg class="size-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 6l12 12M18 6 6 18"/></svg>
    </button>
  </div>
  <div id="projectsManage" class="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto px-3 py-2.5">
    <section class="flex flex-col gap-1.5 rounded-xl border border-line bg-white p-2.5">
      <div class="text-[10px] font-bold tracking-[.04em] text-muted uppercase">Scan folder</div>
      <div id="projectsRootLabel" class="truncate text-[12px] font-semibold text-ink" title="">No folder chosen</div>
      <div id="projectsRootHint" class="text-[11px] text-muted">Choose a folder, then Scan.</div>
      <div class="grid grid-cols-2 gap-1.5">
        <button type="button" id="projectsChooseFolderBtn" class="inline-flex min-h-8 cursor-pointer items-center justify-center gap-1 rounded-full border border-line bg-chip px-2 text-[12px] font-semibold text-ink hover:bg-accent-soft">
          <svg class="size-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/></svg>
          Choose
        </button>
        <button type="button" id="projectsScanBtn" class="inline-flex min-h-8 cursor-pointer items-center justify-center rounded-full border-0 bg-accent px-2 text-[12px] font-semibold text-white hover:brightness-105">Scan</button>
      </div>
      <details>
        <summary class="cursor-pointer text-[11px] font-semibold text-muted">Or type a path</summary>
        <div class="mt-1.5 flex gap-1">
          <input id="projectsRootInput" class="min-w-0 flex-1 rounded-lg border border-line bg-white px-2 py-1.5 text-[12px] text-ink outline-none placeholder:text-[#8a9a93] focus:border-accent/40" type="text" placeholder="C:/laragon/www" autocomplete="off" spellcheck="false">
          <button type="button" id="projectsRootSaveBtn" class="shrink-0 cursor-pointer rounded-full border border-line bg-chip px-2.5 text-[11px] font-semibold text-ink hover:bg-accent-soft">Save</button>
        </div>
      </details>
    </section>
    <section class="flex min-h-0 flex-col gap-1 rounded-xl border border-line bg-white p-2.5">
      <div class="flex items-center justify-between gap-2">
        <div class="text-[10px] font-bold tracking-[.04em] text-muted uppercase">Unregistered</div>
        <span id="candidatesCount" class="text-[10px] text-muted">Scan to load</span>
      </div>
      <div id="candidatesList" class="flex max-h-[22vh] flex-col gap-1 overflow-y-auto text-[12px] text-muted">
        <div class="px-0.5 py-1">No scan yet.</div>
      </div>
    </section>
    <section class="flex min-h-0 flex-1 flex-col gap-1 rounded-xl border border-line bg-white p-2.5">
      <div class="flex items-center justify-between gap-2">
        <div class="text-[10px] font-bold tracking-[.04em] text-muted uppercase">Registered</div>
        <span id="registeredCount" class="text-[10px] text-muted">0</span>
      </div>
      <div id="manageRegistryList" class="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto"></div>
    </section>
  </div>
  <div class="shrink-0 border-t border-line px-3 py-2">
    <button type="button" id="manageDrawerDone" class="inline-flex min-h-9 w-full cursor-pointer items-center justify-center rounded-full border-0 bg-accent px-3 text-[13px] font-semibold text-white transition hover:brightness-105">Done</button>
  </div>
</aside>
<div class="chat-pane-bg relative flex min-w-0 flex-1 flex-col">
<div id="installBanner" class="hidden shrink-0 items-start justify-between gap-2.5 bg-ink px-3.5 py-2.5 text-[12.5px] leading-[1.4] text-white [&.show]:flex standalone:hidden!">
  <span>Install on iPhone: Safari Share → <b>Add to Home Screen</b> for a full-screen app icon.</span>
  <button type="button" id="dismissInstall" class="min-h-9 cursor-pointer rounded-lg border-0 bg-white/12 px-2.5 py-2 text-xs font-semibold whitespace-nowrap text-white">Got it</button>
</div>
<header id="chatHeader" class="z-20 flex shrink-0 items-center justify-between gap-2 border-b border-line bg-surface/95 px-[max(12px,env(safe-area-inset-right,0px))] pt-[max(8px,env(safe-area-inset-top,0px))] pb-2.5 pl-[max(12px,env(safe-area-inset-left,0px))] backdrop-blur-2xl">
  <div class="flex min-w-0 flex-1 items-center gap-2.5">
    <button type="button" id="menuBtn" class="inline-flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-[10px] border border-line bg-white text-ink transition hover:bg-accent-soft" aria-label="Open sidebar" aria-expanded="false" aria-controls="sidebar" title="Open sidebar">
      <svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 7h16M4 12h16M4 17h16"/></svg>
    </button>
    <div class="grid size-9 shrink-0 place-items-center rounded-full bg-accent text-white shadow-[0_6px_14px_rgba(0,104,74,.22)] [&_svg]:size-[17px]" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M5 8.5c0-2 1.8-3.5 4-3.5h6c2.2 0 4 1.5 4 3.5v4c0 2-1.8 3.5-4 3.5h-2.2L9 19v-3H9c-2.2 0-4-1.5-4-3.5z"/><circle cx="10" cy="10.5" r="1" fill="currentColor" stroke="none"/><circle cx="14" cy="10.5" r="1" fill="currentColor" stroke="none"/></svg>
    </div>
    <div class="min-w-0 flex-1">
      <strong class="block truncate font-display text-[1.08rem] leading-[1.05] tracking-[-.02em]">Cursor Orchestrator</strong>
      <span id="pill" class="group mt-0.5 flex min-w-0 items-center gap-1.5 text-[10.5px] text-muted"><span class="size-[7px] shrink-0 rounded-full bg-[#9aa8a1] group-[.live]:animate-dot group-[.live]:bg-ok group-[.off]:bg-bad"></span><span id="pillText" class="truncate">Connecting...</span></span>
    </div>
  </div>
  <div class="flex shrink-0 items-center justify-end gap-1.5">
    <button id="progressToggle" type="button" title="Activity" aria-controls="progressPanel" aria-expanded="false" class="hdr-icon-btn [&.on]:border-accent/35 [&.on]:bg-accent-soft [&.on]:text-accent">
      <svg class="size-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 19V5"/><path d="M4 19h16"/><path d="m8 14 3-3 3 2 4-5"/></svg>
    </button>
    <button id="notifyBtn" type="button" title="Enable notifications" class="hdr-icon-btn [&.on]:border-accent/35 [&.on]:bg-accent-soft [&.on]:text-accent">
      <svg class="size-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M6 9a6 6 0 1 1 12 0c0 7 3 7 3 7H3s3 0 3-7"/><path d="M10 19a2 2 0 0 0 4 0"/></svg>
    </button>
    <button id="refresh" type="button" title="Reload chat from server" class="hdr-icon-btn">
      <svg class="size-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 12a9 9 0 0 1 15.5-6.4M21 12a9 9 0 0 1-15.5 6.4"/><path d="M3 5v5h5M21 19v-5h-5"/></svg>
    </button>
    <button id="clearChat" type="button" title="Clear all chat messages" class="hdr-icon-btn">
      <svg class="size-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 7h16M9 7V5h6v2M8 7l1 12h6l1-12"/></svg>
    </button>
    <button id="popout" type="button" title="Open in new window" class="hdr-icon-btn max-[520px]:hidden">
      <svg class="size-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14 5h5v5"/><path d="M10 14 19 5"/><path d="M19 13v5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/></svg>
    </button>
    <button type="button" id="avatarBtn" title="Account" class="ml-1 grid size-9 shrink-0 cursor-pointer place-items-center rounded-full border border-line bg-[#e8eeeb] text-[11px] font-bold tracking-wide text-ink transition hover:border-accent/30 hover:bg-accent-soft">JD</button>
  </div>
</header>
<div id="activityDrawerBackdrop" class="fixed inset-0 z-[60] hidden bg-ink/35 backdrop-blur-[2px] [&.show]:block" aria-hidden="true"></div>
<aside id="progressPanel" class="activity-drawer idle fixed inset-y-0 right-0 z-[70] flex w-[min(400px,94vw)] translate-x-full flex-col border-l border-line bg-surface pt-[max(10px,env(safe-area-inset-top,0px))] pb-[max(10px,env(safe-area-inset-bottom,0px))] shadow-[-8px_0_32px_rgba(18,32,28,.12)] transition-transform duration-200 ease-out [&.open]:translate-x-0" aria-label="Activity" aria-hidden="true" aria-live="polite">
  <div class="activity-drawer-sweep" aria-hidden="true"></div>
  <div class="flex shrink-0 items-center justify-between gap-2 border-b border-line px-4 pb-3">
    <div class="min-w-0 flex-1">
      <div class="flex items-center gap-2">
        <strong class="font-display text-[1.05rem] font-semibold tracking-[-.02em] text-ink">Activity</strong>
        <span class="work-live-badge" id="progressLiveBadge"><span class="work-live-dot" aria-hidden="true"></span>Live</span>
      </div>
      <span id="progressMeta" class="mt-0.5 block truncate text-[12px] text-muted"></span>
    </div>
    <span id="progressElapsed" class="work-elapsed shrink-0" hidden></span>
    <button type="button" id="activityDrawerClose" class="inline-flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-[10px] border border-line bg-white text-ink transition hover:bg-accent-soft" aria-label="Close activity" title="Close">
      <svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 6l12 12M18 6 6 18"/></svg>
    </button>
  </div>
  <div class="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden px-4 py-3">
    <section class="activity-current shrink-0 rounded-2xl border border-line bg-white p-3 shadow-[0_4px_14px_rgba(18,32,28,.04)]">
      <strong id="progressStageLabel" class="work-compact-stage">No active task</strong>
      <span id="progressNow" class="work-compact-now mt-1 block">Start a coding task to see live progress</span>
      <div id="progressRail" class="work-rail mt-2.5" aria-hidden="true"></div>
      <div id="activityReviewActions" class="activity-review-actions" hidden>
        <p class="activity-review-hint">Coding finished — your project folder is unchanged until you approve.</p>
        <div class="activity-review-btns">
          <button type="button" id="activityApproveBtn" class="activity-review-approve">Approve &amp; apply</button>
          <button type="button" id="activityRejectBtn" class="activity-review-reject">Reject</button>
        </div>
      </div>
    </section>
    <section class="flex min-h-0 flex-1 flex-col gap-1.5">
      <div class="work-feed-head">
        <span class="work-feed-title">Current activity</span>
      </div>
      <ol id="progressEvents" class="work-feed activity-feed flex-1"></ol>
    </section>
    <section class="flex max-h-[34%] min-h-0 shrink-0 flex-col gap-1.5 border-t border-line pt-2.5">
      <div class="work-feed-head">
        <span class="work-feed-title">Task history</span>
      </div>
      <div id="activityHistory" class="activity-history flex-1 overflow-y-auto overscroll-contain"></div>
    </section>
  </div>
  <div class="shrink-0 border-t border-line px-4 py-3">
    <button type="button" id="clearActivityBtn" class="inline-flex min-h-11 w-full cursor-pointer items-center justify-center gap-2 rounded-full border border-line bg-white px-4 text-[13px] font-semibold text-ink transition hover:border-[#f0c4bf] hover:bg-[#fff5f4] hover:text-[#b42318]">
      <svg class="size-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 7h16M9 7V5h6v2M8 7l1 12h6l1-12"/></svg>
      Clear all activity
    </button>
  </div>
</aside>
<div id="log" class="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto overscroll-contain px-[max(14px,env(safe-area-inset-right,0px))] py-4 pl-[max(14px,env(safe-area-inset-left,0px))] [-webkit-overflow-scrolling:touch] min-[900px]:px-8">
  <div class="m-auto max-w-[300px] animate-rise text-center text-[.95rem] leading-normal text-muted" id="empty"><strong class="mb-2 block font-display text-[1.35rem] text-ink">Loading</strong>Fetching your conversation...</div>
</div>
<div id="busy" class="work-busy">
  <span class="work-busy-spinner" aria-hidden="true"></span>
  <span id="busyText" class="work-busy-text">Working on your request...</span>
  <button type="button" id="busyOpenProgress" class="work-busy-link">View activity</button>
</div>
<div id="reviewBanner" class="review-banner" hidden>
  <div class="review-banner-copy">
    <strong id="reviewBannerTitle">Ready for your approval</strong>
    <span id="reviewBannerHint">Not stuck — coding finished. Apply to update your project, or reject.</span>
  </div>
  <div class="review-banner-btns">
    <button type="button" id="bannerApproveBtn" class="activity-review-approve">Approve &amp; apply</button>
    <button type="button" id="bannerCommitApplyBtn" class="activity-review-approve" hidden>Commit local &amp; apply</button>
    <button type="button" id="bannerPushBtn" class="activity-review-reject">Approve &amp; push</button>
    <button type="button" id="bannerRejectBtn" class="activity-review-reject">Reject</button>
  </div>
</div>
<div id="quick" class="no-scrollbar flex shrink-0 gap-1.5 overflow-x-auto px-[max(12px,env(safe-area-inset-right,0px))] py-1.5 pl-[max(12px,env(safe-area-inset-left,0px))] [-webkit-overflow-scrolling:touch] min-[900px]:px-8">
  <button type="button" class="chip-btn" data-send="what projects do I have?">Projects</button>
  <button type="button" class="chip-btn" data-send="show my tasks">My tasks</button>
  <button type="button" class="chip-btn" data-send="how is my last task going?">Last task</button>
  <button type="button" class="chip-btn" data-send="what's remaining?">Remaining</button>
  <button type="button" class="chip-btn" data-send="what changes did you make?">Changes</button>
  <button type="button" class="chip-btn" data-fill="on ">Ask on a project...</button>
  <button type="button" class="chip-btn" data-send="approve and apply">Approve &amp; apply</button>
  <button type="button" class="chip-btn" data-send="approve and push">Approve &amp; push</button>
  <button type="button" class="chip-btn" data-send="apply locally">Apply locally</button>
  <button type="button" class="chip-btn" data-send="commit my local changes">Commit local</button>
  <button type="button" class="chip-btn" data-send="stash my local changes">Stash local</button>
  <button type="button" class="chip-btn" data-send="commit local and apply">Commit &amp; apply</button>
  <button type="button" class="chip-btn" data-send="reject that">Reject</button>
  <button type="button" class="chip-btn" data-send="cancel that task">Cancel task</button>
  <button type="button" class="chip-btn" data-send="what can you do?">Help</button>
</div>
<div id="composer" class="shrink-0 px-[max(12px,env(safe-area-inset-right,0px))] pt-1 pb-[max(12px,env(safe-area-inset-bottom,0px))] pl-[max(12px,env(safe-area-inset-left,0px))] min-[900px]:px-8">
<form id="f" class="flex items-end gap-1.5 rounded-full border border-line bg-white py-1.5 pr-1.5 pl-2 shadow-[0_10px_30px_rgba(18,32,28,.07)] transition focus-within:border-accent/40 focus-within:shadow-[0_12px_34px_rgba(0,104,74,.12)]">
  <button type="button" id="attachBtn" title="Attach" aria-label="Attach" class="grid size-10 shrink-0 cursor-pointer place-items-center rounded-full border-0 bg-transparent text-muted transition hover:bg-accent-soft hover:text-accent">
    <svg class="size-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m15.5 8.5-6.2 6.2a2.2 2.2 0 0 0 3.1 3.1l7.4-7.4a3.8 3.8 0 0 0-5.4-5.4L7 12.4a5.4 5.4 0 0 0 7.6 7.6l5.5-5.5"/></svg>
  </button>
  <textarea id="txt" rows="1" class="max-h-[96px] flex-1 resize-none border-0 bg-transparent py-2.5 text-[15px] leading-[1.35] text-ink outline-none placeholder:text-[#8a9a93]" placeholder="Message like ChatGPT — e.g. on my-project, improve form validation" autocomplete="off" autocorrect="on" autocapitalize="sentences" spellcheck="true" inputmode="text" enterkeyhint="send"></textarea>
  <button type="button" id="micBtn" title="Voice" aria-label="Dictate with voice" class="grid size-10 shrink-0 cursor-pointer place-items-center rounded-full border-0 bg-transparent text-muted transition hover:bg-accent-soft hover:text-accent [&.listening]:bg-[#fee2e2] [&.listening]:text-[#b91c1c]">
    <svg class="size-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>
  </button>
  <button id="send" type="submit" title="Send" aria-label="Send" class="grid size-11 shrink-0 cursor-pointer place-items-center rounded-[14px] border-0 bg-accent text-white shadow-[0_6px_16px_rgba(0,104,74,.28)] transition hover:bg-[#00553d] active:scale-[.97] disabled:opacity-45 [&_svg]:size-[18px]">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><path d="m5 12 14-7-5.5 14-2.2-5.3L5 12z"/><path d="M11.3 13.7 19 5"/></svg>
  </button>
</form>
</div>
<button id="jump" type="button" title="Jump to latest" class="absolute left-1/2 z-30 hidden -translate-x-1/2 items-center gap-0 rounded-full border border-line bg-white px-3.5 py-1 text-[11px] font-semibold tracking-wide text-muted shadow-[0_6px_18px_rgba(18,32,28,.1)] bottom-[88px] [&.show]:inline-flex [&.show]:animate-rise before:absolute before:top-1/2 before:-left-[42vw] before:h-px before:w-[40vw] before:bg-line before:content-[''] after:absolute after:top-1/2 after:-right-[42vw] after:h-px after:w-[40vw] after:bg-line after:content-['']">Latest</button>
<div id="toast" class="pointer-events-none absolute bottom-[72px] left-1/2 z-40 max-w-[min(90vw,360px)] -translate-x-1/2 translate-y-2 rounded-xl bg-ink px-4 py-2.5 text-center text-[13px] text-white opacity-0 shadow-[0_12px_30px_rgba(18,32,28,.2)] transition duration-200 [&.show]:translate-y-0 [&.show]:opacity-100"></div>
</div>
<div id="confirmModal" class="confirm-modal" hidden aria-hidden="true">
  <div class="confirm-backdrop" data-confirm-cancel></div>
  <div class="confirm-card" role="dialog" aria-modal="true" aria-labelledby="confirmTitle" aria-describedby="confirmMsg">
    <div class="confirm-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M12 8v5"/><circle cx="12" cy="16.5" r="1" fill="currentColor" stroke="none"/></svg>
    </div>
    <strong id="confirmTitle" class="confirm-title">Confirm</strong>
    <p id="confirmMsg" class="confirm-msg"></p>
    <div class="confirm-actions">
      <button type="button" id="confirmCancel" class="confirm-btn confirm-btn-ghost" data-confirm-cancel>Cancel</button>
      <button type="button" id="confirmOk" class="confirm-btn confirm-btn-primary">OK</button>
    </div>
  </div>
</div>
<div id="folderPickerModal" class="confirm-modal !z-[80]" hidden aria-hidden="true">
  <div class="confirm-backdrop" data-folder-cancel></div>
  <div class="confirm-card !max-w-[min(94vw,420px)] !items-stretch !p-0" role="dialog" aria-modal="true" aria-labelledby="folderPickerTitle">
    <div class="flex items-center justify-between gap-2 border-b border-line px-4 py-3">
      <strong id="folderPickerTitle" class="text-[15px] font-semibold text-ink">Choose folder</strong>
      <button type="button" id="folderPickerClose" class="grid size-8 cursor-pointer place-items-center rounded-full border-0 bg-transparent text-muted hover:bg-accent-soft" aria-label="Close" data-folder-cancel>
        <svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 6l12 12M18 6 6 18"/></svg>
      </button>
    </div>
    <div class="flex items-center gap-2 border-b border-line px-3 py-2">
      <button type="button" id="folderPickerUp" class="inline-flex min-h-8 shrink-0 cursor-pointer items-center rounded-full border border-line bg-chip px-3 text-[12px] font-semibold text-ink hover:bg-accent-soft disabled:opacity-40">Up</button>
      <div id="folderPickerPath" class="min-w-0 flex-1 truncate text-[12px] text-muted" title="">This PC</div>
    </div>
    <div id="folderPickerList" class="max-h-[min(50vh,320px)] min-h-[180px] overflow-y-auto px-2 py-2"></div>
    <div class="flex items-center justify-end gap-2 border-t border-line px-3 py-3">
      <button type="button" class="confirm-btn confirm-btn-ghost" data-folder-cancel>Cancel</button>
      <button type="button" id="folderPickerSelect" class="confirm-btn confirm-btn-primary">Use this folder</button>
    </div>
  </div>
</div>
<script nonce="__NONCE__">
const log = document.getElementById('log');
const txt = document.getElementById('txt');
const sendBtn = document.getElementById('send');
const busy = document.getElementById('busy');
const pill = document.getElementById('pill');
const pillText = document.getElementById('pillText');
const toast = document.getElementById('toast');
const notifyBtn = document.getElementById('notifyBtn');
const jump = document.getElementById('jump');
const sidebar = document.getElementById('sidebar');
const sidebarBackdrop = document.getElementById('sidebarBackdrop');
const menuBtn = document.getElementById('menuBtn');
const sidebarCloseBtn = document.getElementById('sidebarCloseBtn');
const projectList = document.getElementById('projectList');
const projectSearch = document.getElementById('projectSearch');
const projectsManage = document.getElementById('projectsManage');
const manageDrawer = document.getElementById('manageDrawer');
const manageDrawerBackdrop = document.getElementById('manageDrawerBackdrop');
const projectsManageToggle = document.getElementById('projectsManageToggle');
const candidatesList = document.getElementById('candidatesList');
const candidatesCount = document.getElementById('candidatesCount');
const manageRegistryList = document.getElementById('manageRegistryList');
const registeredCount = document.getElementById('registeredCount');
const projectsRootInput = document.getElementById('projectsRootInput');
const projectsRootHint = document.getElementById('projectsRootHint');
const projectsRootLabel = document.getElementById('projectsRootLabel');
const folderPickerModal = document.getElementById('folderPickerModal');
const folderPickerList = document.getElementById('folderPickerList');
const folderPickerPath = document.getElementById('folderPickerPath');
const folderPickerUp = document.getElementById('folderPickerUp');
let projectsRootInfo = null;
let folderPickerCurrent = null;
let folderPickerParent = null;
const SIDEBAR_COLLAPSED_KEY = 'orch-sidebar-collapsed';
const desktopSidebarMq = window.matchMedia('(min-width: 900px)');
let last = 0;
let sending = false;
let pollBusy = false;
let toastTimer = null;
let bootstrapped = false;
// Back off polls when the tunnel/origin is briefly down (avoids console 502 floods).
let pollDelayMs = 1500;
let statusDelayMs = 5000;
let progressDelayMs = 1500;
const POLL_DELAY_MIN = 1500;
const POLL_DELAY_MAX = 20000;
const STATUS_DELAY_MIN = 5000;
const STATUS_DELAY_MAX = 30000;
const PROGRESS_DELAY_MIN = 1500;
const PROGRESS_DELAY_MAX = 20000;
let transportDown = false;
function noteTransportOk() {
  pollDelayMs = POLL_DELAY_MIN;
  statusDelayMs = STATUS_DELAY_MIN;
  progressDelayMs = PROGRESS_DELAY_MIN;
  if (transportDown) {
    transportDown = false;
  }
}
function noteTransportFail() {
  transportDown = true;
  pollDelayMs = Math.min(POLL_DELAY_MAX, Math.floor(pollDelayMs * 1.8));
  statusDelayMs = Math.min(STATUS_DELAY_MAX, Math.floor(statusDelayMs * 1.6));
  progressDelayMs = Math.min(PROGRESS_DELAY_MAX, Math.floor(progressDelayMs * 1.8));
  setPill('off');
  if (pillText) pillText.textContent = 'Reconnecting…';
  const detail = document.getElementById('statusDetail');
  if (detail) detail.textContent = 'Reconnecting to laptop…';
}
let activeProject = '';
let allProjects = [];
let inflightProjects = new Set();
const seenMsgIds = new Set();
const LEVEL_TITLE = {success:'Ready', error:'Needs attention', warning:'Heads up', info:'Update'};
const LEVEL_LABEL = {success:'Ready', error:'Needs attention', warning:'Heads up'};
const EMPTY = 'm-auto max-w-[300px] animate-rise text-center text-[.95rem] leading-normal text-muted';
const EMPTY_TITLE = 'mb-2 block font-display text-[1.35rem] text-ink';
const AGENT_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M5 8.5c0-2 1.8-3.5 4-3.5h6c2.2 0 4 1.5 4 3.5v4c0 2-1.8 3.5-4 3.5h-2.2L9 19v-3H9c-2.2 0-4-1.5-4-3.5z"/><circle cx="10" cy="10.5" r="1" fill="currentColor" stroke="none"/><circle cx="14" cy="10.5" r="1" fill="currentColor" stroke="none"/></svg>';
const ICON_COPY = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M4 16V6a2 2 0 0 1 2-2h10"/></svg>';
const ICON_UP = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h10.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3z"/><path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>';
const ICON_DOWN = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H6.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3z"/><path d="M17 2h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3"/></svg>';
const ICON_MORE = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="6" cy="12" r="1.2" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.2" fill="currentColor" stroke="none"/><circle cx="18" cy="12" r="1.2" fill="currentColor" stroke="none"/></svg>';
const ICON_CHECK = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12 4.5 4.5L19 7"/></svg>';
const ICON_CHECKS = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.9"><path d="m2.5 12.5 3.5 3.5L13 8"/><path d="m9.5 12.5 3.5 3.5L21 8"/></svg>';
const ICON_FOLDER = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M3 8.5A1.5 1.5 0 0 1 4.5 7H9l2 2h8.5A1.5 1.5 0 0 1 21 10.5v7A1.5 1.5 0 0 1 19.5 19h-15A1.5 1.5 0 0 1 3 17.5v-9z"/></svg>';

function setPill(state) {
  pill.classList.remove('live', 'off');
  if (state) pill.classList.add(state);
}

function showToast(msg, ms) {
  toast.textContent = msg;
  // Keep toast above the iPhone keyboard (visualViewport shrinks when kb opens).
  try {
    const vv = window.visualViewport;
    if (vv) {
      const occluded = Math.max(0, window.innerHeight - vv.height - (vv.offsetTop || 0));
      toast.style.bottom = Math.round(72 + occluded) + 'px';
    } else {
      toast.style.bottom = '';
    }
  } catch (e) {
    toast.style.bottom = '';
  }
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), ms || 2800);
}

const confirmModal = document.getElementById('confirmModal');
const confirmTitle = document.getElementById('confirmTitle');
const confirmMsg = document.getElementById('confirmMsg');
const confirmOk = document.getElementById('confirmOk');
const confirmCancel = document.getElementById('confirmCancel');
let confirmResolver = null;

function closeConfirm(result) {
  if (!confirmResolver) return;
  const resolve = confirmResolver;
  confirmResolver = null;
  confirmModal.hidden = true;
  confirmModal.setAttribute('aria-hidden', 'true');
  confirmModal.classList.remove('open');
  resolve(result);
}

function askConfirm(message, opts) {
  const options = opts || {};
  confirmTitle.textContent = options.title || 'Confirm';
  confirmMsg.textContent = message;
  confirmOk.textContent = options.okLabel || 'OK';
  confirmCancel.textContent = options.cancelLabel || 'Cancel';
  confirmOk.classList.toggle('danger', !!options.danger);
  return new Promise((resolve) => {
    confirmResolver = resolve;
    confirmModal.hidden = false;
    confirmModal.setAttribute('aria-hidden', 'false');
    requestAnimationFrame(() => confirmModal.classList.add('open'));
    confirmOk.focus();
  });
}

confirmOk.addEventListener('click', () => closeConfirm(true));
confirmModal.querySelectorAll('[data-confirm-cancel]').forEach((el) => {
  el.addEventListener('click', () => closeConfirm(false));
});
document.addEventListener('keydown', (e) => {
  if (!confirmResolver) return;
  if (e.key === 'Escape') { e.preventDefault(); closeConfirm(false); }
  if (e.key === 'Enter') { e.preventDefault(); closeConfirm(true); }
});

function nearBottom() {
  return log.scrollTop + log.clientHeight >= log.scrollHeight - 64;
}

function syncJump() {
  jump.classList.toggle('show', !nearBottom() && bootstrapped);
}

function isDesktopSidebar() {
  return desktopSidebarMq.matches;
}

function isSidebarVisible() {
  return isDesktopSidebar()
    ? !sidebar.classList.contains('collapsed')
    : sidebar.classList.contains('open');
}

function syncSidebarControls() {
  const visible = isSidebarVisible();
  menuBtn.setAttribute('aria-expanded', visible ? 'true' : 'false');
  menuBtn.setAttribute('aria-label', visible ? 'Close sidebar' : 'Open sidebar');
  menuBtn.title = visible ? 'Close sidebar' : 'Open sidebar';
  sidebarCloseBtn.setAttribute('aria-label', 'Close sidebar');
  sidebarCloseBtn.title = 'Close sidebar';
}

function setSidebarCollapsed(collapsed) {
  sidebar.classList.toggle('collapsed', !!collapsed);
  try { localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? '1' : '0'); } catch (e) {}
  syncSidebarControls();
}

function setSidebarOpen(open) {
  // Mobile drawer only — desktop uses collapsed/expanded instead.
  const show = !!open && !isDesktopSidebar();
  sidebar.classList.toggle('open', show);
  sidebarBackdrop.classList.toggle('show', show);
  sidebarBackdrop.setAttribute('aria-hidden', show ? 'false' : 'true');
  syncSidebarControls();
}

function toggleSidebar() {
  if (isDesktopSidebar()) {
    setSidebarCollapsed(!sidebar.classList.contains('collapsed'));
    return;
  }
  setSidebarOpen(!sidebar.classList.contains('open'));
}

function closeSidebar() {
  if (isDesktopSidebar()) {
    setSidebarCollapsed(true);
    return;
  }
  setSidebarOpen(false);
}

try {
  if (localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1') {
    sidebar.classList.add('collapsed');
  }
} catch (e) {}
syncSidebarControls();
desktopSidebarMq.addEventListener('change', () => {
  sidebar.classList.remove('open');
  sidebarBackdrop.classList.remove('show');
  sidebarBackdrop.setAttribute('aria-hidden', 'true');
  syncSidebarControls();
});

function syncNotifyBtn() {
  if (!('Notification' in window)) {
    notifyBtn.style.display = 'none';
    return;
  }
  notifyBtn.classList.toggle('on', Notification.permission === 'granted');
  notifyBtn.title = Notification.permission === 'granted'
    ? 'Notifications on'
    : 'Enable notifications';
}

async function enableNotifications() {
  if (!('Notification' in window)) {
    showToast('Notifications not supported here');
    return;
  }
  const perm = await Notification.requestPermission();
  syncNotifyBtn();
  if (perm !== 'granted') {
    showToast('Notifications blocked - enable in browser settings');
    return;
  }
  if ('serviceWorker' in navigator) {
    try {
      await navigator.serviceWorker.register('/chat/sw.js', {scope: '/chat/'});
      showToast('Notifications enabled');
    } catch (e) {
      showToast('Notifications on (no service worker)');
    }
  } else {
    showToast('Notifications enabled');
  }
}

function pushNotify(m) {
  if (m.direction !== 'out') return;
  if (!('Notification' in window) || Notification.permission !== 'granted') return;
  const level = m.level || 'info';
  if (level === 'info' && document.visibilityState === 'visible' && document.hasFocus()) return;
  const title = 'Orchestrator - ' + (LEVEL_TITLE[level] || 'Update');
  const body = (m.text || '').slice(0, 180);
  const opts = {body, tag: 'orch-' + m.id, renotify: true, data: {url: '/chat'}};
  if (navigator.serviceWorker && navigator.serviceWorker.controller) {
    navigator.serviceWorker.controller.postMessage({type: 'notify', title, ...opts, level});
  } else {
    try { new Notification(title, opts); } catch (e) {}
  }
}

function renderProjects(filter) {
  const q = (filter || '').trim().toLowerCase();
  const items = allProjects.filter(p => {
    if (!q) return true;
    return p.id.toLowerCase().includes(q) || (p.name || '').toLowerCase().includes(q);
  });
  projectList.innerHTML = '';
  const allBtn = document.createElement('button');
  allBtn.type = 'button';
  const allActive = !activeProject;
  allBtn.className = 'proj-item' + (allActive ? ' active' : '');
  allBtn.dataset.id = '';
  if (allActive) allBtn.setAttribute('aria-current', 'true');
  allBtn.innerHTML = ICON_FOLDER + '<span class="name">All Projects</span><span class="count">' + allProjects.length + '</span>';
  allBtn.addEventListener('click', () => selectProject(''));
  projectList.appendChild(allBtn);
  if (!items.length) {
    const empty = document.createElement('div');
    empty.className = 'px-2 py-3 text-[12px] text-muted';
    empty.textContent = q ? 'No matching projects' : 'No projects registered';
    projectList.appendChild(empty);
  } else {
    for (const p of items) {
      const b = document.createElement('button');
      b.type = 'button';
      const isActive = activeProject === p.id;
      const isWorking = inflightProjects.has(p.id);
      b.className = 'proj-item' + (isActive ? ' active' : '') + (isWorking ? ' working' : '');
      b.dataset.id = p.id;
      if (isActive) b.setAttribute('aria-current', 'true');
      b.title = isWorking
        ? ((p.name || p.id) + ' — agent working in background')
        : (p.path || p.name || p.id);
      b.innerHTML = ICON_FOLDER
        + '<span class="name"></span>'
        + (isWorking ? '<span class="work-dot" aria-hidden="true"></span>' : '')
        + '<span class="count"></span>';
      b.querySelector('.name').textContent = p.name || p.id;
      b.querySelector('.count').textContent = isWorking ? 'live' : ((p.type || '').slice(0, 4));
      b.addEventListener('click', () => selectProject(p.id));
      projectList.appendChild(b);
    }
  }
  renderManageRegistry();
}

function renderManageRegistry() {
  if (!manageRegistryList) return;
  manageRegistryList.innerHTML = '';
  if (registeredCount) registeredCount.textContent = String(allProjects.length);
  if (!allProjects.length) {
    const empty = document.createElement('div');
    empty.className = 'px-0.5 py-1 text-[11px] text-muted';
    empty.textContent = 'None registered yet.';
    manageRegistryList.appendChild(empty);
    return;
  }
  for (const p of allProjects) {
    const id = String(p.id || p.name || '').trim() || 'unknown';
    const row = document.createElement('div');
    row.className = 'manage-proj-row';
    const top = document.createElement('div');
    top.className = 'manage-proj-top';
    const title = document.createElement('div');
    title.className = 'manage-proj-name';
    title.textContent = id;
    title.title = p.path || id;
    const actions = document.createElement('div');
    actions.className = 'manage-proj-actions';
    const pushLabel = document.createElement('label');
    pushLabel.className = 'manage-proj-flag';
    const pushCb = document.createElement('input');
    pushCb.type = 'checkbox';
    pushCb.checked = !!p.allow_push;
    pushCb.disabled = (p.type || '') === 'local';
    pushCb.addEventListener('change', () => patchProjectFlags(id, {allow_push: pushCb.checked}));
    pushLabel.appendChild(pushCb);
    pushLabel.appendChild(document.createTextNode('push'));
    const applyLabel = document.createElement('label');
    applyLabel.className = 'manage-proj-flag';
    const applyCb = document.createElement('input');
    applyCb.type = 'checkbox';
    applyCb.checked = !!p.apply_local;
    applyCb.disabled = (p.type || '') === 'local';
    applyCb.addEventListener('change', () => patchProjectFlags(id, {apply_local: applyCb.checked}));
    applyLabel.appendChild(applyCb);
    applyLabel.appendChild(document.createTextNode('apply'));
    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'manage-proj-remove';
    removeBtn.textContent = 'Remove';
    removeBtn.addEventListener('click', () => removeRegisteredProject(id));
    actions.appendChild(pushLabel);
    actions.appendChild(applyLabel);
    actions.appendChild(removeBtn);
    top.appendChild(title);
    top.appendChild(actions);
    const meta = document.createElement('div');
    meta.className = 'manage-proj-meta';
    meta.textContent = (p.type || 'local') + (p.path ? ' · ' + p.path : '');
    meta.title = p.path || '';
    row.appendChild(top);
    row.appendChild(meta);
    manageRegistryList.appendChild(row);
  }
}

function renderCandidates(candidates) {
  if (!candidatesList) return;
  candidatesList.innerHTML = '';
  const fresh = (candidates || []).filter(c => !c.registered);
  if (candidatesCount) {
    candidatesCount.textContent = fresh.length ? (fresh.length + ' found') : 'None';
  }
  if (!fresh.length) {
    const empty = document.createElement('div');
    empty.className = 'px-0.5 py-1 text-[11px]';
    empty.textContent = 'No unregistered folders.';
    candidatesList.appendChild(empty);
    return;
  }
  for (const c of fresh) {
    const row = document.createElement('div');
    row.className = 'flex items-center gap-2 rounded-lg border border-line bg-chip/40 px-2 py-1';
    const meta = document.createElement('div');
    meta.className = 'min-w-0 flex-1';
    const name = document.createElement('div');
    name.className = 'truncate text-[12px] font-semibold leading-tight text-ink';
    name.textContent = c.id;
    name.title = c.path || c.id;
    const path = document.createElement('div');
    path.className = 'truncate text-[10px] text-muted';
    path.textContent = (c.type || 'local') + (c.path ? ' · ' + c.path : '');
    meta.appendChild(name);
    meta.appendChild(path);
    const addBtn = document.createElement('button');
    addBtn.type = 'button';
    addBtn.className = 'shrink-0 cursor-pointer rounded-full border-0 bg-accent px-2.5 py-0.5 text-[11px] font-semibold text-white';
    addBtn.textContent = 'Add';
    addBtn.addEventListener('click', () => registerCandidate(c));
    row.appendChild(meta);
    row.appendChild(addBtn);
    candidatesList.appendChild(row);
  }
}

function applyProjectsRootInfo(info) {
  projectsRootInfo = info || null;
  const path = (info && info.path) || '';
  if (projectsRootInput && path && !projectsRootInput.matches(':focus')) {
    projectsRootInput.value = path;
  }
  if (projectsRootLabel) {
    projectsRootLabel.textContent = path || 'No folder chosen';
    projectsRootLabel.title = path || '';
  }
  if (projectsRootHint) {
    if (!path) {
      projectsRootHint.textContent = 'Choose a folder on this PC, then Scan.';
    } else {
      const src = info.source === 'override' ? 'chosen' : (info.source === 'env' ? 'from .env' : info.source);
      projectsRootHint.textContent = 'Ready to scan (' + src + ')';
    }
  }
}

async function persistProjectsRoot(path) {
  const r = await fetch('/chat/projects/root', {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({path}),
  });
  if (r.status === 401) { location.reload(); return null; }
  const j = await r.json();
  if (!r.ok) {
    showToast(j.error || 'Could not save folder');
    return null;
  }
  applyProjectsRootInfo(j.projects_root);
  return j.projects_root;
}

async function saveProjectsRoot() {
  const path = (projectsRootInput && projectsRootInput.value || '').trim();
  if (!path) {
    showToast('Enter a folder path first');
    return;
  }
  try {
    const info = await persistProjectsRoot(path);
    if (info) showToast('Scan folder saved');
  } catch (e) {
    showToast('Could not save folder');
  }
}

function closeFolderPicker() {
  if (!folderPickerModal) return;
  folderPickerModal.hidden = true;
  folderPickerModal.setAttribute('aria-hidden', 'true');
  folderPickerModal.classList.remove('open');
}

async function openFolderPicker() {
  if (!folderPickerModal) return;
  folderPickerModal.hidden = false;
  folderPickerModal.setAttribute('aria-hidden', 'false');
  // Same as confirmModal: CSS keeps .confirm-modal at opacity:0 until .open.
  requestAnimationFrame(() => folderPickerModal.classList.add('open'));
  const start = (projectsRootInfo && projectsRootInfo.path) || (projectsRootInput && projectsRootInput.value) || '';
  await loadFolderPicker(start);
}

async function loadFolderPicker(path) {
  if (!folderPickerList) return;
  folderPickerList.innerHTML = '<div class="px-2 py-3 text-[12px] text-muted">Loading…</div>';
  try {
    const q = path ? ('?path=' + encodeURIComponent(path)) : '';
    const r = await fetch('/chat/projects/browse' + q, {cache: 'no-store'});
    if (r.status === 401) { location.reload(); return; }
    const j = await r.json();
    if (!r.ok) {
      folderPickerList.innerHTML = '<div class="px-2 py-3 text-[12px] text-[#b91c1c]"></div>';
      folderPickerList.firstChild.textContent = j.error || 'Could not open folder';
      return;
    }
    folderPickerCurrent = j.path || null;
    folderPickerParent = (j.parent === '' || j.parent) ? j.parent : null;
    if (folderPickerPath) {
      folderPickerPath.textContent = j.path || 'This PC';
      folderPickerPath.title = j.path || 'This PC';
    }
    if (folderPickerUp) {
      const canUp = j.at_root ? false : (j.parent === '' || !!j.parent || !!j.path);
      folderPickerUp.disabled = !canUp;
    }
    folderPickerList.innerHTML = '';
    const entries = j.entries || [];
    if (!entries.length) {
      const empty = document.createElement('div');
      empty.className = 'px-2 py-3 text-[12px] text-muted';
      empty.textContent = j.at_root ? 'No drives found.' : 'No subfolders here. You can still use this folder.';
      folderPickerList.appendChild(empty);
      return;
    }
    for (const entry of entries) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'flex w-full cursor-pointer items-center gap-2 rounded-lg px-2 py-2 text-left text-[13px] text-ink hover:bg-accent-soft';
      btn.innerHTML = '<svg class="size-4 shrink-0 text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/></svg><span class="min-w-0 flex-1 truncate"></span>';
      btn.querySelector('span').textContent = entry.name || entry.path;
      btn.title = entry.path || entry.name;
      btn.addEventListener('click', () => loadFolderPicker(entry.path));
      folderPickerList.appendChild(btn);
    }
  } catch (e) {
    folderPickerList.innerHTML = '<div class="px-2 py-3 text-[12px] text-[#b91c1c]">Could not open folder</div>';
  }
}

async function selectFolderFromPicker() {
  if (!folderPickerCurrent) {
    showToast('Open a drive or folder first');
    return;
  }
  try {
    const info = await persistProjectsRoot(folderPickerCurrent);
    if (!info) return;
    closeFolderPicker();
    showToast('Folder selected');
  } catch (e) {
    showToast('Could not save folder');
  }
}

async function scanProjectFolders() {
  try {
    if (!(projectsRootInfo && projectsRootInfo.path)) {
      showToast('Choose a folder first');
      await openFolderPicker();
      return;
    }
    const r = await fetch('/chat/projects/candidates', {cache: 'no-store'});
    if (r.status === 401) { location.reload(); return; }
    const j = await r.json();
    if (!r.ok) {
      showToast(j.error || 'Scan failed');
      return;
    }
    if (j.projects_root) applyProjectsRootInfo(j.projects_root);
    renderCandidates(j.candidates || []);
    showToast('Scan complete');
  } catch (e) {
    showToast('Scan failed');
  }
}

async function registerCandidate(c) {
  try {
    const r = await fetch('/chat/projects', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id: c.id, path: c.path}),
    });
    if (r.status === 401) { location.reload(); return; }
    const j = await r.json();
    if (!r.ok) {
      showToast(j.error || 'Could not add project');
      return;
    }
    showToast('Added ' + (j.project && j.project.id ? j.project.id : c.id));
    await refreshStatus();
    await scanProjectFolders();
  } catch (e) {
    showToast('Could not add project');
  }
}

async function patchProjectFlags(id, fields) {
  try {
    const r = await fetch('/chat/projects/' + encodeURIComponent(id), {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(fields),
    });
    if (r.status === 401) { location.reload(); return; }
    const j = await r.json();
    if (!r.ok) {
      showToast(j.error || 'Update failed');
      await refreshStatus();
      return;
    }
    showToast('Updated ' + id);
    await refreshStatus();
  } catch (e) {
    showToast('Update failed');
  }
}

async function removeRegisteredProject(id) {
  if (!window.confirm('Remove "' + id + '" from the registry? The folder on disk stays.')) return;
  try {
    const wasActive = activeProject === id;
    const r = await fetch('/chat/projects/' + encodeURIComponent(id), {method: 'DELETE'});
    if (r.status === 401) { location.reload(); return; }
    const j = await r.json();
    if (!r.ok) {
      showToast(j.error || 'Remove failed');
      return;
    }
    showToast('Removed ' + id);
    // Stay on All Projects (do not jump to another registered project).
    if (wasActive) {
      await selectProject('');
    } else {
      await refreshStatus();
    }
  } catch (e) {
    showToast('Remove failed');
  }
}

async function selectProject(id) {
  activeProject = id || '';
  renderProjects(projectSearch.value);
  setSidebarOpen(false);
  try {
    const r = await fetch('/chat/active-project', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({project: id || ''}),
    });
    if (r.status === 401) { location.reload(); return; }
    const j = await r.json();
    if (!r.ok) {
      showToast(j.error || 'Could not switch project');
      return;
    }
    // Always reload the project-scoped thread so LifeOS chat cannot leak.
    resetLog();
    const stick = true;
    for (const m of (j.messages || [])) {
      add(m, {notify: false});
      if (m.id > last) last = m.id;
    }
    bootstrapped = true;
    if (!last) {
      const emptyEl = document.getElementById('empty');
      if (emptyEl) {
        emptyEl.innerHTML = id
          ? ('<strong class="' + EMPTY_TITLE + '">' + id + '</strong>Fresh chat for this project. What should I change?')
          : ('<strong class="' + EMPTY_TITLE + '">Hi</strong>What can I help you with?');
      }
    }
    if (stick) log.scrollTop = log.scrollHeight;
    showToast(id ? ('Switched to ' + id) : 'Showing all projects');
    await refreshStatus();
  } catch (e) {
    showToast('Could not switch project');
  }
  if (id) {
    txt.value = '';
    txt.placeholder = 'Message about ' + id + '…';
    txt.focus();
    autoSize();
  } else {
    txt.placeholder = 'Message like ChatGPT - e.g. on my-project, improve form validation';
  }
}

function add(m, {notify=false} = {}) {
  if (m.id != null) {
    if (seenMsgIds.has(m.id)) return false;
    seenMsgIds.add(m.id);
  }
  const emptyEl = document.getElementById('empty');
  if (emptyEl) emptyEl.remove();
  const level = m.level || 'info';
  const incoming = m.direction === 'in';
  const row = document.createElement('div');
  row.className = 'msg-row' + (incoming ? ' user' : '');
  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar ' + (incoming ? 'user' : 'agent');
  avatar.innerHTML = incoming ? 'JD' : AGENT_ICON;
  avatar.setAttribute('aria-hidden', 'true');
  const col = document.createElement('div');
  col.className = 'msg-col';
  const meta = document.createElement('div');
  meta.className = 'msg-meta';
  const name = document.createElement('span');
  name.className = 'msg-name';
  name.textContent = incoming ? 'You' : 'Cursor Orchestrator';
  const time = document.createElement('span');
  time.className = 'msg-time';
  time.textContent = new Date(m.ts * 1000).toLocaleTimeString();
  meta.appendChild(name);
  meta.appendChild(time);
  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble ' + (incoming ? 'user' : 'agent');
  if (!incoming && LEVEL_LABEL[level]) {
    const badge = document.createElement('div');
    badge.className = 'msg-level ' + level;
    if (level === 'success') badge.innerHTML = ICON_CHECK;
    const label = document.createElement('span');
    label.textContent = LEVEL_LABEL[level];
    badge.appendChild(label);
    bubble.appendChild(badge);
  }
  const body = document.createElement('div');
  body.className = 'msg-bubble-text';
  body.textContent = m.text;
  bubble.appendChild(body);
  col.appendChild(meta);
  col.appendChild(bubble);
  if (!incoming) {
    if (isReviewReadyMessage(m)) {
      const cta = document.createElement('div');
      cta.className = 'msg-review-cta';
      const approve = document.createElement('button');
      approve.type = 'button';
      approve.className = 'activity-review-approve';
      approve.textContent = 'Approve & apply';
      approve.addEventListener('click', () => send('approve and apply'));
      const reject = document.createElement('button');
      reject.type = 'button';
      reject.className = 'activity-review-reject';
      reject.textContent = 'Reject';
      reject.addEventListener('click', () => send('reject that'));
      cta.appendChild(approve);
      cta.appendChild(reject);
      col.appendChild(cta);
    }
    const actions = document.createElement('div');
    actions.className = 'msg-actions';
    const copyBtn = document.createElement('button');
    copyBtn.type = 'button';
    copyBtn.title = 'Copy';
    copyBtn.setAttribute('aria-label', 'Copy');
    copyBtn.innerHTML = ICON_COPY;
    copyBtn.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(m.text); showToast('Copied'); } catch (e) { showToast('Copy failed'); }
    });
    const up = document.createElement('button');
    up.type = 'button';
    up.title = 'Helpful';
    up.setAttribute('aria-label', 'Helpful');
    up.innerHTML = ICON_UP;
    up.addEventListener('click', () => showToast('Thanks for the feedback'));
    const down = document.createElement('button');
    down.type = 'button';
    down.title = 'Not helpful';
    down.setAttribute('aria-label', 'Not helpful');
    down.innerHTML = ICON_DOWN;
    down.addEventListener('click', () => showToast('Thanks — noted'));
    const more = document.createElement('button');
    more.type = 'button';
    more.title = 'More';
    more.setAttribute('aria-label', 'More');
    more.innerHTML = ICON_MORE;
    more.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(m.text); showToast('Copied'); } catch (e) { showToast('Copy failed'); }
    });
    actions.appendChild(copyBtn);
    actions.appendChild(up);
    actions.appendChild(down);
    actions.appendChild(more);
    col.appendChild(actions);
  } else {
    const checks = document.createElement('div');
    checks.className = 'msg-checks';
    checks.innerHTML = ICON_CHECKS;
    checks.setAttribute('aria-hidden', 'true');
    col.appendChild(checks);
  }
  row.appendChild(avatar);
  row.appendChild(col);
  log.appendChild(row);
  if (notify) pushNotify(m);
  return true;
}

function isReviewReadyMessage(m) {
  if (!m || m.direction === 'in') return false;
  const text = String(m.text || '');
  if ((m.level || '') === 'success' && /ready for your (review|approval)|waiting for your approval|Done — not stuck/i.test(text)) {
    return true;
  }
  return /ready for your review|approve and apply|Approve & apply/i.test(text)
    && /unchanged until you approve|Isolated workspace only|waiting for your approval/i.test(text);
}

const progressPanel = document.getElementById('progressPanel');
const activityDrawerBackdrop = document.getElementById('activityDrawerBackdrop');
const activityDrawerClose = document.getElementById('activityDrawerClose');
const activityHistory = document.getElementById('activityHistory');
const activityReviewActions = document.getElementById('activityReviewActions');
const activityApproveBtn = document.getElementById('activityApproveBtn');
const activityRejectBtn = document.getElementById('activityRejectBtn');
const reviewBanner = document.getElementById('reviewBanner');
const reviewBannerTitle = document.getElementById('reviewBannerTitle');
const reviewBannerHint = document.getElementById('reviewBannerHint');
const bannerApproveBtn = document.getElementById('bannerApproveBtn');
const bannerCommitApplyBtn = document.getElementById('bannerCommitApplyBtn');
const bannerPushBtn = document.getElementById('bannerPushBtn');
const bannerRejectBtn = document.getElementById('bannerRejectBtn');
const progressToggle = document.getElementById('progressToggle');
const progressMeta = document.getElementById('progressMeta');
const progressStageLabel = document.getElementById('progressStageLabel');
const progressNow = document.getElementById('progressNow');
const progressEvents = document.getElementById('progressEvents');
const progressRail = document.getElementById('progressRail');
const progressElapsed = document.getElementById('progressElapsed');
const progressLiveBadge = document.getElementById('progressLiveBadge');
const busyOpenProgress = document.getElementById('busyOpenProgress');
const PIPELINE_STEPS = [
  {key: 'queued', short: 'Queued'},
  {key: 'preparing_workspace', short: 'Workspace'},
  {key: 'agent_running', short: 'Coding'},
  {key: 'testing', short: 'Tests'},
  {key: 'ready_for_review', short: 'Review'},
];
let progressOpen = false;
let _progressStartedAt = 0;
let _progressActive = false;
let _elapsedTimer = null;
let _selectedTaskId = '';
let _renderedEventIds = new Set();
let _lastHistorySig = '';
let _recentTasksCache = [];
let _knownTaskIds = new Set();
let _inflightCount = 0;
try { progressOpen = localStorage.getItem('orch_progress_open') === '1'; } catch (e) {}
async function focusTaskOnServer(taskId) {
  if (!taskId) return;
  try {
    await fetch('/chat/focus-task', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({task_id: taskId}),
    });
  } catch (e) { /* poll will reconcile */ }
}
function applyProgressChrome() {
  if (!progressPanel) return;
  progressPanel.classList.toggle('open', progressOpen);
  progressPanel.setAttribute('aria-hidden', progressOpen ? 'false' : 'true');
  if (activityDrawerBackdrop) {
    activityDrawerBackdrop.classList.toggle('show', progressOpen);
    activityDrawerBackdrop.setAttribute('aria-hidden', progressOpen ? 'false' : 'true');
  }
  if (progressToggle) {
    progressToggle.classList.toggle('on', progressOpen);
    progressToggle.setAttribute('aria-expanded', progressOpen ? 'true' : 'false');
  }
}
function setProgressOpen(open) {
  progressOpen = !!open;
  applyProgressChrome();
  try { localStorage.setItem('orch_progress_open', progressOpen ? '1' : '0'); } catch (e) {}
  if (progressOpen) {
    if (typeof setSidebarOpen === 'function') setSidebarOpen(false);
    if (typeof closeManageDrawer === 'function') closeManageDrawer();
    refreshProgress();
  }
}
function openProgressPanel() {
  setProgressOpen(true);
}
function closeProgressPanel() {
  setProgressOpen(false);
}
applyProgressChrome();
if (progressToggle) {
  progressToggle.addEventListener('click', () => setProgressOpen(!progressOpen));
}
if (activityDrawerClose) {
  activityDrawerClose.addEventListener('click', () => closeProgressPanel());
}
const clearActivityBtn = document.getElementById('clearActivityBtn');
if (clearActivityBtn) {
  clearActivityBtn.addEventListener('click', () => doClearActivity());
}
if (activityDrawerBackdrop) {
  activityDrawerBackdrop.addEventListener('click', () => closeProgressPanel());
}
if (busyOpenProgress) {
  busyOpenProgress.addEventListener('click', () => openProgressPanel());
}
function wireApproveReject(btn, phrase) {
  if (!btn) return;
  btn.addEventListener('click', () => send(phrase));
}
wireApproveReject(activityApproveBtn, 'approve and apply');
wireApproveReject(activityRejectBtn, 'reject that');
wireApproveReject(bannerApproveBtn, 'approve and apply');
wireApproveReject(bannerCommitApplyBtn, 'commit local and apply');
wireApproveReject(bannerPushBtn, 'approve and push');
wireApproveReject(bannerRejectBtn, 'reject that');
function formatElapsed(sec) {
  sec = Math.max(0, Math.floor(sec || 0));
  if (sec < 60) return sec + 's';
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (m < 60) return m + 'm ' + String(s).padStart(2, '0') + 's';
  const h = Math.floor(m / 60);
  return h + 'h ' + (m % 60) + 'm';
}
function tickElapsed() {
  if (!_progressStartedAt || !progressElapsed) return;
  const sec = (Date.now() / 1000) - _progressStartedAt;
  progressElapsed.textContent = formatElapsed(sec);
  progressElapsed.hidden = false;
}
function setElapsedClock(startedAt, active) {
  _progressStartedAt = startedAt ? Number(startedAt) : 0;
  _progressActive = !!active && !!_progressStartedAt;
  if (_elapsedTimer) { clearInterval(_elapsedTimer); _elapsedTimer = null; }
  if (_progressActive) {
    tickElapsed();
    _elapsedTimer = setInterval(tickElapsed, 1000);
  } else if (progressElapsed) {
    if (_progressStartedAt) tickElapsed();
    else {
      progressElapsed.hidden = true;
      progressElapsed.textContent = '';
    }
  }
}
function pipelineKey(stage) {
  if (!stage) return 'queued';
  if (stage === 'investigating' || stage === 'implementing') return 'agent_running';
  return stage;
}
function renderRail(stage, status) {
  if (!progressRail) return;
  const key = status === 'review' || status === 'publishing' || status === 'published'
    ? 'ready_for_review'
    : pipelineKey(stage);
  const idx = Math.max(0, PIPELINE_STEPS.findIndex(s => s.key === key));
  const next = PIPELINE_STEPS.map((step, i) =>
    '<span class="work-rail-seg' + (i < idx ? ' done' : (i === idx ? ' current' : '')) + '" title="' + step.short + '"></span>'
  ).join('');
  if (progressRail.dataset.sig === String(idx)) return;
  progressRail.dataset.sig = String(idx);
  progressRail.innerHTML = next;
}
function shortPath(raw) {
  if (!raw) return '';
  let p = String(raw).replace(/\\/g, '/');
  const marker = '/workspaces/';
  const wi = p.toLowerCase().indexOf(marker);
  if (wi >= 0) {
    const rest = p.slice(wi + marker.length);
    const slash = rest.indexOf('/');
    p = slash >= 0 ? rest.slice(slash + 1) : rest;
  }
  for (const tip of ['/app/', '/resources/', '/tests/', '/config/', '/public/', '/src/']) {
    const i = p.toLowerCase().indexOf(tip);
    if (i >= 0) { p = p.slice(i + 1); break; }
  }
  const parts = p.split('/').filter(Boolean);
  if (parts.length > 3) p = parts.slice(-3).join('/');
  return p;
}
function formatActivity(msg) {
  const text = String(msg || '').trim();
  if (!text) return {label: 'Activity', path: '', write: false};
  const m = text.match(/^(?:Write:\\s*)?(?:Read:\\s*)?(Write|Edit|Read|Grep|Glob|Shell|Delete|Tool)(?:\\s*:\\s*|\\s+)?(?:->\\s*)?(.*)$/i)
    || text.match(/^(Write|Edit|Read|Grep|Glob|Shell|Delete)\\s+(.+)$/i);
  if (m) {
    const tool = m[1].charAt(0).toUpperCase() + m[1].slice(1).toLowerCase();
    const path = shortPath((m[2] || '').trim());
    const write = /write|edit|delete/i.test(tool);
    return {label: tool, path, write};
  }
  if (/^Agent:/i.test(text)) {
    return {label: 'Agent', path: text.replace(/^Agent:\\s*/i, '').slice(0, 80), write: false};
  }
  return {label: '', path: shortPath(text) || text.slice(0, 90), write: /\\b(write|edit|delete)/i.test(text)};
}
function renderActivityLine(parsed) {
  if (parsed.label && parsed.path) {
    return parsed.label + ' · <code>' + escapeHtml(parsed.path) + '</code>';
  }
  if (parsed.path) return '<code>' + escapeHtml(parsed.path) + '</code>';
  return escapeHtml(parsed.label || 'Activity');
}
function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

let _lastProgressSig = '';
function setIdleCurrentActivity() {
  _renderedEventIds = new Set();
  _lastProgressSig = '';
  if (progressStageLabel) progressStageLabel.textContent = 'No active task';
  if (progressNow) progressNow.textContent = 'Start a coding task to see live progress';
  if (progressMeta) progressMeta.textContent = '';
  if (progressEvents) {
    progressEvents.innerHTML = '<li class="work-feed-item empty">No activity yet</li>';
  }
  if (progressRail) {
    progressRail.innerHTML = '';
    delete progressRail.dataset.sig;
  }
  if (progressPanel) {
    progressPanel.classList.add('idle');
    progressPanel.classList.remove('needs-review');
  }
  if (progressLiveBadge) progressLiveBadge.hidden = true;
  if (activityReviewActions) activityReviewActions.hidden = true;
  setReviewBanner(false);
  setElapsedClock(0, false);
}
function resetProgressPanel() {
  _selectedTaskId = '';
  _recentTasksCache = [];
  _knownTaskIds = new Set();
  _inflightCount = 0;
  _lastHistorySig = '';
  setIdleCurrentActivity();
  if (progressToggle) progressToggle.classList.remove('working');
  if (activityHistory) {
    activityHistory.innerHTML = '<div class="activity-history-empty">No task history yet</div>';
  }
}
function statusLabel(status, stage) {
  if (status === 'review') return 'Ready for review';
  if (status === 'running' || status === 'queued' || status === 'publishing') return 'In progress';
  if (status === 'published') return 'Published';
  if (status === 'rejected') return 'Rejected';
  if (stage === 'canceled' || status === 'failed') return 'Cancelled';
  return status || 'Task';
}
function isClearedActivityTask(t) {
  if (!t || !t.id) return true;
  const stage = String(t.execution_stage || '').toLowerCase();
  const blocker = String(t.blocker || '').toLowerCase();
  const summary = String(t.summary || '').toLowerCase();
  if (stage === 'canceled') return true;
  if (blocker.includes('cleared') || summary.includes('cleared:')) return true;
  return false;
}
function renderActivityHistory(tasks, activeId) {
  if (!activityHistory) return;
  const rows = (tasks || []).filter(t => !isClearedActivityTask(t));
  const sig = rows.map(t => t.id + ':' + t.status + ':' + (t.execution_stage || '')).join('|') + '|' + (activeId || '');
  if (sig === _lastHistorySig) return;
  _lastHistorySig = sig;
  if (!rows.length) {
    activityHistory.innerHTML = '<div class="activity-history-empty">No task history yet</div>';
    return;
  }
  activityHistory.innerHTML = '';
  rows.forEach((t) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'activity-history-item' + (t.id === activeId ? ' active' : '');
    btn.dataset.taskId = t.id;
    const live = t.status === 'queued' || t.status === 'running' || t.status === 'publishing';
    btn.innerHTML =
      '<span class="activity-history-main">'
      + '<strong>' + escapeHtml(t.project || 'task') + '</strong>'
      + '<span>' + escapeHtml(statusLabel(t.status, t.execution_stage)) + '</span>'
      + '</span>'
      + '<span class="activity-history-id">' + escapeHtml(String(t.id).slice(0, 8))
      + (live ? ' · live' : '') + '</span>';
    btn.addEventListener('click', async () => {
      _selectedTaskId = t.id;
      _renderedEventIds = new Set();
      _lastProgressSig = '';
      await focusTaskOnServer(t.id);
      refreshProgress();
    });
    activityHistory.appendChild(btn);
  });
}
function appendFeedItems(evs, {replace}) {
  if (!progressEvents) return;
  if (replace) {
    progressEvents.innerHTML = '';
    _renderedEventIds = new Set();
  }
  if (!evs.length) {
    if (!progressEvents.children.length) {
      progressEvents.innerHTML = '<li class="work-feed-item empty">Waiting for tool activity…</li>';
    }
    return;
  }
  const empty = progressEvents.querySelector('.work-feed-item.empty');
  if (empty) empty.remove();
  const nearBottom = (progressEvents.scrollHeight - progressEvents.scrollTop - progressEvents.clientHeight) < 48;
  let added = 0;
  evs.forEach((ev, i) => {
    const eid = String(ev.id != null ? ev.id : (ev.ts + ':' + (ev.message || '') + ':' + i));
    if (_renderedEventIds.has(eid)) return;
    _renderedEventIds.add(eid);
    progressEvents.querySelectorAll('.work-feed-item.fresh').forEach((n) => n.classList.remove('fresh'));
    const parsed = formatActivity(ev.message || ev.event_type || '');
    const li = document.createElement('li');
    const isLast = i === evs.length - 1;
    // Only animate newly streamed lines — full rebuilds stay still (no jerk).
    li.className = 'work-feed-item'
      + (parsed.write ? ' write' : '')
      + ((!replace || isLast) ? ' fresh' : '');
    li.dataset.eid = eid;
    li.innerHTML = '<span class="work-feed-mark" aria-hidden="true"></span><span>' + renderActivityLine(parsed) + '</span>';
    progressEvents.appendChild(li);
    added += 1;
  });
  if (added && (replace || nearBottom)) {
    progressEvents.scrollTop = progressEvents.scrollHeight;
  }
}
async function refreshProgress() {
  try {
    const q = _selectedTaskId ? ('?task_id=' + encodeURIComponent(_selectedTaskId)) : '';
    const r = await fetch('/chat/task-progress' + q, {cache: 'no-store'});
    if (r.status === 401) { location.reload(); return; }
    if (!r.ok) { noteTransportFail(); return; }
    noteTransportOk();
    const j = await r.json();
    const t = j.task;
    renderActivityHistory(_recentTasksCache, t ? t.task_id : _selectedTaskId);
    if (!t) {
      if (activityReviewActions) activityReviewActions.hidden = true;
      if (progressPanel) progressPanel.classList.remove('needs-review');
      if (!_selectedTaskId) {
        setIdleCurrentActivity();
        renderActivityHistory(_recentTasksCache, '');
      } else {
        if (progressStageLabel) progressStageLabel.textContent = 'Task unavailable';
        if (progressNow) progressNow.textContent = 'This task has no progress to show';
        appendFeedItems([], {replace: true});
        if (progressPanel) progressPanel.classList.add('idle');
        if (progressLiveBadge) progressLiveBadge.hidden = true;
        setElapsedClock(0, false);
      }
      return;
    }
    if (!_selectedTaskId) _selectedTaskId = t.task_id || '';
    const evs = (j.events && j.events.length) ? j.events : (t.events || []);
    const stream = evs.filter(e =>
      (e.event_type || '') === 'agent_stream'
      || /^(Read|Write|Edit|Grep|Glob|Shell|Agent|Cancel)/i.test(e.message || '')
    );
    const feed = stream.length ? stream : evs;
    const label = t.current_label || t.execution_stage || 'Working';
    const active = t.status === 'queued' || t.status === 'running' || t.status === 'publishing';
    const needsReview = t.status === 'review';
    const latestMsg = feed.length ? (feed[feed.length - 1].message || '') : '';
    const headSig = [t.task_id, t.status, t.execution_stage, label, latestMsg, _inflightCount].join('|');
    const taskChanged = _lastProgressSig.split('|')[0] !== String(t.task_id || '');
    progressPanel.classList.toggle('idle', !active && !needsReview);
    progressPanel.classList.toggle('needs-review', needsReview);
    if (progressLiveBadge) {
      progressLiveBadge.hidden = !active && !needsReview;
      if (needsReview) progressLiveBadge.innerHTML = '<span class="work-live-dot" aria-hidden="true"></span>Review';
      else if (active) progressLiveBadge.innerHTML = '<span class="work-live-dot" aria-hidden="true"></span>Live';
    }
    if (activityReviewActions) activityReviewActions.hidden = !needsReview;
    setElapsedClock(t.started_at, active);
    if (headSig !== _lastProgressSig) {
      _lastProgressSig = headSig;
      progressStageLabel.textContent = needsReview
        ? 'Ready for your approval'
        : label;
      const latest = formatActivity(latestMsg || stageHint(t.execution_stage, t.status));
      progressNow.innerHTML = needsReview
        ? 'Coding finished — tap Approve &amp; apply below (project folder unchanged until then).'
        : (latest.path
          ? (latest.label ? (escapeHtml(latest.label) + ' · <code>' + escapeHtml(latest.path) + '</code>') : ('<code>' + escapeHtml(latest.path) + '</code>'))
          : escapeHtml(latest.label || stageHint(t.execution_stage, t.status)));
      if (progressMeta) {
        let meta = (t.project || '') + (t.task_id ? (' · ' + t.task_id) : '');
        if (_inflightCount > 1) meta += ' · ' + _inflightCount + ' live';
        if (needsReview) meta += ' · awaiting approval';
        progressMeta.textContent = meta;
      }
      renderRail(t.execution_stage, t.status);
    }
    appendFeedItems(feed, {replace: taskChanged});
  } catch (e) { noteTransportFail(); }
}
function setReviewBanner(on, mode) {
  if (!reviewBanner) return;
  reviewBanner.hidden = !on;
  if (!on) return;
  const dirty = mode === 'dirty';
  if (reviewBannerTitle) {
    reviewBannerTitle.textContent = dirty
      ? 'Apply blocked — local changes'
      : 'Ready for your approval';
  }
  if (reviewBannerHint) {
    reviewBannerHint.textContent = dirty
      ? 'Commit or stash laptop WIP, then apply/push the review branch.'
      : 'Not stuck — coding finished. Apply, push, or reject.';
  }
  if (bannerCommitApplyBtn) bannerCommitApplyBtn.hidden = !dirty;
  if (bannerApproveBtn) bannerApproveBtn.hidden = false;
  if (bannerPushBtn) bannerPushBtn.hidden = false;
}
function stageHint(stage, status) {
  if (status === 'review') return 'Ready for your review';
  if (stage === 'investigating') return 'Reading and searching files';
  if (stage === 'implementing') return 'Writing and editing files';
  if (stage === 'preparing_workspace') return 'Preparing isolated workspace';
  if (stage === 'testing') return 'Running tests';
  if (stage === 'agent_running') return 'Cursor agent is running';
  if (stage === 'queued') return 'Queued for a worker';
  return 'Working…';
}

async function refreshStatus() {
  try {
    const r = await fetch('/chat/status', {cache: 'no-store'});
    if (r.status === 401) { location.reload(); return; }
    if (!r.ok) {
      noteTransportFail();
      return;
    }
    noteTransportOk();
    const j = await r.json();
    const mode = j.dry_run ? 'DRY RUN' : 'LIVE';
    const agent = j.agent_ok ? 'agent ok' : 'agent missing';
    const chat = j.groq_chat ? 'smart chat' : 'basic chat';
    const jobs = j.pending_jobs ? (', ' + j.pending_jobs + ' queued') : '';
    const proj = j.active_project ? (' · ' + j.active_project) : '';
    setPill(j.agent_ok ? 'live' : 'off');
    pillText.textContent = mode + ' · ' + agent + ' · ' + chat + ' · ' + j.projects + ' projects' + jobs + proj;
    document.getElementById('statusProjects').textContent = j.projects + ' projects active';
    document.getElementById('statusDetail').textContent = j.agent_ok
      ? ('Agent ready · All systems ok')
      : ('Agent issue · check laptop');
    const ring = document.getElementById('statusRing');
    if (ring) ring.style.strokeDashoffset = j.agent_ok ? '18' : '70';
    if (Array.isArray(j.inflight_projects)) {
      inflightProjects = new Set(j.inflight_projects);
    } else {
      inflightProjects = new Set(
        (j.recent_tasks || [])
          .filter(t => t.status === 'queued' || t.status === 'running' || t.status === 'publishing')
          .map(t => t.project)
          .filter(Boolean)
      );
    }
    if (Array.isArray(j.project_list)) {
      allProjects = j.project_list;
    }
    if (j.projects_root) {
      applyProjectsRootInfo(j.projects_root);
    }
    if ('active_project' in j) {
      activeProject = j.active_project || '';
    }
    renderProjects(projectSearch.value);
    // Busy / progress are for the chat you are viewing — other projects keep working silently.
    const scopedRecent = (j.recent_tasks || []).filter(t =>
      !activeProject || t.project === activeProject
    );
    const nextCache = scopedRecent.filter(t => !isClearedActivityTask(t));
    const liveScoped = nextCache.filter(t =>
      t.status === 'queued' || t.status === 'running' || t.status === 'publishing'
    );
    const reviewScoped = nextCache.filter(t => t.status === 'review');
    const publishFailedScoped = nextCache.filter(t => t.status === 'publish_failed');
    _inflightCount = (typeof j.inflight_count === 'number')
      ? j.inflight_count
      : liveScoped.length;
    // Prefer selected task for the approval banner; else newest review / failed publish.
    let reviewTask = null;
    if (_selectedTaskId) {
      reviewTask = reviewScoped.find(t => t.id === _selectedTaskId)
        || publishFailedScoped.find(t => t.id === _selectedTaskId)
        || null;
    }
    if (!reviewTask && reviewScoped.length) reviewTask = reviewScoped[0];
    if (!reviewTask && publishFailedScoped.length) reviewTask = publishFailedScoped[0];
    const dirtyBlock = !!(reviewTask && reviewTask.status === 'publish_failed'
      && /uncommitted changes/i.test(String(reviewTask.summary || reviewTask.blocker || '')));
    setReviewBanner(!!reviewTask && !liveScoped.length, dirtyBlock ? 'dirty' : 'review');
    // Auto-focus a newly created live task (Cursor focuses the agent you just started).
    const seenBefore = _knownTaskIds.size > 0;
    for (const t of nextCache) {
      if (!_knownTaskIds.has(t.id)) {
        const isLive = t.status === 'queued' || t.status === 'running' || t.status === 'publishing';
        if (seenBefore && isLive) {
          _selectedTaskId = t.id;
          _renderedEventIds = new Set();
          _lastProgressSig = '';
          focusTaskOnServer(t.id);
        }
        _knownTaskIds.add(t.id);
      }
    }
    // Drop selection only if the selected task disappeared from this project's history.
    if (_selectedTaskId && !nextCache.some(t => t.id === _selectedTaskId)) {
      _selectedTaskId = '';
    }
    _recentTasksCache = nextCache;
    const projectActive = liveScoped.length > 0;
    const otherWorking = [...inflightProjects].some(p => p !== activeProject);
    busy.classList.toggle('on', projectActive || sending);
    if (progressToggle) progressToggle.classList.toggle('working', projectActive || otherWorking);
    const stage = (j.active_task && j.active_task.execution_stage) || '';
    const stageNice = stage ? stage.replace(/_/g, ' ') : '';
    const busyEl = document.getElementById('busyText');
    if (sending && !projectActive) {
      busyEl.textContent = 'Sending your message…';
    } else if (projectActive && _inflightCount > 1) {
      busyEl.textContent = _inflightCount + ' agents working — open Activity to switch';
    } else if (projectActive) {
      busyEl.textContent = stageNice
        ? ('Agent working — ' + stageNice)
        : 'Agent working on your task…';
    } else if (reviewTask) {
      busyEl.textContent = 'Ready for approval — Approve & apply when it looks good';
    } else {
      busyEl.textContent = 'Working on your request…';
    }
    // Do not auto-open the drawer (that jerks the UI). Refresh quietly while open or working.
    if (progressOpen || projectActive || reviewTask) {
      await refreshProgress();
    } else {
      renderActivityHistory(_recentTasksCache, _selectedTaskId);
    }
  } catch (e) {
    noteTransportFail();
  }
}

function resetLog() {
  last = 0;
  bootstrapped = false;
  seenMsgIds.clear();
  log.innerHTML = '';
  const e = document.createElement('div');
  e.className = EMPTY;
  e.id = 'empty';
  e.innerHTML = '<strong class="' + EMPTY_TITLE + '">Loading</strong>Fetching your conversation...';
  log.appendChild(e);
}

async function poll() {
  if (pollBusy) return;
  pollBusy = true;
  try {
    const projQ = activeProject ? ('&project=' + encodeURIComponent(activeProject)) : '';
    const r = await fetch('/chat/messages?after=' + last + projQ, {cache: 'no-store'});
    if (r.status === 401) { location.reload(); return; }
    if (!r.ok) { noteTransportFail(); return; }
    noteTransportOk();
    const j = await r.json();
    // If server active project diverged (e.g. chat said "work on X"), reload thread.
    const serverProj = j.active_project || '';
    if (serverProj !== (activeProject || '')) {
      activeProject = serverProj;
      renderProjects(projectSearch.value);
      resetLog();
      const fullQ = activeProject
        ? ('&project=' + encodeURIComponent(activeProject))
        : '';
      const full = await fetch('/chat/messages?after=0' + fullQ, {cache: 'no-store'});
      const fj = await full.json();
      for (const m of (fj.messages || [])) {
        add(m, {notify: false});
        if (m.id > last) last = m.id;
      }
      bootstrapped = true;
      if (!last) {
        const emptyEl = document.getElementById('empty');
        if (emptyEl) {
          emptyEl.innerHTML = activeProject
            ? ('<strong class="' + EMPTY_TITLE + '">' + activeProject + '</strong>Fresh chat for this project. What should I change?')
            : ('<strong class="' + EMPTY_TITLE + '">Hi</strong>What can I help you with?');
        }
      }
      log.scrollTop = log.scrollHeight;
      syncJump();
      return;
    }
    const stick = nearBottom();
    const notifyNew = bootstrapped;
    const emptyEl = document.getElementById('empty');
    let added = 0;
    for (const m of j.messages) {
      if (add(m, {notify: notifyNew})) added += 1;
      if (m.id > last) last = m.id;
    }
    bootstrapped = true;
    if (added && stick) log.scrollTop = log.scrollHeight;
    if (!last && emptyEl) {
      emptyEl.innerHTML = activeProject
        ? ('<strong class="' + EMPTY_TITLE + '">' + activeProject + '</strong>Fresh chat for this project. What should I change?')
        : ('<strong class="' + EMPTY_TITLE + '">Hi</strong>What can I help you with?');
    }
    syncJump();
  } catch (e) { noteTransportFail(); }
  finally { pollBusy = false; }
}

function autoSize() {
  txt.style.height = 'auto';
  txt.style.height = Math.min(txt.scrollHeight, 96) + 'px';
}

async function send(text) {
  text = text.trim();
  if (!text || sending) return;
  sending = true;
  sendBtn.disabled = true;
  busy.classList.add('on');
  txt.value = '';
  autoSize();
  try {
    const r = await fetch('/chat/send', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text, cid: crypto.randomUUID()})});
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      showToast(j.error || ('Send failed: ' + r.status));
    }
    await poll();
    await refreshStatus();
    log.scrollTop = log.scrollHeight;
  } finally {
    sending = false;
    sendBtn.disabled = false;
    busy.classList.remove('on');
    txt.focus();
  }
}

async function doClearChat() {
  const ok = await askConfirm(
    'This clears the chat and deletes isolated workspaces for this project so the next run starts fresh. You can’t undo it.',
    {
      title: 'Clear chat & workspaces?',
      okLabel: 'Clear everything',
      danger: true,
    }
  );
  if (!ok) return;
  // Pin the project we are clearing so a later status/poll cannot jump chats.
  const stayOn = activeProject || '';
  const r = await fetch('/chat/clear', {method: 'POST'});
  if (r.status === 401) { location.reload(); return; }
  if (!r.ok) { showToast('Clear failed'); return; }
  let detail = 'Chat cleared';
  try {
    const j = await r.json();
    if (j && (j.removed || j.canceled)) {
      detail = 'Chat cleared · ' + (j.removed || 0) + ' workspace(s) removed'
        + (j.canceled ? (', ' + j.canceled + ' task(s) cancelled') : '');
    }
  } catch (e) {}
  activeProject = stayOn;
  resetLog();
  resetProgressPanel();
  try {
    const projQ = stayOn ? ('&project=' + encodeURIComponent(stayOn)) : '';
    const full = await fetch('/chat/messages?after=0' + projQ, {cache: 'no-store'});
    if (full.ok) {
      const fj = await full.json();
      for (const m of (fj.messages || [])) {
        add(m, {notify: false});
        if (m.id > last) last = m.id;
      }
      bootstrapped = true;
      if (!last) {
        const emptyEl = document.getElementById('empty');
        if (emptyEl) {
          emptyEl.innerHTML = stayOn
            ? ('<strong class="' + EMPTY_TITLE + '">' + stayOn + '</strong>Fresh chat for this project. What should I change?')
            : ('<strong class="' + EMPTY_TITLE + '">Hi</strong>What can I help you with?');
        }
      }
    }
  } catch (e) {}
  await refreshStatus();
  showToast(detail);
}

async function doClearActivity() {
  const ok = await askConfirm(
    'This clears activity history and cancels any in-progress work for this project. Chat messages stay. You can’t undo it.',
    {
      title: 'Clear all activity?',
      okLabel: 'Clear activity',
      danger: true,
    }
  );
  if (!ok) return;
  const r = await fetch('/chat/clear-activity', {method: 'POST'});
  if (r.status === 401) { location.reload(); return; }
  if (!r.ok) { showToast('Could not clear activity'); return; }
  let detail = 'Activity cleared';
  try {
    const j = await r.json();
    if (j && (j.removed || j.canceled)) {
      detail = 'Activity cleared'
        + (j.canceled ? (' · ' + j.canceled + ' task(s) cancelled') : '')
        + (j.removed ? (', ' + j.removed + ' workspace(s) removed') : '');
    }
  } catch (e) {}
  resetProgressPanel();
  // Force history empty before status poll can repaint stale rows.
  _recentTasksCache = [];
  _lastHistorySig = '';
  renderActivityHistory([], '');
  await refreshStatus();
  showToast(detail);
}

async function doLogout() {
  const ok = await askConfirm('You’ll need your password to sign back in on this device.', {
    title: 'Log out?',
    okLabel: 'Log out',
    danger: true,
  });
  if (!ok) return;
  await fetch('/chat/logout', {method: 'POST'});
  location.reload();
}

document.getElementById('f').addEventListener('submit', (e) => { e.preventDefault(); send(txt.value); });
txt.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(txt.value); }
});
txt.addEventListener('input', autoSize);
log.addEventListener('scroll', syncJump);
jump.addEventListener('click', () => { log.scrollTop = log.scrollHeight; syncJump(); });
document.getElementById('quick').addEventListener('click', (e) => {
  const b = e.target.closest('button');
  if (!b) return;
  if (b.dataset.send) { send(b.dataset.send); return; }
  txt.value = b.dataset.fill;
  txt.focus();
  autoSize();
});
menuBtn.addEventListener('click', () => toggleSidebar());
sidebarCloseBtn.addEventListener('click', () => closeSidebar());
sidebarBackdrop.addEventListener('click', () => setSidebarOpen(false));
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape' || confirmResolver) return;
  if (folderPickerModal && !folderPickerModal.hidden) return;
  if (isManageDrawerOpen()) return;
  if (!isDesktopSidebar() && sidebar.classList.contains('open')) {
    e.preventDefault();
    setSidebarOpen(false);
  }
});
document.getElementById('projectsToggle').addEventListener('click', () => {
  const open = projectList.style.display !== 'none';
  projectList.style.display = open ? 'none' : '';
  document.getElementById('projectsChevron').style.transform = open ? 'rotate(-90deg)' : '';
  document.getElementById('projectsToggle').setAttribute('aria-expanded', open ? 'false' : 'true');
});

function isManageDrawerOpen() {
  return !!(manageDrawer && manageDrawer.classList.contains('open'));
}

function setManageDrawerOpen(open) {
  if (!manageDrawer || !manageDrawerBackdrop) return;
  const show = !!open;
  manageDrawer.classList.toggle('open', show);
  manageDrawerBackdrop.classList.toggle('show', show);
  manageDrawer.setAttribute('aria-hidden', show ? 'false' : 'true');
  manageDrawerBackdrop.setAttribute('aria-hidden', show ? 'false' : 'true');
  if (projectsManageToggle) {
    projectsManageToggle.classList.toggle('active', show);
    projectsManageToggle.setAttribute('aria-expanded', show ? 'true' : 'false');
  }
  if (show) {
    // Give Manage its own left drawer; tuck the workspace sidebar away on mobile.
    setSidebarOpen(false);
    if (typeof closeProgressPanel === 'function') closeProgressPanel();
    renderManageRegistry();
  }
}

function closeManageDrawer() {
  setManageDrawerOpen(false);
}

projectsManageToggle.addEventListener('click', () => {
  setManageDrawerOpen(!isManageDrawerOpen());
});
document.getElementById('manageDrawerClose').addEventListener('click', () => closeManageDrawer());
document.getElementById('manageDrawerDone').addEventListener('click', () => closeManageDrawer());
manageDrawerBackdrop.addEventListener('click', () => closeManageDrawer());
document.getElementById('projectsScanBtn').addEventListener('click', () => scanProjectFolders());
document.getElementById('projectsChooseFolderBtn').addEventListener('click', () => openFolderPicker());
document.getElementById('projectsRootSaveBtn').addEventListener('click', () => saveProjectsRoot());
document.getElementById('folderPickerSelect').addEventListener('click', () => selectFolderFromPicker());
document.getElementById('folderPickerUp').addEventListener('click', () => {
  if (folderPickerParent === '') loadFolderPicker('');
  else if (folderPickerParent) loadFolderPicker(folderPickerParent);
});
if (folderPickerModal) {
  folderPickerModal.querySelectorAll('[data-folder-cancel]').forEach((el) => {
    el.addEventListener('click', () => closeFolderPicker());
  });
}
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  if (folderPickerModal && !folderPickerModal.hidden) {
    e.preventDefault();
    closeFolderPicker();
    return;
  }
  if (isManageDrawerOpen()) {
    e.preventDefault();
    closeManageDrawer();
    return;
  }
  if (progressOpen) {
    e.preventDefault();
    closeProgressPanel();
  }
});
if (projectsRootInput) {
  projectsRootInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      saveProjectsRoot();
    }
  });
}
projectSearch.addEventListener('input', () => renderProjects(projectSearch.value));
document.getElementById('newChat').addEventListener('click', () => { setSidebarOpen(false); doClearChat(); });
document.getElementById('attachBtn').addEventListener('click', () => showToast('Attachments coming soon'));
(function setupVoiceInput() {
  const micBtn = document.getElementById('micBtn');
  if (!micBtn) return;

  let mediaStream = null;
  let mediaRecorder = null;
  let chunks = [];
  let recording = false;
  let stopping = false;
  let voiceBusy = false;
  let maxTimer = null;
  let voiceAvailable = null; // null=unknown, bool after /chat/status

  function pickMime() {
    const candidates = [
      'audio/mp4',
      'audio/aac',
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus',
    ];
    if (!window.MediaRecorder) return '';
    for (const t of candidates) {
      try { if (MediaRecorder.isTypeSupported(t)) return t; } catch (e) {}
    }
    return '';
  }

  function setRecording(on) {
    recording = on;
    micBtn.classList.toggle('listening', on);
    micBtn.setAttribute('aria-pressed', on ? 'true' : 'false');
    micBtn.title = on ? 'Stop & send' : 'Voice';
  }

  function cleanupStream() {
    if (maxTimer) { clearTimeout(maxTimer); maxTimer = null; }
    if (mediaStream) {
      try { mediaStream.getTracks().forEach((t) => t.stop()); } catch (e) {}
      mediaStream = null;
    }
    mediaRecorder = null;
    chunks = [];
  }

  function focusComposerHint() {
    try { txt.focus(); } catch (e) {}
    try { txt.setSelectionRange(txt.value.length, txt.value.length); } catch (e) {}
    showToast('Allow microphone, or use the mic on your keyboard', 4000);
  }

  async function refreshVoiceFlag() {
    try {
      const r = await fetch('/chat/status', {cache: 'no-store'});
      if (r.ok) {
        const j = await r.json();
        voiceAvailable = !!j.voice;
      }
    } catch (e) {}
  }

  async function transcribeBlob(blob, mime) {
    const fd = new FormData();
    const ext = (mime || '').includes('mp4') || (mime || '').includes('aac') ? 'm4a'
      : (mime || '').includes('ogg') ? 'ogg'
      : (mime || '').includes('webm') ? 'webm' : 'm4a';
    fd.append('audio', blob, 'voice.' + ext);
    const r = await fetch('/chat/voice', {method: 'POST', body: fd});
    if (r.status === 401) { location.reload(); return null; }
    const j = await r.json().catch(() => ({}));
    if (!r.ok) {
      showToast(j.error || ('Voice failed: ' + r.status), 4000);
      return null;
    }
    return (j.text || '').trim();
  }

  async function stopAndSend() {
    if (!mediaRecorder || stopping) return;
    stopping = true;
    showToast('Transcribing…', 5000);
    await new Promise((resolve) => {
      mediaRecorder.addEventListener('stop', resolve, {once: true});
      try { mediaRecorder.stop(); } catch (e) { resolve(); }
    });
    const mime = mediaRecorder.mimeType || pickMime() || 'audio/mp4';
    const blob = new Blob(chunks, {type: mime});
    cleanupStream();
    setRecording(false);
    stopping = false;
    if (!blob.size) {
      showToast('No audio captured — try again');
      return;
    }
    voiceBusy = true;
    micBtn.disabled = true;
    try {
      const text = await transcribeBlob(blob, mime);
      if (text) {
        txt.value = text;
        autoSize();
        await send(text);
      }
    } finally {
      voiceBusy = false;
      micBtn.disabled = false;
    }
  }

  async function startRecording() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      focusComposerHint();
      return;
    }
    if (!window.MediaRecorder) {
      focusComposerHint();
      return;
    }
    if (voiceAvailable === false) {
      showToast('Voice needs GROQ_API_KEY on the server', 4000);
      focusComposerHint();
      return;
    }
    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {echoCancellation: true, noiseSuppression: true},
      });
    } catch (e) {
      showToast('Microphone permission denied — enable it in Safari settings', 4500);
      focusComposerHint();
      return;
    }
    chunks = [];
    const mime = pickMime();
    try {
      mediaRecorder = mime
        ? new MediaRecorder(mediaStream, {mimeType: mime})
        : new MediaRecorder(mediaStream);
    } catch (e) {
      cleanupStream();
      showToast('Recording not supported in this browser', 4000);
      focusComposerHint();
      return;
    }
    mediaRecorder.ondataavailable = (ev) => {
      if (ev.data && ev.data.size) chunks.push(ev.data);
    };
    mediaRecorder.onerror = () => {
      cleanupStream();
      setRecording(false);
      showToast('Recording error — try again');
    };
    try {
      mediaRecorder.start(250);
    } catch (e) {
      cleanupStream();
      setRecording(false);
      showToast('Could not start recording');
      return;
    }
    setRecording(true);
    showToast('Listening… tap mic again to send', 4000);
    maxTimer = setTimeout(() => {
      if (recording) stopAndSend();
    }, 55000);
  }

  let lastTapAt = 0;
  async function onMicTap(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    const now = Date.now();
    if (now - lastTapAt < 450) return; // ignore click+pointerup double fire on iOS
    lastTapAt = now;
    if (voiceBusy || sending) return;
    if (voiceAvailable === null) await refreshVoiceFlag();
    if (recording) {
      await stopAndSend();
      return;
    }
    await startRecording();
  }

  micBtn.addEventListener('click', onMicTap);
  micBtn.addEventListener('touchend', (e) => {
    // Prefer touchend on iOS so the gesture isn't lost; debounce skips the follow-up click.
    onMicTap(e);
  }, {passive: false});
  refreshVoiceFlag();
})();
document.getElementById('popout').addEventListener('click', () => window.open(location.href, '_blank', 'noopener'));
document.getElementById('avatarBtn').addEventListener('click', doLogout);
document.getElementById('refresh').addEventListener('click', async () => {
  resetLog();
  await refreshStatus();
  await poll();
  showToast('Chat reloaded');
});
document.getElementById('clearChat').addEventListener('click', doClearChat);
notifyBtn.addEventListener('click', enableNotifications);
syncNotifyBtn();

let fitTimer = null;
function fitViewport() {
  const vv = window.visualViewport;
  let h = window.innerHeight;
  let top = 0;
  if (vv) {
    h = vv.height;
    top = vv.offsetTop || 0;
  }
  h = Math.max(240, Math.round(h));
  top = Math.max(0, Math.round(top));
  document.documentElement.style.setProperty('--app-height', h + 'px');
  document.documentElement.style.setProperty('--app-top', top + 'px');
  const focused = document.activeElement === txt;
  const kb = focused || (vv ? (window.innerHeight - vv.height > 60) : false);
  document.body.classList.toggle('kb-open', kb);
  if (window.scrollY || document.documentElement.scrollTop) window.scrollTo(0, 0);
}
function scheduleFit(scrollLog) {
  clearTimeout(fitTimer);
  fitViewport();
  fitTimer = setTimeout(() => {
    fitViewport();
    if (scrollLog || nearBottom()) log.scrollTop = log.scrollHeight;
  }, 80);
  setTimeout(fitViewport, 280);
}
fitViewport();
window.addEventListener('resize', () => scheduleFit(false));
window.addEventListener('orientationchange', () => scheduleFit(true));
if (window.visualViewport) {
  window.visualViewport.addEventListener('resize', () => scheduleFit(false));
  window.visualViewport.addEventListener('scroll', () => {
    fitViewport();
    window.scrollTo(0, 0);
  });
}
txt.addEventListener('focus', () => scheduleFit(true));
txt.addEventListener('blur', () => setTimeout(() => { fitViewport(); }, 120));
document.addEventListener('touchmove', (e) => {
  if (!e.target.closest('#log, #quick, #projectList, #sidebar, #manageDrawer, #progressPanel, #activityHistory, #folderPickerModal, textarea, input')) e.preventDefault();
}, {passive: false});

const installBanner = document.getElementById('installBanner');
const isStandalone = window.matchMedia('(display-mode: standalone)').matches
  || window.navigator.standalone === true;
if (!isStandalone && !localStorage.getItem('orch_hide_install')) {
  installBanner.classList.add('show');
}
document.getElementById('dismissInstall').addEventListener('click', () => {
  localStorage.setItem('orch_hide_install', '1');
  installBanner.classList.remove('show');
});

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/chat/sw.js', {scope: '/chat/'}).catch(() => {});
}

function schedulePoll() {
  setTimeout(async () => {
    await poll();
    schedulePoll();
  }, pollDelayMs);
}
function scheduleStatus() {
  setTimeout(async () => {
    await refreshStatus();
    scheduleStatus();
  }, statusDelayMs);
}
function scheduleProgress() {
  setTimeout(async () => {
    if (progressOpen || (busy && busy.classList.contains('on'))) {
      await refreshProgress();
    }
    scheduleProgress();
  }, progressDelayMs);
}
(async () => {
  await refreshStatus();
  await poll();
  schedulePoll();
  scheduleStatus();
  scheduleProgress();
})();
</script></body></html>"""
