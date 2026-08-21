"""Static, trusted HTML for the session-independent mobile upload surface."""

from __future__ import annotations


MOBILE_UPLOAD_HTML = r"""
<!doctype html>
<html lang="bg">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { color-scheme: dark; font-family: sans-serif; }
  body { margin: 0; color: #f1f5f9; background: transparent; }
  .box { border: 1px solid #475569; border-radius: 12px; padding: 14px; background: #1e293b; }
  .title { font-weight: 700; margin-bottom: 6px; }
  .hint { color: #cbd5e1; font-size: 14px; line-height: 1.4; margin-bottom: 12px; }
  input[type=file] { display: block; width: 100%; margin: 8px 0 12px; }
  button { border: 0; border-radius: 8px; padding: 10px 14px; font-weight: 700; cursor: pointer; }
  .confirm { background: #22c55e; color: #052e16; margin-top: 10px; }
  .confirm:disabled { background: #64748b; color: #e2e8f0; cursor: wait; }
  .status { min-height: 22px; font-size: 14px; line-height: 1.4; }
  .ok { color: #86efac; }
  .error { color: #fca5a5; }
  .progress { color: #7dd3fc; }
</style>
</head>
<body>
<div class="box">
  <div class="title">📱 Android resilient upload — експеримент</div>
  <div class="hint">Файлът се прехвърля независимо от Streamlit сесията. Анализът започва само след изрично потвърждение.</div>
  <input id="file" type="file" accept=".dxf,.dwg">
  <div id="status" class="status">Подготвям защитения upload…</div>
  <div id="pending"></div>
</div>
<script>
(() => {
  const API = "/api/zuru-mobile-upload";
  const MAX = 200 * 1024 * 1024;
  const status = document.getElementById("status");
  const pending = document.getElementById("pending");
  const input = document.getElementById("file");
  let xsrf = null;

  function setStatus(message, kind = "") {
    status.textContent = message;
    status.className = "status " + kind;
  }

  async function jsonFetch(url, options = {}) {
    const response = await fetch(url, {
      credentials: "same-origin",
      cache: "no-store",
      ...options,
    });
    let payload = {};
    try { payload = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    return payload;
  }

  function renderReady(upload) {
    pending.replaceChildren();
    const text = document.createElement("div");
    text.className = "ok";
    text.textContent = `✅ Получен: ${upload.filename} (${(upload.size / 1048576).toFixed(1)} MB)`;
    const button = document.createElement("button");
    button.className = "confirm";
    button.textContent = "Потвърди и анализирай";
    button.addEventListener("click", async () => {
      button.disabled = true;
      setStatus("Потвърждавам файла…", "progress");
      try {
        const result = await jsonFetch(`${API}/intents/${encodeURIComponent(upload.upload_id)}/claim`, {
          method: "POST",
          headers: { "X-Zuru-XSRF": xsrf },
        });
        const target = new URL(window.parent.location.href);
        target.searchParams.set("zuru_staged_claim", result.claim_token);
        window.parent.location.assign(target.toString());
      } catch (_) {
        button.disabled = false;
        setStatus("Потвърждението не успя. Опитай отново.", "error");
      }
    });
    pending.append(text, button);
    setStatus("Файлът чака твоето потвърждение.", "ok");
  }

  async function refreshPending() {
    const payload = await jsonFetch(`${API}/pending`);
    const ready = (payload.uploads || []).filter(item => item.ready);
    if (ready.length) renderReady(ready[ready.length - 1]);
    else setStatus("Готово за избор на DXF/DWG файл.");
  }

  async function initialize() {
    const bootstrap = await jsonFetch(`${API}/bootstrap`);
    xsrf = bootstrap.xsrf_token;
    await refreshPending();
  }

  input.addEventListener("change", async () => {
    const file = input.files && input.files[0];
    if (!file) return;
    const extension = file.name.includes(".") ? file.name.split(".").pop().toLowerCase() : "";
    if (!["dxf", "dwg"].includes(extension)) {
      setStatus("Разрешени са само DXF и DWG файлове.", "error");
      input.value = "";
      return;
    }
    if (file.size <= 0 || file.size > MAX) {
      setStatus("Файлът трябва да е до 200 MB.", "error");
      input.value = "";
      return;
    }

    pending.replaceChildren();
    setStatus("Качвам файла независимо от Streamlit сесията…", "progress");
    try {
      const intent = await jsonFetch(`${API}/intents`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Zuru-XSRF": xsrf },
        body: JSON.stringify({ filename: file.name, size: file.size }),
      });
      const uploaded = await jsonFetch(`${API}/intents/${encodeURIComponent(intent.upload_id)}/bytes`, {
        method: "PUT",
        headers: { "Content-Type": "application/octet-stream", "X-Zuru-XSRF": xsrf },
        body: file,
      });
      renderReady(uploaded);
    } catch (_) {
      setStatus("Качването не успя. След възстановяване избери файла отново.", "error");
    } finally {
      input.value = "";
    }
  });

  initialize().catch(() => setStatus("Защитеният mobile upload не може да стартира.", "error"));
})();
</script>
</body>
</html>
"""
