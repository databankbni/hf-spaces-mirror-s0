from fastai.vision.all import load_learner, PILImage
import gradio as gr

learn = load_learner("export.pkl")
labels = learn.dls.vocab


def classify_image(img):
    img = PILImage.create(img)
    _, _, probs = learn.predict(img)
    return {label: float(prob) for label, prob in zip(labels, probs)}


demo = gr.Interface(
    fn=classify_image,
    inputs=gr.Image(type="pil", label="Upload a bear"),
    outputs=gr.Label(num_top_classes=3, label="Prediction"),
    title="Bear Classifier",
    description="Grizzly, black, or teddy? Upload an image to find out.",
    examples=["images/grizzly.jpg"],
)

if __name__ == "__main__":
    demo.launch()
