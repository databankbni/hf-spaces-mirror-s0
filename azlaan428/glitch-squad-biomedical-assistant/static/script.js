async function submitQuery() {
    const input = document.getElementById('queryInput');
    const btn = document.getElementById('submitBtn');
    const statusBar = document.getElementById('statusBar');
    const statusText = document.getElementById('statusText');
    const responseBox = document.getElementById('responseBox');
    const responseText = document.getElementById('responseText');

    const query = input.value.trim();
    if (!query) return;

    btn.disabled = true;
    responseBox.classList.add('hidden');
    statusBar.classList.remove('hidden');
    statusText.textContent = 'Retrieving PubMed literature...';

    try {
        const res = await fetch('/query', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: query })
        });

        const data = await res.json();
        statusBar.classList.add('hidden');

        if (data.error) {
            responseText.textContent = 'Error: ' + data.error;
        } else {
            responseText.textContent = data.response;
        }

        responseBox.classList.remove('hidden');

    } catch (err) {
        statusBar.classList.add('hidden');
        responseText.textContent = 'Network error: ' + err.message;
        responseBox.classList.remove('hidden');
    } finally {
        btn.disabled = false;
    }
}

document.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        submitQuery();
    }
});