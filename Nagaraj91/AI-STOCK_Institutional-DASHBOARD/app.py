import gradio as gr
from dashboard_models import DashboardInsights
from agent import run_dashboard_workflow
from services.ticker_resolver import resolve_tickers
from services.chart_builder import create_candlestick_chart, create_gauge_chart, create_scenario_bar_chart, create_overlap_heatmap
from services.overlap_calculator import calculate_overlap
from langchain_core.messages import HumanMessage
import json
import os
from dotenv import load_dotenv
import logging
import yfinance as yf

# Suppress yfinance internal HTTP 404 warnings from printing to terminal
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

load_dotenv()

def format_overlap_markdown(overlap_data):
    md = "### Pairwise Overlap Details\n\n"
    for pair in overlap_data["pairwise_overlaps"]:
        md += f"**{pair['fund_a']}** & **{pair['fund_b']}**: `{pair['overlap_percentage']}%` Overlap\n\n"
        
        if pair['common_stocks']:
            md += "| Stock | Weight in A | Weight in B | Overlap |\n"
            md += "|---|---|---|---|\n"
            # Show top 10 overlapping stocks
            for stock in pair['common_stocks'][:10]:
                md += f"| {stock['stock']} | {stock['weight_a']:.2f}% | {stock['weight_b']:.2f}% | {stock['overlap']:.2f}% |\n"
            md += "\n"
        else:
            md += "*No common stocks found or data unavailable.*\n\n"
    return md

