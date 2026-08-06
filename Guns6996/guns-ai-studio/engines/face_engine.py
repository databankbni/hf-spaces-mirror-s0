import torch
import numpy as np
import insightface
from PIL import Image, ImageEnhance, ImageFilter, ImageDraw
import gradio as gr
import spaces
import replicate
import requests
from pathlib import Path
# Global variable to avoid reloading the model on every request
face_analyzer = None

def load_face_analyzer():
    global face_analyzer
    if face_analyzer is None:
        # Uses CPUExecutionProvider to ensure compatibility across different HF Space tiers
        face_analyzer = insightface.app.FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        face_analyzer.prepare(ctx_id=0, det_size=(640, 640))
    return face_analyzer

def preserve_original_face(original_image, edited_image, strength=0.65):
    original_image = original_image.convert("RGB")
    edited_image = edited_image.convert("RGB").resize(original_image.size)
    w, h = original_image.size
    
    # Region of interest (ROI) for the face based on your app.py logic
    x1, y1, x2, y2 = int(w * 0.28), int(h * 0.08), int(w * 0.72), int(h * 0.38)
    
    original_crop = original_image.crop((x1, y1, x2, y2))
    edited_crop = edited_image.crop((x1, y1, x2, y2))
    
    blended_face = Image.blend(edited_crop, original_crop, float(strength))
    
    # Create a soft circular mask for a natural blend
    mask = Image.new("L", blended_face.size, 0)
    mask_w, mask_h = blended_face.size
    for y in range(mask_h):
        for x in range(mask_w):
            dx, dy = (x - mask_w/2)/(mask_w/2), (y - mask_h/2)/(mask_h/2)
            value = int(max(0, min(255, 255 * (1 - (dx*dx + dy*dy)))))
            mask.putpixel((x, y), value)
            
    result = edited_image.copy()
    result.paste(blended_face, (x1, y1), mask)
    return result

def restore_face_eye_safe(image_path):
    if image_path is None: 
        return None
    try:
        img = Image.open(image_path).convert("RGB")
        # Sharpening and contrast enhancements specifically tuned for face clarity
        img = img.filter(ImageFilter.UnsharpMask(radius=0.4, percent=25, threshold=6))
        img = ImageEnhance.Contrast(img).enhance(1.02)
        img = ImageEnhance.Sharpness(img).enhance(1.02)
        
        fixed_path = "outputs/face_eye_safe.png"
        img.save(fixed_path)
        return fixed_path
    except Exception as e:
        print(f"Error in restore_face_eye_safe: {e}")
        return image_path
def face_swap_image(target_image, face_image, prompt):
    check_token()
    try:
        tp, fp, rp = "/tmp/target.png", "/tmp/face.png", "outputs/face_swap.png"
        target_image.convert("RGB").save(tp)
        face_image.convert("RGB").save(fp)
        output = replicate.run("kwaivgi/kling-v1.6-standard", input={"input_image": Path(tp), "swap_image": Path(fp), "prompt": prompt if prompt else ""})
        url = str(output[0]) if isinstance(output, list) else str(output)
        with open(rp, "wb") as f: f.write(requests.get(url).content)
        return restore_face_eye_safe(rp), "✅ Face swap complete"
    except Exception as e: return None, f"❌ Error: {e}"

def swap_selected_face(target_image, source_face, face_index, prompt):
    check_token()
    if target_image is None or source_face is None: raise gr.Error("Images missing.")
    try:
        target_image = target_image.convert("RGB")
        source_face = source_face.convert("RGB")
        analyzer = load_face_analyzer()
        detected_faces = analyzer.get(np.asarray(target_image))
        if not detected_faces: return None, "❌ No faces detected."
        detected_faces = sorted(detected_faces, key=lambda face: float(face.bbox[0]))
        if face_index < 0 or face_index >= len(detected_faces): return None, "❌ Face index out of range."
        
        selected_face = detected_faces[face_index]
        x1, y1, x2, y2 = selected_face.bbox.astype(int)
        padding_x, padding_top, padding_bottom = int((x2-x1)*0.65), int((y2-y1)*0.7), int((y2-y1)*0.55)
        target_crop = target_image.crop((max(0,x1-padding_x), max(0,y1-padding_top), min(target_image.width,x2+padding_x), min(target_image.height,y2+padding_bottom)))
        
        if not prompt or not prompt.strip(): prompt = "Replace selected person's face. Photorealistic."
        swapped_path, swap_status = face_swap_image(target_crop, source_face, prompt)
        if swapped_path is None: return None, swap_status
        
        swapped_crop = Image.open(swapped_path).convert("RGB").resize(target_crop.size, Image.LANCZOS)
        mask = Image.new("L", target_crop.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((int(target_crop.width*0.18), int(target_crop.height*0.1), int(target_crop.width*0.82), int(target_crop.height*0.9)), fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(max(12, int(min(target_crop.size)*0.1))))
        
        final_image = target_image.copy()
        final_image.paste(swapped_crop, (max(0,x1-padding_x), max(0,y1-padding_top)), mask)
        out_path = f"outputs/selected_face_{face_index}_swap.png"
        final_image.save(out_path)
        return final_image, f"✅ Swapped face {face_index}."
    except Exception as e: return None, f"❌ Error: {e}"

def face_to_video(face_image, motion_prompt):
    check_token()
    fp = "/tmp/f2v.png"
    face_image.convert("RGB").save(fp)
    output = replicate.run("kwaivgi/kling-v1.6-standard", input={"image": Path(fp), "prompt": motion_prompt, "duration": 5, "fps": 15})
    return str(output[0]) if isinstance(output, list) else str(output), "✅ Video generated."

def face_swap_video(face_image, target_video):
    check_token()
    if face_image is None:
        return None,"X please upload a source face."
    if target_video is None:
        return None,"X please upload a target video."
    fp = "/tmp/fsv.png"
    face_image.convert("RGB").save(fp)
    vp = target_video.name if hasattr(target_video, "name") else str(target_video)
    output = replicate.run("arabyai-replicate/roop_face_swap:11b6bf0f4e14d808f655e87e5448233cceff10a45f659d71539cafb7163b2e84", input={"swap_image": Path(fp), "target_video": Path(vp)})
    url = str(output[0]) if isinstance(output, list) else str(output)
    local_out = "/tmp/swap_out.mp4"
    with open(local_out, "wb") as f: f.write(requests.get(url).content)
    return local_out, "✅ Video swap complete."