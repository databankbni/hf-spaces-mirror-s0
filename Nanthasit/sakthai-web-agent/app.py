import gradio as gr
import subprocess, os, threading, torch, json, re, time, base64, io

subprocess.run(["playwright", "install", "chromium", "--with-deps"], capture_output=True)

from playwright.sync_api import sync_playwright
from transformers import AutoModelForCausalLM, AutoTokenizer
from PIL import Image

MODEL_ID = "Nanthasit/sakthai-coder-browser"

TOOLS = [
    {"type": "function", "function": {"name": "navigate", "description": "Go to a URL", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "click", "description": "Click an element by selector or text", "parameters": {"type": "object", "properties": {"target": {"type": "string", "description": "CSS selector, text label, or coordinate"}}, "required": ["target"]}}},
    {"type": "function", "function": {"name": "type", "description": "Type text into a field", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}, "text": {"type": "string"}, "clear_first": {"type": "boolean"}}, "required": ["selector", "text"]}}},
    {"type": "function", "function": {"name": "select", "description": "Select from dropdown", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}, "value": {"type": "string"}}, "required": ["selector", "value"]}}},
    {"type": "function", "function": {"name": "extract", "description": "Extract text content", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "scroll", "description": "Scroll the page", "parameters": {"type": "object", "properties": {"direction": {"type": "string", "enum": ["up", "down", "top", "bottom"]}}, "required": ["direction"]}}},
    {"type": "function", "function": {"name": "wait", "description": "Wait for milliseconds", "parameters": {"type": "object", "properties": {"ms": {"type": "integer"}}, "required": ["ms"]}}},
    {"type": "function", "function": {"name": "press_key", "description": "Press a keyboard key", "parameters": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}}},
    {"type": "function", "function": {"name": "screenshot", "description": "Take screenshot", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "go_back", "description": "Go back", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "done", "description": "Mark task as complete", "parameters": {"type": "object", "properties": {"answer": {"type": "string"}}}}},
]

print("Loading model on CPU...", flush=True)
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModelForCausalLM.from_pretrained(MODEL_ID, device_map=None, torch_dtype=torch.float32)
print("Model loaded", flush=True)

_tls = threading.local()

def get_page():
    if not hasattr(_tls, "page") or _tls.page is None:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        _tls.page = browser.new_page(viewport={"width": 1280, "height": 800})
        _tls.pw = pw
        _tls.browser = browser
    return _tls.page

def build_msgs(url, task):
    fmt = (
        "You are a browser automation agent. Complete the user's web task by outputting actions.\n"
        "Output ONLY actions, one per line, in this exact format:\n"
        "navigate(url=https://example.com)\n"
        "click(target=#submit-button)\n"
        "type(selector=#search, text=hello world)\n"
        "select(selector=#country, value=TH)\n"
        "extract(selector=.price)\n"
        "scroll(direction=down)\n"
        "wait(ms=2000)\n"
        "press_key(key=Enter)\n"
        "go_back()\n"
        "done(answer=the result)\n"
        "Example:\n"
        f"User: Go to {url} and read the page title\n"
        f"You: navigate(url={url})\n"
        f"Tool: Page loaded: {url}. Page title: Example Domain\n"
        "You: done(answer=Example Domain)\n"
    )
    return [
        {"role": "system", "content": "You are a browser automation agent. Output tool-call lines only."},
        {"role": "user", "content": fmt + f"\nTask: Go to {url} and {task}"},
    ]

def generate(msgs, max_new_tokens=160):
    text = tokenizer.apply_chat_template(
        msgs, tokenize=False, add_generation_prompt=True, tools=None,
    )
    inputs = tokenizer(text, return_tensors="pt")
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=max_new_tokens, temperature=0.1, do_sample=True)
    return tokenizer.decode(out[0][inputs.input_ids.shape[1]:], skip_special_tokens=False)

def generate_action(msgs):
    return parse_actions(generate(msgs)), generate(msgs)