def run_analysis(query: str, model_type: str, progress=gr.Progress()):
    if not query:
        raise gr.Error("Please enter a company name or query.")
        
    progress(0.1, desc="Understanding request & resolving tickers...")
    tickers = resolve_tickers(query, model_type)
    
    if not tickers:
        raise gr.Error("Could not resolve any valid tickers.")
        
    # ROUTING LOGIC
    is_comparison = len(tickers) > 1
    
    if is_comparison:
        # COMPARISON MODE
        progress(0.4, desc="Fetching Mutual Fund Holdings...")
        overlap_data = calculate_overlap(tickers)
        
        if "error" in overlap_data:
            raise gr.Error(overlap_data["error"])
            
        progress(0.8, desc="Building Overlap Visualizations...")
        heatmap = create_overlap_heatmap(overlap_data)
        overlap_md = format_overlap_markdown(overlap_data)
        
        header = f"<div style='padding:20px; text-align:center;'><h2>Portfolio Comparison Mode</h2><p>Analyzing {len(tickers)} funds</p></div>"
        
        # Return Single=False, Compare=True, Empty Single Outputs, Filled Compare Outputs
        return (
            gr.update(visible=False), gr.update(visible=True), # Groups
            gr.update(value=""), None, None, None, None, # Single Top
            gr.update(value=""), gr.update(value=""), gr.update(value=""), gr.update(value=""), # Tabs 1-4
            gr.update(value=""), gr.update(value=""), gr.update(value=""), gr.update(value=""), # Tabs 5-8
            gr.update(value=""), gr.update(value=""), gr.update(value=""), gr.update(value=""), # Tabs 9-12
            gr.update(value=""), # Tab 13
            header, heatmap, overlap_md # Compare Outputs
        )
        
    else:
        # SINGLE ASSET MODE
        ticker = list(tickers.values())[0]
        progress(0.3, desc=f"Fetching live market data for {ticker}...")
        initial_state = {
            "messages": [HumanMessage(content=ticker)],
            "model_type": model_type
        }
        
        try:
            progress(0.5, desc="Running fundamental & technical analysis...")
            raw_data, insights = run_dashboard_workflow(ticker, model_type)
            
            progress(0.9, desc="Building interactive visualizations...")
            
            # Setup raw data variables
            tech = raw_data.get('technicals', {})
            fund = raw_data.get('fundamentals', {})
            val = raw_data.get('valuation', {})
            scores = raw_data.get('scores', {})
            news = raw_data.get('news', [])
            
            company_name = yf.Ticker(ticker).info.get('longName', ticker)
            
            color = "green" if insights.summary.action == "BUY" else "red" if insights.summary.action == "SELL" else "orange"
            header_html = f"""
            <div style="padding: 20px; border-radius: 10px; text-align: center;">
                <h1 style="margin: 0; font-size: 32px;">{company_name} <span style="color: gray;">({ticker})</span></h1>
                <h2 style="margin: 10px 0; font-size: 24px;">AI Recommendation: <span style="color: {color};">{insights.summary.action}</span></h2>
                <p style="font-size: 18px; opacity: 0.8;">Risk Level: {insights.summary.risk_level} | Expected Return: {insights.summary.expected_return}</p>
            </div>
            """
            
            price_chart = create_candlestick_chart(ticker)
            score_gauge = create_gauge_chart(scores.get('overall_score', 50), "Overall AI Score")
            confidence_gauge = create_gauge_chart(insights.summary.confidence, "AI Confidence (%)")
            
            # Derive basic scenarios from technical support/resistance
            scenarios = {
                "Bear Case (Support)": tech.get('support_1', 0),
                "Base Case (Current)": tech.get('current_price', 0),
                "Bull Case (Resistance)": tech.get('resistance_1', 0)
            }
            scenario_chart = create_scenario_bar_chart(scenarios)
            
            mofs = val.get("margin_of_safety", 0) * 100
            
            summary_md = f"**Action Plan:** {insights.summary.action_plan}\n\n**Intrinsic Value:** {val.get('dcf_intrinsic_value', 0):.2f}\n\n**Margin of Safety:** {mofs:.2f}%"
            tech_md = f"**Trend:** {insights.technical.trend}\n\n**Support:** {tech.get('support_1', 0):.2f}\n\n**Resistance:** {tech.get('resistance_1', 0):.2f}\n\n**Pattern:** {insights.technical.pattern_recognition}\n\n---\n\n### 🧠 AI Interpretation\n{insights.technical.ai_interpretation}\n\n### 🎓 Learn\n{insights.technical.educational_note}"
            fund_md = f"### 🧠 AI Interpretation\n{insights.fundamental.ai_interpretation}\n\n### 🎓 Learn\n{insights.fundamental.educational_note}"
            health_md = f"**Health Score:** {scores.get('health_score', 0):.1f}/100\n\n**Cash Flow Health:** {insights.health.cash_flow_health}\n\n**Debt Trend:** {insights.health.debt_trend}\n\n---\n\n### 🧠 AI Interpretation\n{insights.health.ai_interpretation}\n\n### 🎓 Learn\n{insights.health.educational_note}"
            growth_md = f"**Forecast:** {insights.growth.forecast}\n\n---\n\n### 🧠 AI Interpretation\n{insights.growth.ai_interpretation}\n\n### 🎓 Learn\n{insights.growth.educational_note}"
            val_md = f"**Fair Value:** {val.get('dcf_intrinsic_value', 0):.2f}\n\n**Status:** {insights.valuation.valuation_status}\n\n---\n\n### 🧠 AI Interpretation\n{insights.valuation.ai_interpretation}\n\n### 🎓 Learn\n{insights.valuation.educational_note}"
            own_md = f"**Promoter Trend:** {insights.ownership.promoter_trend}\n\n**Institutional Trend:** {insights.ownership.institutional_trend}\n\n---\n\n### 🧠 AI Interpretation\n{insights.ownership.ai_interpretation}\n\n### 🎓 Learn\n{insights.ownership.educational_note}"
            news_content = "\n- ".join(news) if news else "No recent news available."
            news_md = f"**Sentiment:** {insights.news.sentiment}\n\n**Recent Headlines:**\n- {news_content}\n\n### 🧠 AI Summary\n{insights.news.ai_summary}"
            sec_md = f"**Industry Outlook:** {insights.sector.industry_outlook}\n\n**Macro Trends:** {insights.sector.macro_trends}\n\n---\n\n### 🧠 AI Interpretation\n{insights.sector.ai_interpretation}"
            risk_md = f"**Top Risks:**\n- " + "\n- ".join(insights.risk.top_risks) + f"\n\n**Mitigation:** {insights.risk.mitigation}\n\n### 🎓 Learn\n{insights.risk.educational_note}"
            
            peer_list = "\n- ".join(insights.peer.competitors) if insights.peer.competitors else "No direct competitors identified in this data."
            peer_md = f"**Identified Competitors:**\n- {peer_list}\n\n### 🧠 AI Interpretation\n{insights.peer.ai_interpretation}"
            scen_md = f"### 🎓 Learn\n{insights.scenario.educational_note}"
            reas_md = f"### ✅ Positive Factors\n- " + "\n- ".join(insights.reasoning.positive_factors) + f"\n\n### ❌ Negative Factors\n- " + "\n- ".join(insights.reasoning.negative_factors) + f"\n\n### ➖ Neutral Factors\n- " + "\n- ".join(insights.reasoning.neutral_factors) + f"\n\n### 🌳 Decision Tree\n{insights.reasoning.decision_tree}"
            
            return (
                gr.update(visible=True), gr.update(visible=False), # Groups
                header_html, price_chart, score_gauge, confidence_gauge, scenario_chart, # Top
                summary_md, tech_md, fund_md, health_md, growth_md, val_md, own_md, # Tabs 1-7
                news_md, sec_md, risk_md, peer_md, scen_md, reas_md, # Tabs 8-13
                gr.update(value=""), None, gr.update(value="") # Compare Outputs
            )
        except Exception as e:
            raise gr.Error(f"Analysis Failed: {str(e)}")

