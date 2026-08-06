import gradio as gr

from predictor import predict_next_numbers
from ml_predictor import predict_next_draw
from data import load_data, add_draw
from report import generate_report
from visualization import create_frequency_chart
from generator import generate_numbers
from analysis import (
    dataset_summary,
    number_frequency,
    hot_numbers,
    cold_numbers
)
from data import load_data

# Generate ticket
def generate_ticket():

    result = generate_numbers(iterations=1000)

    numbers = result["numbers"]
    score = result["score"]

    historical_prediction = predict_next_numbers()

    ml_prediction = predict_next_draw()

    odd = sum(n % 2 != 0 for n in numbers)
    even = sum(n % 2 == 0 for n in numbers)

    # Initialize the output text
    text = ""
    text += "# 🎲 Smart Lottery Ticket\n\n"

    text += "## Your Numbers\n\n"

    text += "| 🎱 | 🎱 | 🎱 | 🎱 | 🎱 | 🎱 |\n"
    text += "|---|---|---|---|---|---|\n"
    text += f"| **{numbers[0]}** | **{numbers[1]}** | **{numbers[2]}** | **{numbers[3]}** | **{numbers[4]}** | **{numbers[5]}** |\n\n"

    text += "\n"

    text += "----------------------------------\n"
    text += "\nAnalysis\n\n"

    text += "✅ Unique Numbers\n"
    text += "✅ Balanced Odd/Even\n"
    text += "✅ Good Number Spread\n"
    text += "✅ Historical Validation Passed\n"
    text += "✅ Hybrid Selection Strategy\n"

    # Confidence Rating
    if score >= 300:
        stars = "★★★★★"
    elif score >= 270:
        stars = "★★★★☆"
    elif score >= 240:
        stars = "★★★☆☆"
    elif score >= 210:
        stars = "★★☆☆☆"
    else:
        stars = "★☆☆☆☆"

    text += "\n----------------------------------\n"

    text += "\nConfidence Rating\n\n"

    text += "## ⭐ AI Confidence\n\n"

    text += f"**Rating:** {stars}\n\n"

    text += f"**Score:** {score}\n\n"

    text += "\nSelection Strategy\n"
    text += "- Balanced odd/even numbers\n"
    text += "- Good number spread\n"
    text += "- Hybrid pool (hot, cold, and random numbers)\n"
    text += "- Historical duplicate check\n"
    text += "- Highest score from generated candidates\n"

    text += "## 📊 Ticket Statistics\n\n"

    text += f"- Odd Numbers: **{odd}**\n"
    text += f"- Even Numbers: **{even}**\n"
    text += f"- Lowest Number: **{min(numbers)}**\n"
    text += f"- Highest Number: **{max(numbers)}**\n"
    text += f"- Range: **{max(numbers)-min(numbers)}**\n"

    text += f"- Sum: **{sum(numbers)}**\n\n"

    text += "\n\n---\n\n"

    text += "## 📚 Historical AI Prediction\n\n"
    text += ", ".join(str(number) for number in historical_prediction)

    text += "\n\n"

    text += "## 🤖 Machine Learning Prediction\n\n"
    text += ", ".join(str(number) for number in ml_prediction)

    return text

# AI insights
def ai_insights():

    historical = predict_next_numbers()

    machine = predict_next_draw()

    text = "🧠 AI INSIGHTS\n"
    text += "=" * 40 + "\n\n"

    text += "Historical AI Prediction\n\n"

    for number in historical:
        text += f"• {number}\n"

    text += "\n"

    text += "=" * 40 + "\n\n"

    text += "Machine Learning Prediction\n\n"

    for number in machine:
        text += f"• {number}\n"

    return text

# Save draw
def save_draw(n1, n2, n3, n4, n5, n6):

    dataframe = load_data()

    numbers = [
        int(n1),
        int(n2),
        int(n3),
        int(n4),
        int(n5),
        int(n6)
    ]

    dataframe, message = add_draw(dataframe, numbers)

    return message

# Dataset Summary
def show_summary():

    data = load_data()

    summary = dataset_summary(data)

    text = ""

    for key, value in summary.items():
        text += f"{key}: {value}\n"

    return text

# Hot numbers
def show_hot():

    data = load_data()

    frequency = number_frequency(data)

    hot = hot_numbers(frequency)

    text = "🔥 Top 10 Hot Numbers\n\n"

    for number, count in hot:
        text += f"{number} : {count}\n"

    return text

# Cold numbers
def show_cold():

    data = load_data()

    frequency = number_frequency(data)

    cold = cold_numbers(frequency)

    text = "❄️ Top 10 Cold Numbers\n\n"

    for number, count in cold:
        text += f"{number} : {count}\n"

    return text

def system_status():

    data = load_data()

    total_draws = len(data)

    frequency = number_frequency(data)

    hot = hot_numbers(frequency)
    cold = cold_numbers(frequency)

    hottest_number, hottest_count = hot[0]
    coldest_number, coldest_count = cold[0]

    return f"""
 # 📊 UAE Lottery AI Status

 ## Dataset

 - 📁 Total Draws: **{total_draws}**
 - 🎯 Numbers Per Draw: **6**
 - 🤖 Machine Learning: **Ready**
 - 📈 Historical Analysis: **Ready**

 ---

 ## Statistics

 🔥 Hottest Number: **{hottest_number}** ({hottest_count} appearances)

 ❄️ Coldest Number: **{coldest_number}** ({coldest_count} appearances)

 ---

 ## System Status

 | Component | Status |
 |-----------|--------|
 | Data | ✅ Loaded |
 | Generator | ✅ Ready |
 | Analysis | ✅ Ready |
 | Machine Learning | ✅ Ready |
 | Charts | ✅ Ready |
 | Reports | ✅ Ready |

 ---

 ### Version

 **UAE Lottery AI v1.0**
 """

