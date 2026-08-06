# Deploy to Hugging Face Spaces (Gradio)

This project is a Gradio app and can be deployed to Hugging Face Spaces as a Gradio Space.

Prerequisites:
- A Hugging Face account and an access token. Create one at https://huggingface.co/settings/tokens
- `huggingface_hub` CLI installed: `pip install huggingface_hub`
- `git` and `git-lfs` installed locally

Steps:

1. Login to Hugging Face CLI:

```bash
huggingface-cli login
# paste your token
```

2. Create a new Space on Hugging Face (via web UI) or use the CLI to create (replace YOUR_USERNAME and SPACE_NAME):

```bash
# from HF CLI v0.14+, simple creation example (or create via web UI):
# huggingface-cli repo create YOUR_USERNAME/SPACE_NAME --type space --space-sdk gradio
```

3. Clone the Spaces repo locally (replace path):

```bash
git clone https://huggingface.co/spaces/YOUR_USERNAME/SPACE_NAME
cd SPACE_NAME
```

4. Copy project files into the cloned repo. The Space needs an entrypoint file (the Gradio app). Use `PS5MonthlyPlanner.py` as the app file or create a small `app.py` that imports and runs the Gradio Blocks. Example `app.py`:

```python
from PS5MonthlyPlanner import demo

def main():
    demo.launch(share=False)

if __name__ == '__main__':
    main()
```

5. Ensure `requirements.txt` is present in the Space root (this repo already contains one). Commit and push:

```bash
git add .
git commit -m "Add PS5MonthlyPlanner Gradio Space"
git push
```

6. The Space will build automatically and provide a public URL in the Spaces settings.

Notes:
- If the app scrapes external sites, ensure it complies with the target site's robots and terms.
- For large dependencies, consider slimming down the requirements for faster builds.

