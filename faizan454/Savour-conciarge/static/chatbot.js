async function sendMessage(text) {

  const input = document.getElementById('user-input');
  const message = text || input.value.trim();

  if (!message) return;

  // Remove welcome message
  const welcome = document.querySelector('.welcome-msg');
  if (welcome) welcome.remove();

  // Show user message
  addMessage(message, 'user');
  input.value = '';

  // Show typing indicator
  addMessage('Typing...', 'bot', 'typing');

  try {
    const response = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: message })
    });

    const data = await response.json();

    // Remove typing
    const typing = document.getElementById('typing');
    if (typing) typing.remove();

    // Show reply
    addMessage(data.reply, 'bot');

  } catch (error) {
    const typing = document.getElementById('typing');
    if (typing) typing.remove();
    addMessage('Sorry, something went wrong. Please try again.', 'bot');
  }
}

function addMessage(text, sender, id = '') {
  const chatBox = document.getElementById('chat-box');
  const div = document.createElement('div');
  div.className = `message ${sender}-message`;
  if (id) div.id = id;
  div.innerHTML = formatText(text);
  chatBox.appendChild(div);
  chatBox.scrollTop = chatBox.scrollHeight;
  return div;
}

function askQuestion(question) {
  sendMessage(question);
}

function formatText(text) {
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
    .replace(/\n/g, '<br>');
}

// Send on Enter key
document.addEventListener('keydown', function(e) {
  if (e.key === 'Enter') sendMessage();
});