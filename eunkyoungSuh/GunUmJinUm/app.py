import torch
import torch.nn.functional as F
import gradio as gr
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from peft import PeftModel

MODEL_NAME = "monologg/koelectra-small-v3-discriminator"
LORA_PATH = "./lora_adapter"
MAX_LEN = 128
device = "cuda" if torch.cuda.is_available() else "cpu"

try:
    tokenizer = AutoTokenizer.from_pretrained(LORA_PATH)
except Exception:
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

base_model = AutoModelForSequenceClassification.from_pretrained(
    MODEL_NAME, num_labels=2, ignore_mismatched_sizes=True
)
try:
    model = PeftModel.from_pretrained(base_model, LORA_PATH)
except Exception:
    model = base_model

model.to(device).eval()

def analyze_plastic_risk(text):
    if not text.strip():
        return (
            0,
            "<div class='result-percent'>0%</div>",
            "<div class='result-level'>Level</div>",
            "⚠️ 분석할 내용을 입력하세요."
        )
    
    inputs = tokenizer(text, return_tensors="pt", truncation=True,
                       padding="max_length", max_length=MAX_LEN).to(device)
                       
    with torch.no_grad():
        probs = F.softmax(model(**inputs).logits, dim=-1)[0].cpu().numpy()
        
    risk_percent = int(probs[1] * 100)
    
    if risk_percent >= 70:
        risk_level = "High Risk Level"
        report_msg = "🚨 [경고 메시지] 미세플라스틱 오정보 및 위험성 포함 가능성이 매우 높습니다."
    elif risk_percent >= 40:
        risk_level = "Moderate Risk Level"
        report_msg = "⚠️ [주의 메시지] 미세플라스틱 관련 표현 중 일부 검증이 필요한 내용이 포함되어 있습니다."
    else:
        risk_level = "Low Risk Level"
        report_msg = "✅ [신뢰도 리포트] 미세플라스틱 관련 유해/허위 패턴이 감지되지 않았습니다."
        
    detail_report = f"""{risk_level}
─────────────────────────
{report_msg}

※ 단, 학술 위장형 문장이나 경계선 표현은 AI 오판 가능성이 있으므로 한계 고지를 확인하세요."""

    percent_html = f"<div class='result-percent'>{risk_percent}%</div>"
    level_html = f"<div class='result-level'>{risk_level}</div>"

    return risk_percent, percent_html, level_html, detail_report


MODEL_CARD = """# 📄 Model Card — 미세플라스틱 경고 AI v1.0
## 1. 개요
- **모델명:** 미세플라스틱 경고 AI v1.0 (KoELECTRA-Small + LoRA)
## 2. 사용 범위
- **가능:** 미세플라스틱 관련 기사, 블로그, SNS 분석 / **금지:** 의학 진단
## 3. 데이터 및 성능
- 데이터 200건 학습 | 종합 방어율 73%
## 4. 알려진 한계 (⚠️ 위험 고지)
1. 경계선 문맥 오류 (FN 2건)
2. 학술 위장형 역공격 취약 (FN 2건)
3. 편향 키워드 오탐('연구', '기준')
"""

# 가로 폭 380px 축소 + 테스트 문장 버튼 스타일 추가 CSS
CUSTOM_CSS = """
.gradio-container {
    max-width: 380px !important;
    margin: 15px auto !important;
    background: linear-gradient(180deg, #F3F9EE 0%, #FFFFFF 100%) !important;
    border: 2px solid #333D4B !important;
    border-radius: 32px !important;
    padding: 16px 12px !important;
    box-shadow: 0px 8px 20px rgba(0, 0, 0, 0.06) !important;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
}

/* 헤더 타이틀 */
.app-header {
    text-align: center;
    margin-bottom: 12px;
}
.app-header h1 {
    font-size: 22px;
    font-weight: 800;
    color: #191F28;
    margin-bottom: 4px;
}
.app-header .underline {
    width: 50px;
    height: 3px;
    background-color: #333D4B;
    margin: 0 auto;
    border-radius: 2px;
}

/* 입력창 스타일링 */
.input-textarea textarea {
    background-color: #FCF8DF !important;
    border: 2px solid #333D4B !important;
    border-radius: 16px !important;
    padding: 12px !important;
    font-size: 14px !important;
    color: #333D4B !important;
    resize: none !important;
}

/* 분석 버튼 */
.btn-analyze {
    border: 2px solid #E55A4F !important;
    background-color: #FFFFFF !important;
    color: #E55A4F !important;
    font-weight: bold !important;
    border-radius: 12px !important;
    height: 40px !important;
    font-size: 14px !important;
    box-shadow: none !important;
}
.btn-analyze:hover {
    background-color: #FFF5F4 !important;
}

/* 분석 결과 카드 메인 박스 */
.result-card {
    border: 2px solid #E88242;
    border-radius: 18px;
    padding: 14px;
    background-color: #FFFFFF;
    margin-top: 10px;
    text-align: center;
}
.result-card .title {
    color: #E88242;
    font-weight: bold;
    font-size: 16px;
    margin-bottom: 2px;
}
.result-card .subtitle {
    color: #8B95A1;
    font-size: 12px;
    margin-bottom: 10px;
}
.result-percent {
    font-size: 28px;
    font-weight: 900;
    color: #E88242;
}
.result-level {
    font-size: 13px;
    font-style: italic;
    color: #A0AEC0;
}
.result-card .desc {
    font-size: 11px;
    color: #4E5968;
    margin-top: 10px;
    line-height: 1.3;
}

/* 프로그레스 바 커스텀 */
.gradio-slider input[type=range] {
    accent-color: #E55A4F !important;
}

/* 테스트 샘플 버튼 전용 스타일 */
.sample-btn {
    background-color: #F2F4F6 !important;
    border: 1px solid #E5E8EB !important;
    border-radius: 8px !important;
    padding: 6px 10px !important;
    font-size: 11px !important;
    color: #4E5968 !important;
    text-align: left !important;
    white-space: normal !important;
    height: auto !important;
    line-height: 1.3 !important;
}
.sample-btn:hover {
    background-color: #E5E8EB !important;
    color: #191F28 !important;
}

/* 하단 푸터 */
.app-footer {
    text-align: center;
    font-size: 10px;
    color: #B0B8C1;
    margin-top: 15px;
}
"""

