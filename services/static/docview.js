
const editor = document.getElementById('editor');
const boldBtn = document.getElementById('bold-btn');
const italicBtn = document.getElementById('italic-btn');

function toggleCommand(command) {
    document.execCommand(command, false, null);
    updateButtonState();
}

function updateButtonState() {
    boldBtn.setAttribute('aria-pressed', document.queryCommandState('bold'));
    italicBtn.setAttribute('aria-pressed', document.queryCommandState('italic'));
}


boldBtn.addEventListener('click', () => toggleCommand('bold'));
italicBtn.addEventListener('click', () => toggleCommand('italic'));

editor.addEventListener('keyup', updateButtonState);
editor.addEventListener('mouseup', updateButtonState);


updateButtonState();
