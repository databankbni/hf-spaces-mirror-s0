from flask import Flask, jsonify, request

from BankingAgent import banking_chat_handler


app = Flask(__name__)


HTML_PAGE = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>HDFC Banking Assistant</title>
    <style>
      :root {
        --bg: #f4f7fb;
        --surface: #ffffff;
        --surface-soft: #f8fbff;
        --primary: #045f9c;
        --primary-soft: #e8f4ff;
        --text: #1f2937;
        --muted: #5b6472;
        --border: #d9e2ec;
      }
      * { box-sizing: border-box; }
      body {
        font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
        max-width: 920px;
        margin: 24px auto;
        padding: 0 12px;
        color: var(--text);
        background:
          radial-gradient(circle at 10% 10%, #ffffff 0%, rgba(255,255,255,0) 40%),
          radial-gradient(circle at 90% 0%, #e8f2ff 0%, rgba(232,242,255,0) 42%),
          var(--bg);
      }
      .card {
        border: 1px solid var(--border);
        border-radius: 16px;
        background: var(--surface);
        padding: 16px;
        margin-bottom: 14px;
        box-shadow: 0 12px 28px rgba(15, 23, 42, 0.06);
      }
      .row { display: flex; gap: 10px; }
      .stack { display: grid; gap: 10px; }
      input, button, select {
        font-size: 14px;
        padding: 10px 12px;
        border-radius: 10px;
        border: 1px solid var(--border);
      }
      button {
        background: #ffffff;
        color: var(--text);
        cursor: pointer;
      }
      button:hover {
        border-color: #b9c9dc;
        background: #fafdff;
      }
      #message { flex: 1; }
      #log {
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 14px;
        min-height: 340px;
        margin-bottom: 10px;
        display: flex;
        flex-direction: column;
        gap: 12px;
        background: linear-gradient(180deg, #fbfdff 0%, #f6f9fc 100%);
      }
      .u, .a {
        margin: 0;
        padding: 11px 13px;
        border-radius: 12px;
        line-height: 1.55;
        max-width: 92%;
      }
      .u {
        align-self: flex-end;
        color: #0b4f8a;
        background: var(--primary-soft);
        border: 1px solid #cfe7ff;
        font-family: Georgia, "Times New Roman", serif;
        font-weight: 700;
      }
      .a {
        align-self: flex-start;
        color: var(--text);
        background: var(--surface-soft);
        border: 1px solid #deebf8;
        font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      }
      .msg-title {
        display: block;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        margin-bottom: 5px;
        color: var(--muted);
      }
      .msg-body {
        white-space: pre-line;
        word-break: break-word;
      }
      .sources {
        margin-top: 10px;
        padding-top: 8px;
        border-top: 1px dashed #c8d8ea;
      }
      .sources strong {
        display: block;
        margin-bottom: 4px;
        color: #2a4766;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
      }
      .sources a {
        color: var(--primary);
        text-decoration: none;
      }
      .sources a:hover { text-decoration: underline; }
      .hidden { display: none; }
      .muted { color: var(--muted); font-size: 13px; }
      @media (max-width: 640px) {
        body { margin: 12px auto; }
        .u, .a { max-width: 100%; }
        .row.card { flex-direction: column; }
      }
    </style>
  </head>
  <body>
    <div id="landing" class="card">
      <h1>HDFC Login</h1>
      <p class="muted">Login page for demo use only.</p>
      <div class="stack">
        <input id="userId" placeholder="Customer ID / User ID" />
        <input id="password" type="password" placeholder="Password" />
        <div class="row">
          <button id="enterDemo" type="button">Sign In</button>
          <button id="clearDemo" type="button">Clear</button>
        </div>
      </div>
    </div>

    <div id="app" class="hidden">
      <div class="card">
        <div class="row" style="justify-content:space-between;align-items:center;">
          <h1 style="margin:0;">HDFC Customer Support Agent</h1>
          <button id="signOut" type="button">Sign Out</button>
        </div>
      </div>

      <div id="suggestions" style="display:flex;flex-wrap:wrap;gap:8px;margin:0 0 12px;"></div>

      <div id="log" class="card"></div>

      <div class="row card">
        <input id="message" placeholder="Ask your banking question..." />
        <button id="send">Send</button>
      </div>
    </div>

    <script>
      const landing = document.getElementById('landing');
      const userId = document.getElementById('userId');
      const password = document.getElementById('password');
      const enterDemo = document.getElementById('enterDemo');
      const clearDemo = document.getElementById('clearDemo');
      const signOut = document.getElementById('signOut');
      const app = document.getElementById('app');
      const log = document.getElementById('log');
      const message = document.getElementById('message');
      const send = document.getElementById('send');
      const suggestions = document.getElementById('suggestions');
      const history = [];
      const SUGGESTED_QUESTIONS = [
        'What are your branch timings?',
        'How can I find an HDFC branch near me?',
        'Where can I find an ATM?',
        'How do I register a complaint?',
        'Tell me about your loan products.',
        'What documents are needed for a new account?'
      ];

      function openDemoApp() {
        landing.classList.add('hidden');
        app.classList.remove('hidden');
        append('assistant', 'Welcome. You are now in the HDFC demo assistant.');
        message.focus();
      }

      enterDemo.addEventListener('click', () => {
        // Demo mode: allow quick entry even if fields are left empty.
        if (!userId.value.trim()) userId.value = 'demo-user';
        if (!password.value.trim()) password.value = 'demo-pass';
        openDemoApp();
      });

      userId.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') openDemoApp();
      });

      password.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') openDemoApp();
      });

      clearDemo.addEventListener('click', () => {
        userId.value = '';
        password.value = '';
      });

      signOut.addEventListener('click', () => {
        history.length = 0;
        log.innerHTML = '';
        message.value = '';
        app.classList.add('hidden');
        landing.classList.remove('hidden');
        userId.value = '';
        password.value = '';
        userId.focus();
      });

      function formatAssistantText(text) {
        const [mainPart, sourcesPart] = text.split(/\\n\\nSources:\\n/i);
        const wrapper = document.createElement('div');

        const body = document.createElement('div');
        body.className = 'msg-body';
        body.textContent = mainPart || text;
        wrapper.appendChild(body);

        if (sourcesPart) {
          const sources = document.createElement('div');
          sources.className = 'sources';

          const title = document.createElement('strong');
          title.textContent = 'Sources';
          sources.appendChild(title);

          const lines = sourcesPart
            .split('\\n')
            .map((line) => line.trim())
            .filter((line) => line);

          lines.forEach((line) => {
            const row = document.createElement('div');
            const tokens = line.split(' ').filter((token) => token.trim());
            const url = tokens.find((token) => token.startsWith('https://') || token.startsWith('http://'));
            if (url) {
              const prefix = line.slice(0, line.indexOf(url)).trim();
              if (prefix) {
                const prefixNode = document.createElement('span');
                prefixNode.textContent = `${prefix} `;
                row.appendChild(prefixNode);
              }
              const link = document.createElement('a');
              link.href = url;
              link.target = '_blank';
              link.rel = 'noopener noreferrer';
              link.textContent = url;
              row.appendChild(link);

              const suffix = line.slice(line.indexOf(url) + url.length).trim();
              if (suffix) {
                const suffixNode = document.createElement('span');
                suffixNode.textContent = ` ${suffix}`;
                row.appendChild(suffixNode);
              }
            } else {
              row.textContent = line;
            }
            sources.appendChild(row);
          });

          wrapper.appendChild(sources);
        }

        return wrapper;
      }

      function append(role, text) {
        const node = document.createElement('div');
        node.className = role === 'user' ? 'u' : 'a';

        const title = document.createElement('span');
        title.className = 'msg-title';
        title.textContent = role === 'user' ? 'You' : 'Agent';
        node.appendChild(title);

        if (role === 'assistant') {
          node.appendChild(formatAssistantText(text));
        } else {
          const body = document.createElement('div');
          body.className = 'msg-body';
          body.textContent = text;
          node.appendChild(body);
        }

        log.appendChild(node);
        log.scrollTop = log.scrollHeight;
        return node;
      }

      async function sendMessage() {
        const text = message.value.trim();
        if (!text) return;
        message.value = '';
        append('user', text);
        append('assistant', 'Thinking...');

        try {
          const res = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, history })
          });

          let data = {};
          try {
            data = await res.json();
          } catch {
            data = {};
          }

          if (log.lastChild && log.lastChild.classList.contains('a')) {
            log.lastChild.remove();
          }

          const fallbackError = 'I could not fetch the response right now. Please try again.';
          const answerText = res.ok ? (data.answer || 'No answer returned.') : (data.answer || fallbackError);
          const answerNode = append('assistant', answerText);
          answerNode.scrollIntoView({ behavior: 'smooth', block: 'start' });
          history.push([text, answerText]);
        } catch (err) {
          if (log.lastChild && log.lastChild.classList.contains('a')) {
            log.lastChild.remove();
          }
          const answerNode = append('assistant', 'Network error. Please check connection and try again.');
          answerNode.scrollIntoView({ behavior: 'smooth', block: 'start' });
          history.push([text, 'Network error. Please check connection and try again.']);
        }
      }

      function renderSuggestions() {
        SUGGESTED_QUESTIONS.forEach((q) => {
          const btn = document.createElement('button');
          btn.textContent = q;
          btn.style.border = '1px solid #cfd8e3';
          btn.style.borderRadius = '999px';
          btn.style.padding = '7px 11px';
          btn.style.background = '#f8fbff';
          btn.style.cursor = 'pointer';
          btn.addEventListener('click', () => {
            message.value = q;
            sendMessage();
          });
          suggestions.appendChild(btn);
        });
      }

      send.addEventListener('click', sendMessage);
      message.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') sendMessage();
      });

      renderSuggestions();
    </script>
  </body>
</html>
"""


@app.get("/")
def home():
    return HTML_PAGE


@app.post("/chat")
def chat():
    body = request.get_json(silent=True) or {}
    user_message = (body.get("message") or "").strip()
    model_name = "llama-3.1-8b-instant"
    history = body.get("history") or []

    if not user_message:
        return jsonify({"answer": "Please enter a question."})

    answer = banking_chat_handler(user_message, history, model_name)
    return jsonify({"answer": answer})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7860)
