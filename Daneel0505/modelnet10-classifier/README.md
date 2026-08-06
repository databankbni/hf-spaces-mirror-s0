---
title: Modelnet10 Classifier
emoji: 👀
colorFrom: yellow
colorTo: gray
sdk: gradio
sdk_version: 6.19.0
python_version: '3.13'
app_file: app.py
pinned: false
license: mit
---

Check out the configuration reference at https://huggingface.co/docs/hub/spaces-config-reference

# ModelNet10 Multi-View Classifier (PyTorch)

Classifies a 3D object (ModelNet10) from its rendered 2D views, using a custom CNN trained
from scratch for B9AI104 Deep Learning CA1. Upload the four azimuth views (0/90/180/270°) of one
object for multi-view voting, or a single image.

## Files this Space needs
- `app.py` : the Gradio app (rebuilds the CustomCNN and loads the weights)
- `requirements.txt` : dependencies (torch, numpy, pillow, gradio)
- `best_model.pt` : the trained model exported from the PyTorch notebook

## Notes
- The CustomCNN class in `app.py` must match the architecture in the training notebook (it does).
- Preprocessing is resize-224 + ImageNet normalisation, identical to training — do not change it.
- `/predict_views` averages the softmax across the uploaded views (multi-view voting).