# UI Assembly
custom_theme = gr.themes.Monochrome()

with gr.Blocks(theme=custom_theme, title="AI Institutional Dashboard") as demo:
    gr.Markdown("# 🏦 Institutional AI Financial Dashboard")
    
    with gr.Row():
        with gr.Column(scale=1):
            query = gr.Textbox(label="Enter a Stock Ticker or Company Name", placeholder="e.g., AAPL, Reliance, or 'Compare Parag Parikh and Quant ELSS'", lines=2)
            model_type = gr.Dropdown(choices=["OpenAI (ChatGPT)", "Google Gemini"], value="OpenAI (ChatGPT)", label="Reasoning Engine")
            submit_btn = gr.Button("🚀 Run Institutional Analysis", variant="primary")
            
        with gr.Column(scale=2):
            gr.Markdown("Waiting for query...")
            
    # --- SINGLE MODE UI ---
    with gr.Group(visible=True) as single_group:
        single_header = gr.HTML(value="<div style='padding:20px; text-align:center;'>Enter a single ticker to see deep analysis.</div>")
        with gr.Row():
            score_gauge = gr.Plot()
            confidence_gauge = gr.Plot()
            
        with gr.Tabs():
            with gr.Tab("Summary"): summary_out = gr.Markdown()
            with gr.Tab("Technical Analysis"): 
                price_chart = gr.Plot()
                tech_out = gr.Markdown()
            with gr.Tab("Fundamental"): fund_out = gr.Markdown()
            with gr.Tab("Health"): health_out = gr.Markdown()
            with gr.Tab("Growth"): growth_out = gr.Markdown()
            with gr.Tab("Valuation"): val_out = gr.Markdown()
            with gr.Tab("Ownership"): own_out = gr.Markdown()
            with gr.Tab("News"): news_out = gr.Markdown()
            with gr.Tab("Sector"): sec_out = gr.Markdown()
            with gr.Tab("Risk"): risk_out = gr.Markdown()
            with gr.Tab("Peer Comparison"): peer_out = gr.Markdown()
            with gr.Tab("Scenario"): 
                scenario_chart = gr.Plot()
                scen_out = gr.Markdown()
            with gr.Tab("AI Reasoning"): reas_out = gr.Markdown()
            with gr.Tab("Learn (ELI5)"): gr.Markdown("### 👶 Financial Glossary\n\n**P/E Ratio**: The price of a stock relative to its earnings.\n\n**Support**: A price level where a downtrend tends to pause due to demand.\n\n**Resistance**: A price level where an uptrend tends to pause due to selling.\n\n**Intrinsic Value**: The true, calculated value of a company.\n\n**Margin of Safety**: The difference between the intrinsic value and the current price.\n\n**Portfolio Overlap**: The percentage of common stocks held by two mutual funds.")
            
    # --- COMPARE MODE UI ---
    with gr.Group(visible=False) as compare_group:
        compare_header = gr.HTML()
        with gr.Tabs():
            with gr.Tab("Portfolio Overlap Matrix"):
                overlap_heatmap = gr.Plot()
                overlap_table = gr.Markdown()

    submit_btn.click(
        fn=run_analysis,
        inputs=[query, model_type],
        outputs=[
            single_group, compare_group,
            single_header, price_chart, score_gauge, confidence_gauge, scenario_chart,
            summary_out, tech_out, fund_out, health_out, growth_out, val_out, own_out,
            news_out, sec_out, risk_out, peer_out, scen_out, reas_out,
            compare_header, overlap_heatmap, overlap_table
        ]
    )

if __name__ == "__main__":
    demo.launch()
