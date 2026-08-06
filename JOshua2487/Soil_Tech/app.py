# app.py
# ─────────────────────────────────────────────────────────────────────────────
# Keep this file for routes and model only.
# Crop logic lives in: crop_aliases.py, language_utils.py, crop_normalizer.py
# ─────────────────────────────────────────────────────────────────────────────

from flask import Flask, request, jsonify
from flask_cors import CORS
import numpy as np
from PIL import Image
import cv2
import io
import json
import os
import tensorflow as tf
from tensorflow.keras.applications import EfficientNetB3
from tensorflow.keras.applications.efficientnet import preprocess_input
from tensorflow.keras import layers, models
from dotenv import load_dotenv

from crop_normalizer import normalize_crop_name
from crop_aliases import ENGLISH_DISPLAY

load_dotenv()

app = Flask(__name__)
CORS(app)


@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

CLASS_NAMES = ['clay', 'loamy', 'peat', 'sandy', 'silt', 'not_soil']

# Below this confidence (%), reject the prediction instead of returning it.
# Starting point — tune empirically against real test photos.
CONFIDENCE_THRESHOLD = 60.0

# EfficientNetB3's designed input resolution — must match training exactly.
IMG_SIZE = 300

BASE = os.path.dirname(__file__)

# ── Load model ─────────────────────────────────────────────────────────────
# Weights-only load (not a full model save) — same pattern as the MobileNetV2
# version. Rebuild the exact training architecture here and load weights into
# it. Architecture must match training exactly: EfficientNetB3 base (frozen
# initially, later fine-tuned) + GlobalAveragePooling2D + Dense(128, relu) +
# Dropout(0.3) + Dense(6, softmax).
base_model = EfficientNetB3(input_shape=(IMG_SIZE, IMG_SIZE, 3), include_top=False, weights=None)
base_model.trainable = False
x = base_model.output
x = layers.GlobalAveragePooling2D()(x)
x = layers.Dense(128, activation='relu')(x)
x = layers.Dropout(0.3)(x)
output = layers.Dense(len(CLASS_NAMES), activation='softmax')(x)
model = models.Model(inputs=base_model.input, outputs=output)
model.load_weights(os.path.join(BASE, 'soil_model_v7_efficientb3.weights.h5'))

# ── Load JSON files ────────────────────────────────────────────────────────
with open(os.path.join(BASE, 'soil_profile.json')) as f:
    soil_profile = json.load(f)
with open(os.path.join(BASE, 'crop_requirements.json')) as f:
    crop_requirements = json.load(f)
with open(os.path.join(BASE, 'amendments.json')) as f:
    amendments = json.load(f)

# ── Groq client ────────────────────────────────────────────────────────────
from groq import Groq
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def estimate_om(image_bytes, wet_dry_score):
    np_arr = np.frombuffer(image_bytes, np.uint8)
    img    = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    h, w, _ = img.shape
    cx, cy   = w // 2, h // 2
    size     = min(h, w) // 4
    crop_img = img[cy-size:cy+size, cx-size:cx+size]
    hsv      = cv2.cvtColor(crop_img, cv2.COLOR_BGR2HSV)
    v_mean   = np.mean(hsv[:, :, 2])

    corrected_v = v_mean + (wet_dry_score * 15)

    if corrected_v < 76:
        om_level = 'high'
    elif corrected_v <= 127:
        om_level = 'moderate'
    else:
        om_level = 'low'

    return om_level, round(float(corrected_v), 2)


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    return jsonify({"message": "Soiltech API is running"})


@app.route('/crops', methods=['GET'])
def get_crops():
    """Returns raw canonical crop keys."""
    return jsonify({'crops': list(crop_requirements.keys())})


@app.route('/crops-display', methods=['GET'])
def get_crops_display():
    """
    Returns crops with English display names for the default Flutter UI grid.
    Used to populate the crop picker before the farmer types anything.
    """
    result = [
        {
            'key':     key,
            'display': ENGLISH_DISPLAY.get(key, key.replace('_', ' ').title())
        }
        for key in crop_requirements.keys()
    ]
    return jsonify({'crops': result})


@app.route('/normalize-crop', methods=['POST'])
def normalize_crop():
    """
    Accepts any crop name (Bisaya, Tagalog, English, misspelled).
    Returns the canonical key + the correct display name for the frontend.
    """
    data = request.get_json()
    raw  = data.get('crop_name', '').strip()

    if not raw:
        return jsonify({'error': 'crop_name is required'}), 400

    matched, display = normalize_crop_name(raw, crop_requirements)

    if matched and matched in crop_requirements:
        return jsonify({'crop': matched, 'display': display})
    else:
        return jsonify({'crop': None, 'error': 'No match found'}), 404


@app.route('/predict', methods=['POST'])
def predict():
    if 'image' not in request.files:
        return jsonify({"error": "No image provided"}), 400

    wet_dry_score = int(request.form.get('wet_dry_score', 0))
    file          = request.files['image']
    image_bytes   = file.read()

    img       = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    img       = img.resize((IMG_SIZE, IMG_SIZE))
    img_array = np.array(img).astype(np.float32)
    img_array = preprocess_input(img_array)  # EfficientNet-specific preprocessing — NOT /255.0
    img_array = np.expand_dims(img_array, axis=0)

    predictions = model.predict(img_array)
    class_index = np.argmax(predictions[0])
    confidence  = float(np.max(predictions[0])) * 100
    soil_type   = CLASS_NAMES[class_index]

    # ── Reject if model explicitly says not_soil, OR confidence is too low ──
    # (checked BEFORE running OM estimation — no point estimating organic
    # matter on an image that isn't soil in the first place)
    if soil_type == 'not_soil' or confidence < CONFIDENCE_THRESHOLD:
        return jsonify({
            "recognized": False,
            "error"     : "Image not recognized as soil. Please retake the photo with soil filling most of the frame.",
            "confidence": f"{confidence:.2f}%"
        }), 400

    om_level, brightness_value = estimate_om(image_bytes, wet_dry_score)

    return jsonify({
        "recognized"         : True,
        "soil_type"          : soil_type,
        "confidence"         : f"{confidence:.2f}%",
        "om_level"           : om_level,
        "om_brightness_value": brightness_value
    })


