import gradio as gr

def trend_func(keywords,time_frame):
  from pytrends.request import TrendReq
  trend= TrendReq()
  # Ensure keywords is a list, handling comma-separated string if passed from Gradio
  if isinstance(keywords, str):
      keywords = [k.strip() for k in keywords.split(',') if k.strip()]

  trend.build_payload(keywords,timeframe=time_frame)
  df=trend.interest_over_time()
  if 'isPartial' in df.columns: # Safely delete 'isPartial' column
    del df['isPartial']
  return df

timeframe_options = [
    'now 1-H', # Last hour
    'now 4-H', # Last 4 hours
    'now 1-d', # Last day
    'today 1-m', # Last month
    'today 3-m', # Last 3 months
    'today 12-m', # Last 12 months
    'today 5-y', # Last 5 years
    'all' # All available data
]

def plot_trends(keywords_str, time_frame):
    df = trend_func(keywords_str, time_frame)
    if df.empty:
        return None # Return None if no data to plot
    return df.plot(title=f'Google Trends for {keywords_str} ({time_frame})').get_figure()


iface = gr.Interface(
    fn=plot_trends,
    inputs=[
        gr.Textbox(label="Keywords (comma-separated)", value="Gemini, chat gpt, claude"),
        gr.Dropdown(timeframe_options, label="Timeframe", value="today 12-m")
    ],
    outputs=gr.Plot(label="Trend Over Time"),
    title="Google Trends Explorer",
    description="Enter keywords and select a timeframe to see Google Trends data."
)

iface.launch(debug=True)