import gradio as gr
import time
import re
from magi.core import MagiSystem

# Initialize System
magi_system = MagiSystem()

def is_japanese(text):
    """
    Simple check to see if text contains Japanese characters (Hiragana, Katakana, Kanji).
    """
    return bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', str(text)))

def get_status_html(status_text, reasoning_text=""):
    """
    Returns HTML for colored status text.
    Dynamic Language Switching:
    - If reasoning_text contains Japanese -> Display Japanese Label (承認, 否決, 保留)
    - If reasoning_text looks like English -> Display English Label (APPROVAL, DENIAL, RETENTION)
    """
    
    # Normalize input
    status_upper = str(status_text).upper()
    
    # Default to Japanese if no reasoning or if Japanese chars detected
    use_japanese = is_japanese(reasoning_text)
    
    label = status_text
    color = "gray"
    
    if "APPROVAL" in status_upper or "承認" in status_upper:
        label = "承認" if use_japanese else "APPROVAL"
        color = "#28a745" # Green
    elif "DENIAL" in status_upper or "否決" in status_upper:
        label = "否決" if use_japanese else "DENIAL"
        color = "#dc3545" # Red
    elif "RETENTION" in status_upper or "保留" in status_upper:
        label = "保留" if use_japanese else "RETENTION"
        color = "#ffc107" # Yellow
    elif "ERROR" in status_upper:
        label = "エラー" if use_japanese else "ERROR"
        color = "gray"
        
    return f"""<div style="text-align: center; font-size: 24px; font-weight: bold; color: {color}; border: 2px solid {color}; padding: 10px; border-radius: 8px; margin-bottom: 10px;">
        {label}
    </div>"""

def process_question(user_question):
    """
    Handler for Gradio UI.
    Simulates a step-by-step update for a better UX.
    """
    # Reset UI
    yield {
        status_box: "MAGI System Activated... / 起動中...",
        melchior_status: "...", melchior_reasoning: "...",
        balthasar_status: "...", balthasar_reasoning: "...",
        casper_status: "...", casper_reasoning: "...",
        verdict_status: "...", verdict_reasoning: "..."
    }
    
    try:
        result = magi_system.conduct_conference(user_question)
        responses = result["responses"]
        synthesis = result["synthesis"]
        
        # Helper to safely get data
        m_data = responses.get("Melchior", {"status": "Error", "reasoning": "Error"})
        b_data = responses.get("Balthasar", {"status": "Error", "reasoning": "Error"})
        c_data = responses.get("Casper", {"status": "Error", "reasoning": "Error"})
        
        # Parse Synthesis
        if isinstance(synthesis, dict):
            v_data = synthesis
        else:
            v_data = {"status": "Unknown", "reasoning": str(synthesis)}

        # Step 1: Melchior answers
        yield {
            status_box: "MELCHIOR (Scientist) is proposing...",
            melchior_status: get_status_html(m_data["status"], m_data["reasoning"]),
            melchior_reasoning: m_data["reasoning"],
            balthasar_status: "...", balthasar_reasoning: "...",
            casper_status: "...", casper_reasoning: "...",
            verdict_status: "...", verdict_reasoning: "..."
        }
        time.sleep(1)
        
        # Step 2: Balthasar answers
        yield {
            status_box: "BALTHASAR (Mother) is proposing...",
            melchior_status: get_status_html(m_data["status"], m_data["reasoning"]),
            melchior_reasoning: m_data["reasoning"],
            balthasar_status: get_status_html(b_data["status"], b_data["reasoning"]),
            balthasar_reasoning: b_data["reasoning"],
            casper_status: "...", casper_reasoning: "...",
            verdict_status: "...", verdict_reasoning: "..."
        }
        time.sleep(1)
        
        # Step 3: Casper answers
        yield {
            status_box: "CASPER (Woman) is proposing...",
            melchior_status: get_status_html(m_data["status"], m_data["reasoning"]),
            melchior_reasoning: m_data["reasoning"],
            balthasar_status: get_status_html(b_data["status"], b_data["reasoning"]),
            balthasar_reasoning: b_data["reasoning"],
            casper_status: get_status_html(c_data["status"], c_data["reasoning"]),
            casper_reasoning: c_data["reasoning"],
            verdict_status: "...", verdict_reasoning: "..."
        }
        time.sleep(1)
        
        # Step 4: Synthesis
        yield {
            status_box: "MAGI System Synthesis Complete.",
            melchior_status: get_status_html(m_data["status"], m_data["reasoning"]),
            melchior_reasoning: m_data["reasoning"],
            balthasar_status: get_status_html(b_data["status"], b_data["reasoning"]),
            balthasar_reasoning: b_data["reasoning"],
            casper_status: get_status_html(c_data["status"], c_data["reasoning"]),
            casper_reasoning: c_data["reasoning"],
            verdict_status: get_status_html(v_data["status"], v_data["reasoning"]),
            verdict_reasoning: v_data["reasoning"]
        }
        
    except Exception as e:
        error_html = get_status_html("ERROR")
        yield {
            status_box: f"System Error: {str(e)}",
            melchior_status: error_html, melchior_reasoning: str(e),
            balthasar_status: error_html, balthasar_reasoning: str(e),
            casper_status: error_html, casper_reasoning: str(e),
            verdict_status: error_html, verdict_reasoning: str(e)
        }