TOOL_NAME_MAP = {
    "navigate": "navigate", "goto": "navigate", "open": "navigate",
    "click": "click", "click_element": "click",
    "type": "type", "fill": "type", "input": "type",
    "select": "select", "select_option": "select",
    "extract": "extract", "get_text": "extract", "read": "extract",
    "scroll": "scroll", "wait": "wait", "sleep": "wait",
    "press_key": "press_key", "key_press": "press_key",
    "screenshot": "screenshot",
    "go_back": "go_back", "back": "go_back",
    "done": "done", "finish": "done", "complete": "done",
}

def clean_val(val):
    val = str(val).strip()
    val = val.split("<|im_end|>")[0].strip()
    val = val.strip(" '\"").strip()
    while val.endswith(")") and val.count(")") > val.count("("):
        val = val[:-1].strip()
    return val

def parse_actions(text):
    actions = []
    for m in re.finditer(r"<tool_call>(.*?)</tool_call>", text, re.DOTALL):
        try:
            data = json.loads(m.group(1).strip())
            fn = data.get("function", data)
            actions.append((fn.get("name", ""), fn.get("arguments", {})))
        except json.JSONDecodeError:
            pass
    if not actions:
        for m in re.finditer(r"\{[^{}]*\"name\"[^{}]*\}", text, re.DOTALL):
            try:
                data = json.loads(m.group(0))
                fn = data.get("function", data)
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    args = json.loads(args)
                actions.append((fn.get("name", ""), args))
            except json.JSONDecodeError:
                pass
    if not actions:
        for line in text.splitlines():
            line = line.strip().strip("`")
            if not line or line.startswith(("<", "```")):
                continue
            m = re.match(r"([A-Za-z_]+)[,:]?\s*(.*)", line)
            if not m:
                continue
            name_raw = m.group(1).lower()
            name = TOOL_NAME_MAP.get(name_raw, name_raw)
            rest = m.group(2)
            if name not in TOOL_NAME_MAP.values():
                continue
            args = {}
            if rest:
                for kv in re.findall(r"(\w+)\s*=\s*([^,\n]+)", rest):
                    args[kv[0].strip()] = clean_val(kv[1])
                if not args:
                    args = {"url": rest} if name == "navigate" else {"target": rest} if name == "click" else {"answer": clean_val(rest)} if name == "done" else {"text": rest}
            if name == "navigate" and "url" not in args and "http" in rest:
                args = {"url": rest.split()[0]}
            actions.append((name, args))
    return actions

def fix_selector(sel):
    sel = str(sel).strip()
    if sel.startswith("//") or sel.startswith("("):
        return "xpath=" + sel
    return sel

def run_tool(name, args, page):
    if name == "navigate":
        page.goto(args.get("url"), wait_until="domcontentloaded", timeout=30000)
        return f"Navigated to {args.get('url')}"
    elif name == "click":
        target = fix_selector(args.get("target") or args.get("selector") or args.get("text"))
        page.click(target, timeout=10000)
        return f"Clicked {target}"
    elif name == "type":
        sel, text = fix_selector(args.get("selector") or args.get("target")), args.get("text")
        if args.get("clear_first", True):
            page.fill(sel, text)
        else:
            page.type(sel, text)
        return f"Typed into {sel}"
    elif name == "select":
        page.select_option(fix_selector(args.get("selector")), args.get("value"))
        return f"Selected {args.get('value')}"
    elif name == "extract":
        content = page.inner_text(fix_selector(args.get("selector"))) if args.get("selector") else page.inner_text("body")
        return content[:800]
    elif name == "scroll":
        d = args.get("direction") or args.get("target") or "down"
        d = d.split("<|im_end|>")[0].strip()
        if d == "top": page.evaluate("window.scrollTo(0, 0);")
        elif d == "bottom": page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
        else:
            delta = "window.innerHeight" if d == "down" else "-window.innerHeight"
            page.evaluate(f"window.scrollBy(0, {delta});")
        return f"Scrolled {d}"
    elif name == "wait":
        time.sleep(args.get("ms", 1000) / 1000)
        return "Waited"
    elif name == "press_key":
        page.keyboard.press(args.get("key"))
        return f"Pressed {args.get('key')}"
    elif name == "screenshot":
        return "Screenshot taken"
    elif name == "go_back":
        page.go_back(wait_until="domcontentloaded", timeout=30000)
        return "Went back"
    elif name == "done":
        return "DONE:" + str(args.get("answer", ""))
    return f"Unknown tool {name}"

