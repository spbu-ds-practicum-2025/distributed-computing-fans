
const editor = document.getElementById('editor');

const boldBtn = document.getElementById('bold-btn');
const italicBtn = document.getElementById('italic-btn');
const colorPicker = document.getElementById('color-picker');
const saveBack = document.getElementById('save-back');

const pathParts = window.location.pathname.split('/');
const currentUser = pathParts[2];
const docId = pathParts[4];

const GATEWAY_BASE = window.API_GATEWAY_URL || "http://localhost:8000";
const GATEWAY_WS = window.API_GATEWAY_WS || "ws://localhost:8000";

let ydoc, ytext, yprovider, yxmlFragment, provider, awareness;


async function initYjs() {
    ydoc = new Y.Doc();
    ytext = ydoc.getText('content');
    
    provider = new yWebsocket.WebsocketProvider(
        GATEWAY_WS,
        `/documents/${docId}?token=${encodeURIComponent(currentUser)}`,
        ydoc
    );

    // allows to see other users' cursors
    awareness = provider.awareness;

    yxmlFragment = Y.XmlFragment.create(ydoc, 'content-html');
    const binding = new Y.ContenteditableBinding(yxmlFragment, editor, provider.awareness, {});

    updateButtonState();
    ydoc.on('update', updateButtonState);
}


function toggleCommand(command) {
    document.execCommand(command, false, null);
    updateButtonState();
}


function updateButtonState() {
    boldBtn.setAttribute('aria-pressed', document.queryCommandState('bold') ? 'true' : 'false');
    italicBtn.setAttribute('aria-pressed', document.queryCommandState('italic') ? 'true' : 'false');
}


function applyColor() {
    document.execCommand('foreColor', false, colorPicker.value);
    updateButtonState();
}


boldBtn.addEventListener('click', () => toggleCommand('bold'));
italicBtn.addEventListener('click', () => toggleCommand('italic'));
colorPicker.addEventListener('change', applyColor);
colorPicker.addEventListener('input', applyColor);

editor.addEventListener('selectionchange', updateButtonState);
editor.addEventListener('keyup', updateButtonState);
editor.addEventListener('mouseup', updateButtonState);


async function saveDocument() {
    try {
        const content = ytext.toString();
        const htmlContent = editor.innerHTML;
        const body = {
            title: `Document ${docId}`,
            content: htmlContent
        };

        const resp = await fetch(`${GATEWAY_BASE}/documents/${docId}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        });

        if (!resp.ok) throw new Error("Не удалось сохранить документ");
    } catch (err) {
        console.error(err);
        throw err;
    }
}

saveBack.addEventListener('click', () => {
    saveDocument()
        .then(() => window.location.href = "/account")
        .catch((err) => alert(err.message));
});


// initializing on page load
window.addEventListener("load", async () => {
    await initYjs();
    setInterval(saveDocument, 5000);
});




