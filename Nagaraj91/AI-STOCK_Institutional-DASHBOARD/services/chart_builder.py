import plotly.graph_objects as go
import yfinance as yf
import pandas as pd
from typing import Dict, Any

def create_candlestick_chart(ticker: str) -> go.Figure:
    try:
        df = yf.Ticker(ticker).history(period="1y")
    except Exception:
        df = pd.DataFrame()
        
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No Price Data Available", xref="paper", yref="paper", showarrow=False, font=dict(size=20, color="gray"))
        fig.update_layout(template="plotly_dark", xaxis_visible=False, yaxis_visible=False)
        return fig
        
    fig = go.Figure(data=[go.Candlestick(x=df.index,
                open=df['Open'],
                high=df['High'],
                low=df['Low'],
                close=df['Close'])])
    fig.update_layout(title=f"{ticker} 1-Year Price History", template="plotly_dark", xaxis_rangeslider_visible=False)
    return fig

def create_gauge_chart(score: int, title: str) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = score,
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': title},
        gauge = {
            'axis': {'range': [None, 100]},
            'bar': {'color': "darkblue"},
            'steps': [
                {'range': [0, 40], 'color': "red"},
                {'range': [40, 70], 'color': "yellow"},
                {'range': [70, 100], 'color': "green"}],
        }))
    fig.update_layout(template="plotly_dark", height=300)
    return fig

def create_scenario_bar_chart(scenarios: Dict[str, float]) -> go.Figure:
    if not scenarios or all(v == 0 for v in scenarios.values()):
        fig = go.Figure()
        fig.add_annotation(text="No Scenario Data Available", xref="paper", yref="paper", showarrow=False, font=dict(size=20, color="gray"))
        fig.update_layout(template="plotly_dark", xaxis_visible=False, yaxis_visible=False)
        return fig
        
    fig = go.Figure([go.Bar(x=list(scenarios.keys()), y=list(scenarios.values()))])
    fig.update_layout(title="Scenario Target Prices", template="plotly_dark")
    return fig

def create_overlap_heatmap(overlap_data: Dict[str, Any]) -> go.Figure:
    """Creates a heatmap for N-fund portfolio overlap."""
    funds = overlap_data["funds_compared"]
    
    # Initialize N x N matrix with 100% on diagonal
    z = [[100.0 if i==j else 0.0 for j in range(len(funds))] for i in range(len(funds))]
    
    # Fill pairwise overlaps
    for pair in overlap_data["pairwise_overlaps"]:
        f1_idx = funds.index(pair["fund_a"])
        f2_idx = funds.index(pair["fund_b"])
        val = pair["overlap_percentage"]
        z[f1_idx][f2_idx] = val
        z[f2_idx][f1_idx] = val # symmetric
        
    fig = go.Figure(data=go.Heatmap(
        z=z,
        x=funds,
        y=funds,
        colorscale='Viridis',
        text=[[f"{val}%" for val in row] for row in z],
        texttemplate="%{text}",
    ))
    fig.update_layout(title="Portfolio Overlap Matrix", template="plotly_dark")
    return fig
