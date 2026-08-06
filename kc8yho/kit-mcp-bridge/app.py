"""
Kit MCP Bridge - Hugging Face Space
Connects to Kaylasoft Kit MCP1 (6699+ tools) and MCP2 (6597+ tools) servers.
"""
import gradio as gr
import requests
import json
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MCP1_URL = os.environ.get("KIT_MCP1_URL", "https://kc8yho.com/mcp")
MCP2_URL = os.environ.get("KIT_MCP2_URL", "https://kc8yho.com/kit/mcp2")
KIT_AUTH = os.environ.get("KIT_AUTH_TOKEN", "KitBase44InternalService2026Xq!")

HEADERS = {
    "Content-Type": "application/json",
    "X-Kit-Auth": KIT_AUTH,
}

TIMEOUT = 30

def call_mcp1(method, params=None):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    try:
        resp = requests.post(f"{MCP1_URL}/mcp", json=payload, headers=HEADERS, timeout=TIMEOUT)
        return resp.json()
    except Exception as e:
        return {"error": {"code": -32603, "message": str(e)}}

def kit_bridge(action, tool_name, arguments_json):
    """Main bridge function."""
    if action == "status":
        results = []
        for name, url in [("MCP1", MCP1_URL), ("MCP2", MCP2_URL)]:
            try:
                resp = requests.get(f"{url}/health", headers=HEADERS, timeout=10)
                data = resp.json()
                results.append(f"{name}: OK v{data.get('version', '?')} - {data.get('tools', '?')} tools")
            except Exception as e:
                results.append(f"{name}: ERROR {str(e)[:80]}")
        return "\n".join(results)
    elif action == "list":
        result = call_mcp1("tools/list")
        if "result" in result:
            tools = result["result"].get("tools", [])
            tool_names = [t.get("name", "") for t in tools]
            return f"{len(tools)} tools available:\n\n" + "\n".join(f"- {n}" for n in tool_names[:50])
        return f"Error: {result.get('error', 'unknown')}"
    elif action == "execute":
        try:
            args = json.loads(arguments_json) if arguments_json else {}
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}"
        result = call_mcp1("tools/call", {"name": tool_name, "arguments": args})
        if "result" in result:
            content = result["result"].get("content", [])
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            return "\n".join(texts) if texts else json.dumps(result["result"], indent=2)
        return f"Error: {json.dumps(result.get('error', 'unknown'), indent=2)}"
    return "Unknown action"

demo = gr.Interface(
    fn=kit_bridge,
    inputs=[
        gr.Dropdown(choices=["status", "list", "execute"], label="Action", value="status"),
        gr.Textbox(label="Tool Name (for execute)", placeholder="kit_gpu_infer"),
        gr.Textbox(label="Arguments JSON (for execute)", placeholder='{"prompt":"Hello"}', lines=3),
    ],
    outputs=gr.Textbox(label="Result", lines=20),
    title="Kit MCP Bridge - Kaylasoft Solutions",
    description="Connects to Kit MCP1 (6699+ tools) and MCP2 (6597+ tools). Actions: status, list, execute.",
)

demo.launch()
