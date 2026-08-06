import gradio as gr
from predict import predict


def run_prediction(prompt, A, B, C, D, E):

    if not prompt.strip():
        return "Please enter a question."

    results = predict(prompt, A, B, C, D, E)

    output = "# 🧠 Smart MCQ Solver Results\n\n"

    medals = ["🥇", "🥈", "🥉"]

    for i, (label, option_text, score) in enumerate(results):

        output += f"{medals[i]} **Rank {i+1}**\n\n"
        output += f"**Option {label}**\n\n"
        output += f"{option_text}\n\n"
        output += f"Confidence Score: **{score:.4f}**\n\n"
        output += "---\n\n"

    return output


with gr.Blocks(title="Smart MCQ Solver") as demo:

    gr.Markdown(
        """
        # 🧠 Smart MCQ Solver
        ### DeBERTa-v3-base Fine-tuned Multiple Choice Question Answering
        Enter a question and five answer options. The model predicts the **Top-3** most likely answers.
        """
    )

    question = gr.Textbox(
        lines=5,
        label="Question"
    )

    optionA = gr.Textbox(label="Option A")
    optionB = gr.Textbox(label="Option B")
    optionC = gr.Textbox(label="Option C")
    optionD = gr.Textbox(label="Option D")
    optionE = gr.Textbox(label="Option E")

    predict_button = gr.Button(
        "🚀 Predict Top 3",
        variant="primary"
    )

    output = gr.Markdown()

    predict_button.click(
        fn=run_prediction,
        inputs=[
            question,
            optionA,
            optionB,
            optionC,
            optionD,
            optionE
        ],
        outputs=output
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)