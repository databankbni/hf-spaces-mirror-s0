from transformers import pipeline
import gradio as gr

# Load pre-trained sentiment analysis pipeline
sentiment_pipeline = pipeline("sentiment-analysis")

# Function to analyze sentiment
def analyze_sentiment(text):
    results = sentiment_pipeline(text)
    return {result['label']: round(result['score'], 2) for result in results}

# Gradio Interface
iface = gr.Interface(
    fn=analyze_sentiment,
    inputs=gr.Textbox(lines=2, placeholder="Enter a sentence here..."),
    outputs=gr.Label(num_top_classes=3),
    title="Sentiment Analysis",
    description="Enter a sentence, and the model will classify it as Positive, Negative, or Neutral."
)

# Launch the app
iface.launch()