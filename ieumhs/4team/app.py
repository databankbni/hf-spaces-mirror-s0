import gradio as gr
import random

# ==========================================
# 2~4단계: 백엔드 로직 (전처리, 추론, CDA 기반 설명)
# ==========================================

def analyze_climate_text(user_input):
    """
    사용자가 입력한 기후변화 관련 뉴스 문장을 분석하는 가상의 AI 파이프라인
    """
    if not user_input.strip():
        return (
            "⚠️ 입력된 텍스트가 없습니다. 문장을 입력해 주세요.", 
            "텍스트를 입력해야 분석이 가능합니다.", 
            "N/A"
        )
    
    # [2단계] 텍스트 전처리 (간단한 토큰화 예시)
    tokens = user_input.split()
    
    # [3단계] LoRA 모델 추론 시뮬레이션 (위험도 확률 계산)
    # 실제 환경에서는 model(tokenizer(user_input)) 형태로 호출됩니다.
    # 기후변화 관련 특정 키워드가 들어있으면 높은 위험도(부정/과장/왜곡)를 유도하도록 세팅
    danger_keywords = ["음모", "조작", "사기", "빙하기", "거짓", "선동", "폭락", "멸망", "끝났다"]
    has_danger_word = any(keyword in user_input for keyword in danger_keywords)
    
    if has_danger_word:
        danger_probability = random.randint(70, 95)  # 위험 확률 높음
    else:
        danger_probability = random.randint(10, 45)  # 위험 확률 낮음
        
    # [4단계] 팀 설계 로직 결과 해석 (XAI - CDA 기반 영향 단어 추출)
    # 문장 내에서 판정에 가장 큰 영향을 준 단어와 가중치 방향(↑, ↓)을 분석
    influence_words = []
    for token in tokens:
        # 깨끗한 단어 정제
        clean_token = token.strip(".,!?\"' ")
        if clean_token in danger_keywords:
            influence_words.append(f"\"{clean_token}\" → 🔺 (위험 유발)")
        elif len(clean_token) >= 2 and hash(clean_token) % 5 == 0: 
            # 해시값을 활용해 형태소 분석기 없이도 일관된 영향 단어 매핑 시뮬레이션
            influence_words.append(f"\"{clean_token}\" → 🔻 (중립/완화)")
            
    # 영향 단어가 전혀 검출되지 않았을 때의 기본값 처리
    if not influence_words and tokens:
        influence_words.append(f"\"{tokens[0]}\" → 🟡 (영향 미미)")
        
    cda_result = ", ".join(influence_words[:3]) # 최대 3개 출력
    
    # [5단계] 결과 판정 및 오판 신고(이의 제기)를 위한 안내
    # 위험도 확률에 따른 판정 이모지 및 텍스트
    if danger_probability >= 70:
        judgment = f"🔴 {danger_probability}% (높은 왜곡/과장 위험)"
    elif danger_probability >= 40:
        judgment = f"🟡 {danger_probability}% (주의 필요)"
    else:
        judgment = f"🟢 {danger_probability}% (안전/신뢰 가능)"
        
    # 한계 고지 (Model Card §5, §6 기반)
    limitation_text = (
        "※ 본 판정은 기후변화 뉴스 데이터셋으로 파인튜닝된 LoRA 모델의 정량적 추론 결과입니다. "
        "정황적 맥락이 누락되었거나 신조어가 포함된 경우 분석이 부정확할 수 있습니다."
    )
    
    return judgment, cda_result, limitation_text


# ==========================================
# 1, 5단계: Gradio 웹 UI 구성 (UI 스케치 완벽 반영)
# ==========================================

# HuggingFace에 어울리는 세련된 테마 적용
theme = gr.themes.Soft(
    primary_hue="red",       # 스케치 핵심 컬러(🔴) 반영
    secondary_hue="slate",
    neutral_hue="slate"
)

with gr.Blocks(theme=theme, title="래빗홀 탈출 AI") as demo:
    
    # 헤더 섹션
    gr.Markdown(
        """
        # 🐰 래빗홀 탈출 AI (기후변화 뉴스 검증)
        기후변화와 관련된 뉴스 문장을 입력하면, AI가 왜곡·과장·음모론적 요소를 실시간으로 탐지하고 판정 근거를 설명해 줍니다.
        """
    )
    
    with gr.Column():
        # [1단계] 사용자 입력 (M1 I)
        user_input = gr.Textbox(
            label="① 검증할 뉴스 문장 입력",
            placeholder="예시: 기후변화는 대기업들이 탄소세를 걷기 위해 꾸며낸 사기극에 불과하다.",
            lines=3
        )
        
        # 분석 실행 버튼
        submit_btn = gr.Button("⚡ [분석하기]", variant="primary")
        
        # [5단계] 결과 출력부 (UI 스케치의 그리드 구조 그대로 구현)
        with gr.Row():
            # ② 판정 결과
            judgment_output = gr.Textbox(
                label="② 판정 결과",
                placeholder="분석 대기 중...",
                interactive=False
            )
            # ③ 판단 근거 (XAI)
            cda_output = gr.Textbox(
                label="③ 판단 근거 (영향 단어)",
                placeholder="분석 대기 중...",
                interactive=False
            )
            
        # ④ 한계 + 이의 제기 창
        with gr.Row():
            limitation_output = gr.Textbox(
                label="④ 시스템 한계 고지",
                placeholder="모델 카드의 한계 사항이 표시됩니다.",
                interactive=False,
                scale=3
            )
            
            # 오판 신고 (이의제기) 인터랙션 기능 추가
            report_btn = gr.Button("⚠️ [오판 신고 / 이의 제기]", variant="stop", scale=1)

    # ------------------------------------------
    # 컴포넌트 이벤트 연결
    # ------------------------------------------
    
    # 1) [분석하기] 클릭 시 실행되는 파이프라인
    submit_btn.click(
        fn=analyze_climate_text,
        inputs=[user_input],
        outputs=[judgment_output, cda_output, limitation_output]
    )
    
    # 엔터키를 눌렀을 때도 동일하게 분석하도록 설정
    user_input.submit(
        fn=analyze_climate_text,
        inputs=[user_input],
        outputs=[judgment_output, cda_output, limitation_output]
    )
    
    # 2) [오판 신고] 클릭 시 팝업/알림 설정
    def trigger_report():
        return gr.Info("🚨 신고가 접수되었습니다. 해당 데이터는 향후 모델 재학습(M3 9차시 업데이트)에 적극 반영됩니다.")
        
    report_btn.click(fn=trigger_report, inputs=None, outputs=None)

# HuggingFace 배포용 실행 코드
if __name__ == "__main__":
    demo.launch()
