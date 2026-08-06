import gradio as gr
import requests
import uuid
import time
import json

# --- CONFIGURATION ---
API_URL = "" 

def process_sentinel_request(user_id, amount, category):
    tx_id = f"tx_{str(uuid.uuid4())[:8]}"
    
    if API_URL:
        try:
            payload = {
                "transaction_id": tx_id,
                "user_id": user_id,
                "amount": amount,
                "merchant_category": category
            }
            response = requests.post(f"{API_URL}/api/v1/transactions", json=payload, timeout=3)
            if response.status_code == 202:
                success_log = {
                    "status": "SUCCESS",
                    "backend": "AWS EKS (Live)",
                    "transaction_id": tx_id,
                    "message": "Ingested to Kafka successfully"
                }
                return json.dumps(success_log, indent=2)
        except requests.exceptions.RequestException:
            pass 

    # --- FINOPS DEMO MODE ---
    time.sleep(0.8)
    risk_score = 0.92 if amount > 5000 or category == "crypto" else 0.05
    status = "REJECTED (High Risk)" if risk_score > 0.8 else "APPROVED (Low Risk)"
    
    demo_output = {
        "mode": "SENTINEL FINOPS DEMO MODE",
        "backend_status": "Dormant (Cost Optimized: $0/hr)",
        "transaction_id": tx_id,
        "ml_risk_score": risk_score,
        "action": status,
        "note": "UI is currently decoupled from the main AWS cluster to demonstrate the architecture without incurring cloud costs."
    }
    return json.dumps(demo_output, indent=2)

# --- GRADIO UI DESIGN ---
custom_theme = gr.themes.Default(
    primary_hue=gr.themes.colors.slate,
    secondary_hue=gr.themes.colors.gray,
    neutral_hue=gr.themes.colors.gray,
).set(
    body_text_color="#333333",
    block_title_text_weight="bold",
    block_title_text_color="#1B2631",
    button_primary_background_fill="#1B2631",
    button_primary_text_color="white",
)

with gr.Blocks(title="Sentinel Fraud Gateway", theme=custom_theme) as demo:
    gr.Markdown("""
    # Sentinel: Enterprise Fraud Detection Gateway
    ### High-Throughput ML Ingestion Pipeline (Go, Kafka, Kubernetes)
    """)
    
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### Input Transaction Data")
            u_id = gr.Textbox(label="User Identifier", placeholder="user_12345", value="user_demo")
            amt = gr.Number(label="Transaction Amount (USD)", value=1250.00)
            cat = gr.Dropdown(choices=["retail", "crypto", "gaming", "travel"], label="Category", value="retail")
            btn = gr.Button("Submit to Sentinel Ingestion", variant="primary")
            
        with gr.Column(scale=1):
            gr.Markdown("### Ingestion Pipeline Output")
            output = gr.Code(label="System Logs", language="json", interactive=False)

    btn.click(fn=process_sentinel_request, inputs=[u_id, amt, cat], outputs=output)
    
    gr.Markdown("---")
    gr.Markdown("""
    ### Enterprise and FinOps Metrics
    * **Extreme Throughput:** Handled **25,300+ RPS** with **~7ms** latency and 0% error rate during aggressive load testing.
    * **Cost Optimization (FinOps):** Production architecture estimated at only **$107/month** on AWS (leveraging Spot Instances and efficient resource mapping).
    * **Resilience:** Fully decoupled ingestion via Redpanda (Kafka) ensures zero data loss during traffic spikes.
    
    Created by **Enes Guler** | Check the full [Architecture and FinOps Report on GitHub](https://github.com/enesgulerdev/sentinel)
    """)

demo.launch()