def screenshot_png(page):
    data = page.screenshot(type="png")
    return Image.open(io.BytesIO(data))

def page_context(page):
    try:
        title = page.title()
        body = page.inner_text("body")[:600]
        return f"Page title: {title}\nPage text:\n{body}"
    except Exception:
        return ""

def run_task(url, task, max_steps=6):
    page = get_page()
    last_nav = None
    shots = []
    log = []
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        last_nav = url
        shots.append(screenshot_png(page))
        log.append(f"OPEN {url}  (page loaded)")
    except Exception as e:
        return "\n".join([f"ERROR navigating: {e}"]), None

    msgs = [
        {"role": "system", "content": "You are a browser automation agent. Output tool-call lines only."},
        {"role": "user", "content": f"Task: Go to {url} and {task}"},
        {"role": "assistant", "content": f"navigate(url={url})"},
        {"role": "tool", "content": f"Page loaded: {url}\n{page_context(page)}", "name": "navigate"},
    ]

    for step in range(max_steps):
        raw = generate(msgs)
        log.append(f"--- step {step+1}: model said ---\n{raw[:300]}")
        actions = parse_actions(raw)
        if not actions:
            answer = raw.strip().strip("<|im_end|>").strip()
            if answer and "{url}" not in answer and "<tool" not in answer:
                log.append(f"FINAL ANSWER: {answer[:300]}")
                return "\n".join(log), shots
            log.append("(no action parsed)")
            break
        for name, args in actions:
            try:
                if name == "navigate":
                    dest = args.get("url")
                    if dest == last_nav:
                        result = f"Already on {dest}"
                    else:
                        result = run_tool(name, args, page)
                        last_nav = page.url
                else:
                    result = run_tool(name, args, page)
            except Exception as e:
                result = f"ERROR: {type(e).__name__}: {str(e)[:120]}"
            log.append(f">> {name}({json.dumps(args, ensure_ascii=False)}) -> {result[:150]}")
            msgs.append({"role": "assistant", "content": raw[:300]})
            if name == "done":
                answer = result[5:] if result.startswith("DONE:") else ""
                if not answer:
                    answer = last_result if 'last_result' in dir() else ""
                log.append(f"FINAL ANSWER: {answer[:300]}")
                shots.append(screenshot_png(page))
                return "\n".join(log), shots
            last_result = result
            msgs.append({"role": "tool", "content": result + "\n" + page_context(page), "name": name})
            try:
                shots.append(screenshot_png(page))
            except Exception:
                pass
    return "\n".join(log), shots

with gr.Blocks(title="SakThai Web Agent") as demo:
    gr.Markdown("# SakThai Web Agent")
    gr.Markdown("Real Playwright browser on a free CPU Space. The agent drives headless Chromium and shows live screenshots of every step.")
    with gr.Row():
        url = gr.Textbox(value="https://www.google.com", label="URL", scale=2)
        task = gr.Textbox(value="search for sakthai coder browser", label="Task", scale=3)
    btn = gr.Button("Run in Playwright", variant="primary")
    log_out = gr.Textbox(label="Agent log", lines=12)
    gallery = gr.Gallery(label="Browser screenshots (after each action)", columns=3, height=400)
    btn.click(fn=run_task, inputs=[url, task], outputs=[log_out, gallery])

demo.launch(show_error=True)
