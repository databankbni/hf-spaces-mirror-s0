// Custom confirm modal — some hosting embeds (e.g. Hugging Face Spaces'
// huggingface.co/spaces/... iframe wrapper) silently block or auto-dismiss
// native window.confirm()/alert() dialogs when called from inside an
// iframe that doesn't grant modal permissions. That makes any button whose
// handler starts with `if (!window.confirm(...)) return;` look completely
// broken — the click appears to do nothing. This renders its own in-page
// dialog instead, so cancel/delete actions work regardless of embedding.
(function () {
  const overlay = document.getElementById("confirm-overlay");
  const messageEl = document.getElementById("confirm-modal-message");
  const inputEl = document.getElementById("confirm-modal-input");
  const okBtn = document.getElementById("confirm-modal-ok");
  const cancelBtn = document.getElementById("confirm-modal-cancel");

  let resolvePending = null;
  let isPrompt = false;

  function close(confirmed) {
    overlay.classList.add("stage--hidden");
    document.removeEventListener("keydown", onKeydown);
    if (resolvePending) {
      const resolve = resolvePending;
      resolvePending = null;
      resolve(isPrompt ? (confirmed ? inputEl.value.trim() : null) : confirmed);
    }
  }

  function onKeydown(e) {
    if (e.key === "Escape") close(false);
    if (e.key === "Enter") close(true);
  }

  window.showConfirm = function (message) {
    return new Promise((resolve) => {
      resolvePending = resolve;
      isPrompt = false;
      messageEl.textContent = message;
      inputEl.classList.add("stage--hidden");
      cancelBtn.classList.remove("stage--hidden");
      okBtn.textContent = "Ya, lanjutkan";
      overlay.classList.remove("stage--hidden");
      document.addEventListener("keydown", onKeydown);
    });
  };

  // Same modal, single "OK" button — for messages that just need
  // acknowledging (replaces window.alert()).
  window.showAlert = function (message) {
    return new Promise((resolve) => {
      resolvePending = resolve;
      isPrompt = false;
      messageEl.textContent = message;
      inputEl.classList.add("stage--hidden");
      cancelBtn.classList.add("stage--hidden");
      okBtn.textContent = "OK";
      overlay.classList.remove("stage--hidden");
      document.addEventListener("keydown", onKeydown);
    });
  };

  // Same modal plus a text field — replaces window.prompt(), which the
  // iframe embed blocks exactly like confirm()/alert(). Resolves the typed
  // (trimmed) value, or null if cancelled/left empty.
  window.showPrompt = function (message, defaultValue) {
    return new Promise((resolve) => {
      resolvePending = resolve;
      isPrompt = true;
      messageEl.textContent = message;
      inputEl.value = defaultValue || "";
      inputEl.classList.remove("stage--hidden");
      cancelBtn.classList.remove("stage--hidden");
      okBtn.textContent = "Simpan";
      overlay.classList.remove("stage--hidden");
      document.addEventListener("keydown", onKeydown);
      requestAnimationFrame(() => inputEl.focus());
    });
  };

  okBtn.addEventListener("click", () => close(true));
  cancelBtn.addEventListener("click", () => close(false));
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) close(false);
  });
})();
