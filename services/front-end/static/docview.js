// services/front-end/static/docview.js
// =============================
// Conspektor Doc View (CRDT MVP)
// - No CDN, no ESM imports required in browser
// - Yjs is loaded via /static/yjs.umd.js and exposed as window.Y
// - Sync via custom Collaboration Hub protocol (JSON + hex) through API Gateway
// =============================

const Y = window.Y;
if (!Y) {
  console.error("Yjs (window.Y) is not available. Ensure /static/yjs.umd.js is loaded before docview.js.");
  alert("Yjs не загружен. Проверь, что /static/yjs.umd.js подключён в docview.html.");
}

const editor = document.getElementById("editor");

const boldBtn = document.getElementById("bold-btn");
const italicBtn = document.getElementById("italic-btn");
const colorPicker = document.getElementById("color-picker");
const saveBack = document.getElementById("save-back");

// --- Formatting toolbar (kept) ---
function toggleCommand(command) {
  document.execCommand(command, false, null);
  updateButtonState();
}
function updateButtonState() {
  try {
    boldBtn?.setAttribute("aria-pressed", document.queryCommandState("bold") ? "true" : "false");
    italicBtn?.setAttribute("aria-pressed", document.queryCommandState("italic") ? "true" : "false");
  } catch (_) {}
}
function applyColor() {
  const color = colorPicker?.value;
  if (color) document.execCommand("foreColor", false, color);
}

boldBtn?.addEventListener("click", () => toggleCommand("bold"));
italicBtn?.addEventListener("click", () => toggleCommand("italic"));
colorPicker?.addEventListener("change", applyColor);
colorPicker?.addEventListener("input", applyColor);

editor?.addEventListener("keyup", updateButtonState);
editor?.addEventListener("mouseup", updateButtonState);
document.addEventListener("selectionchange", updateButtonState);

updateButtonState();

// --- Helpers: hex <-> Uint8Array ---
function bytesToHex(uint8) {
  return Array.from(uint8, (b) => b.toString(16).padStart(2, "0")).join("");
}
function hexToBytes(hex) {
  if (!hex) return new Uint8Array();
  const len = Math.floor(hex.length / 2);
  const out = new Uint8Array(len);
  for (let i = 0; i < len; i++) out[i] = parseInt(hex.substr(i * 2, 2), 16);
  return out;
}

// --- URL layout: /users/<username>/documents/<docId> ---
const parts = window.location.pathname.split("/").filter(Boolean);
// ["users", "<username>", "documents", "<docId>"]
const currentUser = parts[1] || "demo";
const docId = parts[3] || "";

// Gateway base (for REST). Can be overridden via template if desired.
const GATEWAY_BASE = window.API_GATEWAY_URL || "http://localhost:8000";

// --- REST: load & save (for initial paint + Save&Back) ---
let currentTitle = "";

async function loadDocumentForInitialPaint() {
  if (!docId) return;
  try {
    const resp = await fetch(`${GATEWAY_BASE}/documents/${encodeURIComponent(docId)}`);
    if (!resp.ok) throw new Error(`Не удалось загрузить документ (${resp.status})`);

    const data = await resp.json();
    const doc = Array.isArray(data) ? data[0] : data;

    currentTitle = doc?.title || "";
    const content = doc?.content || "";
    editor.innerHTML = content && content.length ? content : "Начните писать...";
  } catch (err) {
    console.error(err);
    // Keep placeholder
  }
}

async function saveDocument() {
  if (!docId) throw new Error("docId отсутствует в URL");
  const body = {
    title: currentTitle || "Без названия",
    content: editor?.innerHTML || ""
  };

  const resp = await fetch(`${GATEWAY_BASE}/documents/${encodeURIComponent(docId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!resp.ok) {
    const txt = await resp.text().catch(() => "");
    throw new Error(`Не удалось сохранить документ (${resp.status}) ${txt}`);
  }
}

saveBack?.addEventListener("click", () => {
  saveDocument()
    .then(() => (window.location.href = "/account"))
    .catch((err) => alert(err?.message || String(err)));
});

// --- CRDT (Yjs) over custom WS protocol ---
let ws = null;
const ydoc = Y ? new Y.Doc() : null;
const ytext = (Y && ydoc) ? ydoc.getText("content") : null;

let suppressSend = false;
let sentSyncRequest = false;
let editorDebounce = null;

function getEditorText() {
  return editor?.innerHTML || "";
}
function setEditorText(text) {
  const t = text || "";
  if (!editor) return;
  if ((editor.innerHTML || "") !== t) editor.innerHTML = t;
}

function renderFromYjs() {
  if (!ytext) return;
  setEditorText(ytext.toString());
}

function overwriteYjsFromEditor() {
  if (!ydoc || !ytext) return;
  const next = getEditorText();
  const prev = ytext.toString();
  if (next === prev) return;

  ydoc.transact(() => {
    ytext.delete(0, ytext.length);
    ytext.insert(0, next);
  });
}

function connectWs() {
  if (!Y || !ydoc || !ytext) return;

  if (!docId) {
    console.error("docId not found in URL. Expected /users/<username>/documents/<docId>");
    return;
  }
  if (!editor) {
    console.error("editor element (#editor) not found");
    return;
  }

  // token is required by hub/gateway. For MVP use username.
  const token = encodeURIComponent(currentUser || "demo");

  const gatewayUrl = new URL(GATEWAY_BASE); // например http://localhost:8000
  const wsProto = gatewayUrl.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${wsProto}//${gatewayUrl.host}/ws/documents/${encodeURIComponent(docId)}?token=${token}`;


  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log("WS connected (CRDT)", wsUrl);
    // Server should push "sync" as first message.
  };

  ws.onmessage = (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }

    if (msg.type === "sync") {
      const updateBytes = hexToBytes(msg.update);
      suppressSend = true;
      Y.applyUpdate(ydoc, updateBytes);
      suppressSend = false;

      renderFromYjs();

      if (!sentSyncRequest) {
        sentSyncRequest = true;
        const sv = Y.encodeStateVector(ydoc);
        ws.send(JSON.stringify({ type: "sync_request", stateVector: bytesToHex(sv) }));
      }
      return;
    }

    if (msg.type === "update") {
      const updateBytes = hexToBytes(msg.update);
      suppressSend = true;
      Y.applyUpdate(ydoc, updateBytes);
      suppressSend = false;

      renderFromYjs();
      return;
    }

    if (msg.type === "error") {
      console.error("WS error:", msg.message || msg);
    }
  };

  ws.onerror = (e) => console.error("WS error", e);
  ws.onclose = () => console.log("WS closed");

  // Local Yjs updates -> send to server
  ydoc.on("update", (update) => {
    if (suppressSend) return;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: "update", update: bytesToHex(update) }));
  });

  // Editor input -> overwrite Y.Text entirely (MVP)
  editor.addEventListener("input", () => {
    clearTimeout(editorDebounce);
    editorDebounce = setTimeout(() => {
      overwriteYjsFromEditor();
    }, 100);
  });
}

// --- Startup ---
window.addEventListener("load", async () => {
  await loadDocumentForInitialPaint();
  connectWs();
});