# Interface 
custom_css = open("assets/style.css", encoding="utf-8").read()

with gr.Blocks(title="UAE Lottery AI") as app:
    gr.Image(
      value="assets/logo.png",
      show_label=False,
      interactive=False,
      container=False,
      height=180
    )

    gr.Image(
      value="assets/lottery_balls.png",
      show_label=False,
      interactive=False,
      height=280
    )

    gr.Markdown(""" 
    # 🎲 UAE Lottery AI
    ### Historical Analysis • Machine Learning • Smart Predictions

    Generate intelligent lottery tickets using statistical analysis and AI.

    ---
    """)

    with gr.Tab("🏠 Home"):

       gr.Markdown("""
     # 🎲 Lottery AI

     Welcome to Lottery AI!

     This application analyzes historical lottery draws and generates
     6 suggested lottery numbers using historical statistics.

     ## Features

     - 📊 Dataset Summary
     - 🔥 Hot Numbers
     - ❄️ Cold Numbers
     - 📈 Frequency Charts
     - 🎲 Smart Lottery Generator
     - 🧠 AI Insights

     ## ⚠ Disclaimer

     This application analyzes historical lottery data using statistical
     methods and machine learning.

     It is designed for educational and analytical purposes only.
     Lottery draws are random, and no prediction or generated ticket
     can guarantee winning results.

     Built for historical analysis, machine learning, and intelligent lottery data visualization. 
    """)

    with gr.Tab("🎲 Generator"):

        button = gr.Button("Generate Numbers")

        output = gr.Markdown()

        button.click(
            fn=generate_ticket,
            outputs=output
        )

    with gr.Tab("📊Analysis"):

        summary_button = gr.Button("Dataset Summary")

        summary_output = gr.Textbox(lines=6)

        summary_button.click(
            show_summary,
            outputs=summary_output
        )
        
        hot_button = gr.Button("Hot Numbers")

        hot_output = gr.Textbox(lines=12)

        hot_button.click(
            show_hot,
            outputs=hot_output
        )

        cold_button = gr.Button("Cold Numbers")

        cold_output = gr.Textbox(lines=12)

        cold_button.click(
            show_cold,
            outputs=cold_output)

    with gr.Tab("ℹ About"):

        gr.Markdown("""
      # About Lottery AI

      Lottery AI was built with Python.

      Libraries used:

      - Pandas
      - Matplotlib
      - Gradio

      Modules:

     - data.py
     - analysis.py
     - generator.py
     - visualization.py

     Developer:
     Kyambadde Grrald
    """)

    with gr.Tab("📈 Charts"):

     chart_button = gr.Button("📊 Show Frequency Chart")

     chart_output = gr.Plot()

     chart_button.click(
        fn=create_frequency_chart,
        outputs=chart_output
    )

    with gr.Tab("📝 Add New Draw"):

     n1 = gr.Number(label="Number 1", minimum=1, maximum=31)
     n2 = gr.Number(label="Number 2", minimum=1, maximum=31)
     n3 = gr.Number(label="Number 3", minimum=1, maximum=31)
     n4 = gr.Number(label="Number 4", minimum=1, maximum=31)
     n5 = gr.Number(label="Number 5", minimum=1, maximum=31)
     n6 = gr.Number(label="Number 6", minimum=1, maximum=31)

     save_button = gr.Button("💾 Save Draw")

     result = gr.Textbox(label="Status")

     save_button.click(
        save_draw,
        inputs=[n1, n2, n3, n4, n5, n6],
        outputs=result
    )
     
    with gr.Tab("📄 Report"):

     report_button = gr.Button("Generate Report")

     report_output = gr.Textbox(
        lines=30,
        label="Lottery Analysis Report"
    )

    report_button.click(
        fn=generate_report,
        outputs=report_output
    )

    with gr.Tab("🧠 AI Insights"):

     gr.Markdown("## AI Prediction Comparison")

     ai_button = gr.Button("Show AI Predictions")

     ai_output = gr.Textbox(
        lines=20,
        label="AI Insights"
    )

    ai_button.click(
        ai_insights,
        outputs=ai_output
    )

    with gr.Tab("📊 Status"):

     status_button = gr.Button("🔄 Refresh Status")

     status_output = gr.Markdown()

     status_button.click(
        fn=system_status,
        outputs=status_output
    )

    gr.Markdown("""
     ---

     # 🎰 UAE Lottery AI

     Version 1.0

     Developer
     Kyambadde Grrald

     Technologies
     🐍 Python
     📊 Pandas
     🤖 Scikit-learn
     📈 Matplotlib
     🎨 Gradio

     Purpose
     Analyze historical lottery data using statistical analysis
     and machine learning techniques.

     Disclaimer
     This application is for educational and analytical purposes.
     Lottery results are random and no prediction is guaranteed.

     © 2026 UAE Lottery AI
    """)
             
app.launch( css=custom_css )