@app.route('/recommend', methods=['POST'])
def recommend():
    data           = request.get_json()
    soil_type      = data.get('soil_type', '').lower()
    om_level       = data.get('om_level', '').lower()
    drainage_score = data.get('drainage_score', 0)

    crop_name, _   = normalize_crop_name(data.get('crop_name', ''), crop_requirements)

    if not crop_name or crop_name not in crop_requirements:
        return jsonify({'error': f'Crop "{data.get("crop_name", "")}" not recognized. Please try another name.'}), 404

    crop           = crop_requirements[crop_name]
    issues         = []
    amendment_list = []

    # ── Soil type check ────────────────────────────────────────────────────
    if soil_type in crop['unsuitable_soil_types']:
        compatibility = 'not_suitable'
        issues.append(f'{soil_type} soil is not suitable for {crop_name}')
        amendment_list += amendments['unsuitable_soil_type']['amendments']
    else:
        compatibility = 'suitable'

    # ── Organic matter check ───────────────────────────────────────────────
    if om_level not in crop['required_om']:
        issues.append(f'Organic matter is {om_level} — {crop_name} needs {" or ".join(crop["required_om"])}')
        amendment_list += amendments['low_om']['amendments']
        if compatibility == 'suitable':
            compatibility = 'fair'

    # ── Drainage check ─────────────────────────────────────────────────────
    soil_drainage = soil_profile[soil_type]['drainage_default']
    if drainage_score == -1:
        actual_drainage = 'poor'
    elif drainage_score == 1:
        actual_drainage = 'excessive'
    else:
        actual_drainage = soil_drainage

    if actual_drainage not in crop['required_drainage']:
        issues.append(f'Drainage is {actual_drainage} — {crop_name} needs {" or ".join(crop["required_drainage"])}')
        if actual_drainage == 'poor':
            amendment_list += amendments['poor_drainage']['amendments']
        elif actual_drainage == 'excessive':
            amendment_list += amendments['excessive_drainage']['amendments']
        if compatibility == 'suitable':
            compatibility = 'fair'

    amendment_list = list(dict.fromkeys(amendment_list))

    # ── Suitable: build positive reasons + tips instead of issues ─────────
    suitable_reasons = []
    suitable_tips    = []

    if compatibility == 'suitable':
        # reasons are generated dynamically based on what passed
        if soil_type in crop['suitable_soil_types']:
            suitable_reasons.append(
                f'{soil_type.capitalize()} soil matches {crop_name}\'s soil requirements'
            )
        if om_level in crop['required_om']:
            suitable_reasons.append(
                f'Organic matter ({om_level}) meets {crop_name}\'s needs'
            )
        if actual_drainage in crop['required_drainage']:
            suitable_reasons.append(
                f'Drainage ({actual_drainage}) is appropriate for {crop_name}'
            )

        # tips pulled from amendments.json "suitable" key
        suitable_tips = amendments.get('suitable', {}).get('tips', [])

    # ── Response ───────────────────────────────────────────────────────────
    return jsonify({
        'soil_type'       : soil_type,
        'crop'            : crop_name,
        'compatibility'   : compatibility,
        'issues'          : issues,
        'amendments'      : amendment_list,
        'suitable_reasons': suitable_reasons,  # non-empty only when suitable
        'suitable_tips'   : suitable_tips       # non-empty only when suitable
    })


@app.route('/explain', methods=['POST'])
def explain():
    data          = request.get_json()
    soil_type     = data.get('soil_type', '')
    om_level      = data.get('om_level', '')
    crop_name     = data.get('crop_name', '')
    issues        = data.get('issues', [])
    farmer_name   = data.get('farmer_name', 'Kuya')
    compatibility = data.get('compatibility', '')   # NEW — drives prompt mode

    if not soil_type or not crop_name:
        return jsonify({'error': 'Missing soil_type or crop_name'}), 400

    # ── Prompt switches based on compatibility ─────────────────────────────
    if compatibility == 'suitable':
        prompt = f"""You are an agricultural advisor speaking directly to a Filipino farmer named {farmer_name}.
Soil type: {soil_type}
Organic matter level: {om_level}
Crop chosen: {crop_name}

The farmer's soil is fully suitable for {crop_name}.
In 3 to 4 plain sentences, encourage {farmer_name} and explain what good results
they can expect when planting {crop_name} in this soil.
Be specific, positive, and practical.
Address {farmer_name} directly by name at least once.
Avoid technical jargon."""

    else:
        # fair or not_suitable — current warning prompt unchanged
        issues_text = ', '.join(issues) if issues else 'none identified'
        prompt = f"""You are an agricultural advisor speaking directly to a Filipino farmer named {farmer_name}.
Soil type: {soil_type}
Organic matter level: {om_level}
Crop chosen: {crop_name}
Issues identified: {issues_text}

In 3 to 4 plain sentences, explain what will likely happen if {farmer_name}
plants {crop_name} in this soil without fixing the issues.
Address {farmer_name} directly by name at least once.
Be specific, practical, and avoid technical jargon."""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}]
        )
        explanation = response.choices[0].message.content
        return jsonify({'explanation': explanation})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Blueprint ───────────────────────────────────────────────────────────────
from chat_route import chat_bp
app.register_blueprint(chat_bp)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=7860)