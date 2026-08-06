const BANKING_FAQS = [
  "What are HDFC branch timings?",
  "Where is the nearest HDFC ATM?",
  "How do I pay my HDFC credit card bill?",
  "What loan products does HDFC Bank offer?",
  "How can I contact HDFC customer care?",
  "Can I open an HDFC account online?",
  "What documents are required for HDFC account opening?",
];

const messagesEl = document.getElementById("messages");
const chatFormEl = document.getElementById("chat-form");
const chatInputEl = document.getElementById("chat-input");
const faqButtonsEl = document.getElementById("faq-buttons");

const history = [];

function addMessage(role, text) {
  const node = document.createElement("div");
  node.className = `message ${role}`;

  const textNode = document.createElement("p");
  textNode.className = "message-text";
  textNode.textContent = text;
  node.appendChild(textNode);

  messagesEl.appendChild(node);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return node;
}

async function askBackendLlm(question) {
  const response = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: question,
      history,
    }),
  });

  let payload = {};
  try {
    payload = await response.json();
  } catch {
    payload = {};
  }

  if (!response.ok) {
    throw new Error(payload.answer || `Request failed with status ${response.status}`);
  }

  return payload.answer || "No answer returned.";
}

async function submitQuestion(question) {
  const trimmed = question.trim();
  if (!trimmed) {
    return;
  }

  addMessage("user", trimmed);
  const loadingNode = addMessage("bot", "Thinking...");

  try {
    const answer = await askBackendLlm(trimmed);
    loadingNode.remove();
    addMessage("bot", answer);
    history.push([trimmed, answer]);
  } catch (error) {
    loadingNode.remove();
    const fallback = `I could not reach the LLM right now. ${error.message}`;
    addMessage("bot", fallback);
    history.push([trimmed, fallback]);
  }
}

function renderFaqButtons() {
  if (!faqButtonsEl) {
    return;
  }

  const fragment = document.createDocumentFragment();

  for (const question of BANKING_FAQS) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "example-chip";
    button.dataset.question = question;
    button.textContent = question;
    button.addEventListener("click", () => {
      submitQuestion(question);
    });
    fragment.appendChild(button);
  }

  faqButtonsEl.innerHTML = "";
  faqButtonsEl.appendChild(fragment);
}

chatFormEl.addEventListener("submit", (event) => {
  event.preventDefault();
  submitQuestion(chatInputEl.value);
  chatInputEl.value = "";
  chatInputEl.focus();
});

renderFaqButtons();

addMessage(
  "bot",
  "Hello. I am your HDFC banking support assistant. Every question is sent directly to the LLM."
);