# UI Layout
with gr.Blocks(title="MAGI System v2.2", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🧠 MAGI System v2.2")
    gr.Markdown("Concept by PhenoX. Supported by Gemi.")
    
    with gr.Row():
        user_input = gr.Textbox(label="User Question / ユーザーへの質問", placeholder="Ask the council a question... / MAGIに問いたいことを入力してください...", lines=2)
        submit_btn = gr.Button("Initialize MAGI / MAGIシステム起動", variant="primary")
    
    status_box = gr.Markdown("**Status**: Ready")
    
    with gr.Row():
        # MELCHIOR
        with gr.Column(variant="panel"):
            gr.Markdown("### 🟦 MELCHIOR (Scientist)")
            melchior_status = gr.HTML(get_status_html("READY"))
            with gr.Accordion("Detailed Reasoning / 詳細プロセス", open=False):
                melchior_reasoning = gr.Markdown("...")
            
        # BALTHASAR
        with gr.Column(variant="panel"):
            gr.Markdown("### 🟧 BALTHASAR (Mother)")
            balthasar_status = gr.HTML(get_status_html("READY"))
            with gr.Accordion("Detailed Reasoning / 詳細プロセス", open=False):
                balthasar_reasoning = gr.Markdown("...")
            
        # CASPER
        with gr.Column(variant="panel"):
            gr.Markdown("### 🟥 CASPER (Woman)")
            casper_status = gr.HTML(get_status_html("READY"))
            with gr.Accordion("Detailed Reasoning / 詳細プロセス", open=False):
                casper_reasoning = gr.Markdown("...")

    # VERDICT (Final Judge)
    with gr.Row():
        with gr.Column(variant="panel"):
            gr.Markdown("### 🗳️ Final Verdict / 最終合議結果")
            verdict_status = gr.HTML(get_status_html("READY"))
            with gr.Accordion("Detailed Reasoning / 詳細プロセス", open=False):
                verdict_reasoning = gr.Markdown("...")

    submit_btn.click(
        process_question, 
        inputs=[user_input], 
        outputs=[
            status_box, 
            melchior_status, melchior_reasoning,
            balthasar_status, balthasar_reasoning,
            casper_status, casper_reasoning,
            verdict_status, verdict_reasoning
        ]
    )

if __name__ == "__main__":
    from magi.config import APP_USERNAME, APP_PASSWORD
    
    auth = None
    if APP_USERNAME and APP_PASSWORD:
        auth = (APP_USERNAME, APP_PASSWORD)
    
    # Enable public link
    demo.launch(share=True, auth=auth)