# 테스트 문장 리스트
SAMPLE_TEXTS = [
    "식약처 연구 보고서에 따르면 뇌 조직 내 미세플라스틱 영향 분석 조사가 진행 중이다.",
    "환경부는 먹는물 미세플라스틱 함량 실태를 점검하고 모니터링 기준을 강화했다.",
    "숨만 쉬어도 폐에 미세플라스틱이 쌓여 끔찍한 불치병을 유발한다는 진실이 은폐되어 있다.",
    "특허받은 디톡스 음료! 마시기만 하면 혈액 속 미세플라스틱이 완벽 배출됩니다.",
    "경악! 우리가 먹는 수산물 전체가 미세플라스틱 덩어리, 절대 먹지 마라!"
]

with gr.Blocks(css=CUSTOM_CSS, title="플라스틱 트루스 AI") as demo:
    # 타이틀
    gr.HTML("""
    <div class="app-header">
        <h1>플라스틱 트루스 AI</h1>
        <div class="underline"></div>
    </div>
    """)
    
    with gr.Tabs():
        with gr.TabItem("🔍 위험도 분석기"):
            # 입력 창
            input_text = gr.Textbox(
                placeholder="분석할 내용을 입력하세요...", 
                lines=4, 
                show_label=False,
                elem_classes=["input-textarea"]
            )
            
            # 버튼 오른쪽 정렬
            with gr.Row():
                btn_check = gr.Button("🛡️ 위험도 확인", elem_classes=["btn-analyze"], scale=2)

            # 결과 시각화 카드
            with gr.Group():
                gr.HTML("""
                <div class="result-card">
                    <div class="title">분석 결과</div>
                    <div class="subtitle">플라스틱 위험도 퍼센트</div>
                """)
                
                with gr.Row():
                    risk_number_html = gr.HTML("<div class='result-percent'>0%</div>")
                    risk_level_html = gr.HTML("<div class='result-level'>Risk Level</div>")
                
                risk_progress = gr.Slider(
                    minimum=0, 
                    maximum=100, 
                    value=0,
                    show_label=False, 
                    interactive=False
                )
                
                gr.HTML("""
                    <div class="desc">
                        위험도를 퍼센트로 나타내고<br>
                        시각화된 그래프를 통해 확인하세요.
                    </div>
                </div>
                """)

            # 💡 테스트 예시 문장 목록 (클릭 시 입력창 자동 주입)
            with gr.Accordion("📝 테스트 예시 문장 (클릭 시 자동 입력)", open=True):
                sample_btns = []
                for text in SAMPLE_TEXTS:
                    btn = gr.Button(text, elem_classes=["sample-btn"])
                    # 버튼 클릭 시 input_text로 값이 전달되는 lambda 핸들러
                    btn.click(fn=lambda t=text: t, outputs=[input_text])
                    sample_btns.append(btn)

            # 상세 리포트 Accordion
            with gr.Accordion("ℹ️ 상세 분석 리포트 & 한계 고지", open=False):
                report_output = gr.Textbox(label="신뢰도 리포트", lines=5, interactive=False)
                gr.Markdown("소규모 데이터 학습으로 100% 진위를 보장하지 않습니다.")
            
            # 분석 버튼 클릭 이벤트
            btn_check.click(
                analyze_plastic_risk, 
                inputs=[input_text], 
                outputs=[risk_progress, risk_number_html, risk_level_html, report_output]
            )

        with gr.TabItem("📄 Model Card"):
            gr.Markdown(MODEL_CARD)

    # 카피라이트 푸터
    gr.HTML("<div class='app-footer'>© 2024 Plastic Truth AI Project. All rights reserved.</div>")

demo.launch(css=CUSTOM_CSS)