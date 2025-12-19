
const editor = document.getElementById('editor');

const boldBtn = document.getElementById('bold-btn');
const italicBtn = document.getElementById('italic-btn');
const colorPicker = document.getElementById('color-picker');

const saveBack = document.getElementById('save-back');


function toggleCommand(command) {
    document.execCommand(command, false, null);
    updateButtonState();
}

function updateButtonState() {
    boldBtn.setAttribute('aria-pressed', document.queryCommandState('bold'));
    italicBtn.setAttribute('aria-pressed', document.queryCommandState('italic'));
}

function applyColor() {
    document.execCommand('foreColor', false, colorPicker.value);
    updateButtonState();
}


boldBtn.addEventListener('click', () => toggleCommand('bold'));
italicBtn.addEventListener('click', () => toggleCommand('italic'));
colorPicker.addEventListener('change', applyColor);
colorPicker.addEventListener('input', applyColor);

saveBack.addEventListener('click', () => {
    saveDocument()
        .then(() => window.location.href = "/account")
        .catch((err) => alert(err));
});

editor.addEventListener('keyup', updateButtonState);
editor.addEventListener('mouseup', updateButtonState);
editor.addEventListener('selectionchange', updateButtonState);


updateButtonState();



const pathParts = window.location.pathname.split('/');
const currentUser = pathParts[2];
const docId = pathParts[4];

const GATEWAY_BASE = window.API_GATEWAY_URL || "http://localhost:8000";
const GATEWAY_WS = window.API_GATEWAY_WS || "ws://localhost:8000";

let currentTitle = "";

async function loadDocument() {
    try {
        const resp = await fetch(`${GATEWAY_BASE}/documents/${docId}`);
        if (!resp.ok) {
            throw new Error("Не удалось загрузить документ");
        }
        const doc = await resp.json();
        currentTitle = doc.title || `Документ ${docId}`;
        editor.innerHTML = doc.content || "";
    } catch (err) {
        console.error(err);
        alert("Ошибка загрузки документа с сервера");
    }
}

async function saveDocument() {
    try {
        const body = {
            title: currentTitle,
            content: editor.innerHTML
        };
        const resp = await fetch(`${GATEWAY_BASE}/documents/${docId}`, {
            method: "PUT",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(body)
        });
        if (!resp.ok) {
            throw new Error("Не удалось сохранить документ");
        }
    } catch (err) {
        console.error(err);
    }
}

let ws;

function setupWebSocket() {
    const token = encodeURIComponent(currentUser);
    const ws = new WebSocket(`ws://${window.location.hostname}:8000/ws/documents/${docId}?token=${token}`);

    ws.onopen = () => {
        console.log("WS connected via API Gateway");
    };

    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);

            if (msg.type === "initial") {
                editor.innerHTML = msg.content || "";
            } else if (msg.type === "update") {
                editor.innerHTML = msg.content || "";
            } else if (msg.type === "error") {
                console.error("WS error:", msg.message);
            } else if (msg.type === "info") {
                console.log("WS info:", msg.message);
            }
        } catch (e) {
            console.log("WS message (raw):", event.data);
        }
    };

    ws.onclose = () => {
        console.log("WS closed");
    };

    ws.onerror = (err) => {
        console.error("WS error:", err);
    };

    editor.addEventListener("input", () => {
        if (ws.readyState === WebSocket.OPEN) {
            const msg = {
                type: "change",
                content: editor.innerHTML,
                user: currentUser
            };
            ws.send(JSON.stringify(msg));
        }
    });
}

window.addEventListener("load", async () => {
    await loadDocument();
    setupWebSocket();
    setInterval(saveDocument, 5000);
});