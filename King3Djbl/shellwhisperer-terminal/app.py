import os
import re
import signal
import subprocess
from pathlib import Path

# ---- gradio 4.44 / gradio_client schema-bug guard (belt & suspenders) ----
import gradio_client.utils as _gcu
_o = _gcu._json_schema_to_python_type
_gcu._json_schema_to_python_type = lambda s, d=None: ("bool" if isinstance(s, bool) else _o(s, d))
_g = _gcu.get_type
_gcu.get_type = lambda s: ("any" if not isinstance(s, dict) else _g(s))

import gradio as gr
from llama_cpp import Llama

MODEL_REPO = "fableforge-ai/ShellWhisperer-1.5B"
GGUF_FILE = "shellwhisperer-1.5b-Q4_K_M.gguf"
TIMEOUT_SECONDS = 10
MAX_OUTPUT_LINES = 200
SANDBOX = Path("/tmp/sw_sandbox")
SANDBOX.mkdir(parents=True, exist_ok=True)

print("Loading", MODEL_REPO, GGUF_FILE)
# FIXED: Hardcoded optimal threads for HF Spaces (2 cores / 4 threads max)
# FIXED: Added use_mmap=True to prevent RAM thrashing and cache efficiently
llm = Llama.from_pretrained(
    repo_id=MODEL_REPO, 
    filename=GGUF_FILE,
    n_ctx=2048, 
    n_threads=2, 
    use_mmap=True,
    chat_format="chatml", 
    verbose=False,
)
print("Model loaded.")

SYSTEM = (
    "You are ShellWhisperer, an expert Linux sysadmin. Convert the user's natural-language "
    "request into a single precise, safe bash command. Output ONLY the command — no prose, "
    "no markdown fences."
)


def generate_command(nl_prompt, cwd):
    out = llm.create_chat_completion(
        messages=[{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": "cwd: " + cwd + "\nRequest: " + nl_prompt}],
        max_tokens=128, temperature=0.2, top_p=0.9,
    )
    raw = out["choices"][0]["message"]["content"].strip()
    raw = re.sub(r"^```(?:bash|sh)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    # FIXED: Restored the [0] slice index so .strip() executes correctly on the string line
    return raw.splitlines()[0].strip() if raw else raw


# Best-effort denylist. NOT a real jail — reduces obvious abuse only.
DENY = re.compile(
    r"(?:\b(sudo|su|ssh|scp|sftp|telnet|nc|ncat|netcat|nmap|curl|wget|ftp|lynx|"
    r"crontab|at|shutdown|reboot|halt|mkfs|mount|umount|dd|apt|apt-get|yum|dnf|"
    r"apk|pip|pip3|npm|git)\b|/dev/(tcp|udp)|:\s*\(\s*\)\s*\{|\bnohup\b)",
    re.I,
)


def _clamp_cwd(cwd, target):
    nc = os.path.abspath(os.path.join(cwd, target))
    base = str(SANDBOX)
    if nc == base or nc.startswith(base + os.sep):
        return nc if os.path.isdir(nc) else None
    return None  # refuse to leave the sandbox


def execute(command, cwd):
    command = (command or "").strip()
    if not command:
        return "", "no command", -1, cwd
    if DENY.search(command):
        return "", "⛔ blocked: network/privilege/install commands are disabled in this public sandbox", -1, cwd
    # Handle cd ourselves (clamped to sandbox).
    if command.startswith("cd ") or command == "cd":
        target = command[3:].strip() or "."
        nc = _clamp_cwd(cwd, target)
        if nc is None:
            return "", "cd refused (outside sandbox or missing)", -1, cwd
        return "", "", 0, nc
    try:
        proc = subprocess.Popen(
            command, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, preexec_fn=os.setsid,
        )
        try:
            so, se = proc.communicate(timeout=TIMEOUT_SECONDS)
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            so, se = proc.communicate()
            rc, se = -1, "⏱️ timed out after %ds\n%s" % (TIMEOUT_SECONDS, se)
        so = "\n".join(so.splitlines()[-MAX_OUTPUT_LINES:])
        se = "\n".join(se.splitlines()[-MAX_OUTPUT_LINES:])
        return so, se, rc, cwd
    except Exception as e:
        return "", str(e), -1, cwd


custom_css = """
.terminal-box textarea { background:#0d0d1a !important; color:#00ffaa !important;
  font-family:'JetBrains Mono',monospace !important; font-size:13px !important; }
"""

with gr.Blocks(title="💻 ShellWhisperer Terminal",
               theme=gr.themes.Soft(primary_hue="emerald"), css=custom_css) as demo:
    gr.Markdown(
        "# 💻 ShellWhisperer Terminal\n"
        "### Type English → get Bash → run it. Powered by **ShellWhisperer-1.5B**.\n"
        "> ⚠️ **Public best-effort sandbox, not a real jail.** Network / sudo / installs are blocked; "
        "commands run in a throwaway `/tmp` dir and are killed after 10s. Don't put anything private here."
    )
    cwd_state = gr.State(str(SANDBOX))
    with gr.Row():
        with gr.Column(scale=1):
            nl = gr.Textbox(label="📝 Describe what you want",
                            placeholder="list all files by size, largest first", lines=2)
            with gr.Row():
                gen = gr.Button("⚡ Generate", variant="primary")
                run = gr.Button("🚀 Execute", variant="secondary")
                clr = gr.Button("🗑️ Clear", variant="stop")
            cmd = gr.Textbox(label="💲 Command (editable before you run it)")
        with gr.Column(scale=2):
            term = gr.Textbox(label="", value="💻 ShellWhisperer Terminal\nsandbox: /tmp/sw_sandbox\n",
                              lines=18, interactive=False, elem_classes="terminal-box", show_copy_button=True)
    with gr.Row():
        cwd_box = gr.Textbox(label="📂 cwd", value=str(SANDBOX), interactive=False)
        status = gr.Textbox(label="Status", value="✅ Ready", interactive=False)

    def do_gen(text, cwd, log):
        if not text.strip():
            return "", "⚠️ enter a description", log
        c = generate_command(text, cwd)
        return c, "✅ generated — review, then Execute", log + "\n\n[🤖] " + c

    def do_run(command, cwd, log):
        so, se, rc, ncwd = execute(command, cwd)
        body = (so + ("\n[stderr] " + se if se else "")).strip() or "<no output>"
        st = "✅ exit 0" if rc == 0 else ("⏱️ timed out" if rc == -1 and "timed" in se else "❌ exit " + str(rc))
        newlog = (log + "\n\n$ " + command + "\n" + body + "\n[" + st + "]")
        newlog = "\n".join(newlog.splitlines()[-200:])
        return newlog, st, ncwd, ncwd

    def do_clear(cwd):
        return "💻 cleared\n", "✅ cleared", cwd

    gen.click(do_gen, [nl, cwd_state, term], [cmd, status, term], api_name="generate")
    run.click(do_run, [cmd, cwd_state, term], [term, status, cwd_state, cwd_box], api_name="execute")
    nl.submit(do_gen, [nl, cwd_state, term], [cmd, status, term])
    clr.click(do_clear, [cwd_state], [term, status, cwd_box])
    gr.Markdown('---\n⬇️ [**Download ShellWhisperer**](https://huggingface.co) &nbsp;·&nbsp; 🧭 [FableForge Nexus](https://huggingface.co) &nbsp;·&nbsp; 🐦 [Share on X](https://twitter.com) &nbsp;·&nbsp; 👽 [Reddit](https://reddit.com)')

if __name__ == "__main__":
    demo.queue(default_concurrency_limit=1).launch(server_name="0.0.0.0", server_port=7860)
