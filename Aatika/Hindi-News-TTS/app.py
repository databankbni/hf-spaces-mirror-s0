import gradio as gr
import subprocess
import os
import uuid
import re
import zipfile
import glob
import time
import shutil
import requests
import urllib.request
import json

# गूगल ड्राइव सपोर्ट
try:
    import gdown
except ImportError:
    gdown = None

# 🔑 आपका पर्सनल सीक्रेट पासवर्ड
MY_SECRET_KEY = "AryanNewsTech@2026"

# Pydub इंपोर्ट (ऑडियो एनहांसमेंट के लिए)
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False

# --- हगिंग फेस स्टोरेज सेटअप ---
EXTRACT_FOLDER = "uploaded_voice_models"
os.makedirs(EXTRACT_FOLDER, exist_ok=True)

# 🛡️ डिफ़ॉल्ट मॉडल्स जिन्हें कोई डिलीट नहीं कर सकता
DEFAULT_MODELS = [
    "Aman_Voice_Model",
    "Ravi_Voice_Model",
    "hi_IN-pratham-medium",
    "hi_IN-priyamvada-medium",
    "hi_IN-rohan-medium"
]

def refresh_models():
    """लाइव स्कैनिंग फंक्शन"""
    models = []
    for existing_model in glob.glob(f"{EXTRACT_FOLDER}/**/*.onnx", recursive=True):
        if existing_model not in models:
            models.append(existing_model)
    for existing_model in glob.glob("*.onnx"):
        if existing_model not in models:
            models.append(existing_model)
    return models

def get_model_choices(show_mb=False):
    """मेन ड्रॉपडाउन के लिए सभी (डिफ़ॉल्ट + कस्टम) मॉडल लिस्ट तैयार करना।"""
    all_models = refresh_models()
    choices = []
    
    for dm in DEFAULT_MODELS:
        expected_path = os.path.join(EXTRACT_FOLDER, f"{dm}.onnx")
        if expected_path in all_models:
            all_models.remove(expected_path)
            
        if show_mb and os.path.exists(expected_path):
            size_mb = os.path.getsize(expected_path) / (1024 * 1024)
            display_name = f"{dm} ({size_mb:.1f} MB)"
        else:
            display_name = dm
        choices.append((display_name, expected_path))
        
    for p in all_models:
        name = os.path.basename(p).replace(".onnx", "")
        if show_mb:
            try:
                size_mb = os.path.getsize(p) / (1024 * 1024)
                display_name = f"{name} ({size_mb:.1f} MB)"
            except Exception:
                display_name = name
        else:
            display_name = name
        choices.append((display_name, p))
        
    return choices

def get_delete_model_choices(show_mb=True):
    """डिलीट ड्रॉपडाउन के लिए सिर्फ कस्टम मॉडल्स की लिस्ट तैयार करना"""
    all_models = refresh_models()
    choices = []
    
    for p in all_models:
        name = os.path.basename(p).replace(".onnx", "")
        if name in DEFAULT_MODELS:
            continue
            
        if show_mb:
            try:
                size_mb = os.path.getsize(p) / (1024 * 1024)
                display_name = f"{name} ({size_mb:.1f} MB)"
            except Exception:
                display_name = name
        else:
            display_name = name
        choices.append((display_name, p))
        
    if not choices:
        return [("कोई कस्टम मॉडल नहीं है (डिफ़ॉल्ट मॉडल सुरक्षित हैं)", "none")]
    return choices

def count_characters(text):
    if not text:
        text = ""
    return f"📝 **अक्षरों की संख्या (Character Count):** {len(text)}"

def update_active_model_display(model_path):
    if model_path == "none" or not model_path:
        return "🔴 **वर्तमान मॉडल:** कोई मॉडल नहीं चुना गया है"
    model_name = os.path.basename(model_path).replace(".onnx", "")
    return f"🟢 **वर्तमान मॉडल इस्तेमाल हो रहा है:** `{model_name}`"

# --- स्मार्ट गूगल ट्रांसलिटरेशन, कस्टम डिक्शनरी और ऑटो-शॉर्ट फॉर्म ---

DICT_FILE = "custom_acronyms.json"

# जो शब्द अपवाद (Exception) हैं, उन्हें यहाँ डिफ़ॉल्ट रूप से रखा गया है
DEFAULT_ACRONYMS = {
    "NEWS": "न्यूज़",
    "VIP": "वीआईपी"
}

# 📚 इंग्लिश के अक्षरों का हिंदी उच्चारण (ऑटो शॉर्ट-फॉर्म के लिए)
ENG_ALPHABET_HINDI = {
    'A': 'ए', 'B': 'बी', 'C': 'सी', 'D': 'डी', 'E': 'ई', 'F': 'एफ', 'G': 'जी', 
    'H': 'एच', 'I': 'आई', 'J': 'जे', 'K': 'के', 'L': 'एल', 'M': 'एम', 'N': 'एन', 
    'O': 'ओ', 'P': 'पी', 'Q': 'क्यू', 'R': 'आर', 'S': 'एस', 'T': 'टी', 'U': 'यू', 
    'V': 'वी', 'W': 'डब्ल्यू', 'X': 'एक्स', 'Y': 'वाई', 'Z': 'जेड'
}

def load_custom_dict():
    """डिक्शनरी फाइल लोड करता है, अगर नहीं है तो डिफ़ॉल्ट बनाता है।"""
    if os.path.exists(DICT_FILE):
        try:
            with open(DICT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_ACRONYMS.copy()

def save_custom_dict(data):
    """डिक्शनरी को फाइल में सेव करता है।"""
    with open(DICT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def add_new_custom_word(eng_word, hin_word, secret_key):
    """UI से नया शब्द डिक्शनरी में जोड़ने का फंक्शन"""
    if secret_key != MY_SECRET_KEY:
        return "❌ एरर: अनऑथराइज्ड एक्सेस! सीक्रेट पासवर्ड गलत है।"
    
    eng_word = eng_word.strip().upper()
    hin_word = hin_word.strip()
    
    if not eng_word or not hin_word:
        return "❌ कृपया अंग्रेजी और हिंदी दोनों शब्द डालें।"
        
    current_dict = load_custom_dict()
    current_dict[eng_word] = hin_word
    save_custom_dict(current_dict)
    
    recent_words = ", ".join([f"{k}: {v}" for k, v in list(current_dict.items())[-5:]])
    return f"✅ **'{eng_word}'** को सफलतापूर्वक **'{hin_word}'** के रूप में अपडेट कर दिया गया है!\n\n*(डिक्शनरी में मौजूद शब्द: ... {recent_words})*"

def transliterate_english_to_hindi(word):
    current_dict = load_custom_dict()
    upper_word = word.upper()
    
    # 1. पहले कस्टम डिक्शनरी में चेक करें (ताकि NEWS जैसे शब्द न्यूज़ ही रहें)
    if upper_word in current_dict:
        return current_dict[upper_word]

    # 2. ऑटोमैटिक शॉर्ट-फॉर्म (Acronym) डिटेक्शन
    # नियम: अगर शब्द पूरा CAPITAL लेटर्स में है (HDFC, ICICI) या उसमें कोई vowel नहीं है (hdfc, jpsc)
    vowels = set("aeiouAEIOU")
    is_all_caps = word.isupper()
    has_no_vowels = not any(char in vowels for char in word)
    
    # अगर शब्द 1 से बड़ा है और (पूरा कैपिटल है या कोई स्वर नहीं है)
    if len(word) > 1 and (is_all_caps or has_no_vowels):
        # एक-एक अक्षर को हिंदी में बदलें (H -> एच, D -> डी...)
        acronym_hindi = "".join([ENG_ALPHABET_HINDI.get(char.upper(), char) for char in word])
        return acronym_hindi

    # 3. बाकी साधारण शब्दों के लिए Google API (जैसे News, Today, India)
    try:
        url = f"https://inputtools.google.com/request?text={word}&itc=hi-t-i0-und&num=1&cp=0&cs=1&ie=utf-8&oe=utf-8&app=test"
        response = requests.get(url, timeout=3).json()
        if response[0] == 'SUCCESS':
            return response[1][0][1][0]
    except Exception as e:
        pass
    return word 

def clean_and_transliterate_script(text, do_transliterate=True, do_autopunctuate=True):
    if not text:
        return ""
        
    text = text.replace("**", "")
    
    if do_autopunctuate:
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        processed_lines = []
        for line in lines:
            if line and line[-1] not in ['.', '।', '?', '!', ',', ':', ';']:
                line += '।'
            processed_lines.append(line)
        text = ' '.join(processed_lines)
    
    if do_transliterate:
        eng_words = list(set(re.findall(r'[a-zA-Z0-9]+', text)))  # G20 जैसे शब्दों को भी कवर करेगा
        trans_dict = {}
        for word in eng_words:
            # अगर सिर्फ नंबर है तो इग्नोर करें
            if word.isdigit():
                continue
            trans_dict[word] = transliterate_english_to_hindi(word)
            
        def replace_english(match):
            word = match.group(0)
            if word.isdigit():
                return word
            return trans_dict.get(word, word)
        
        text = re.sub(r'[a-zA-Z0-9]+', replace_english, text)
        
    return text.strip()

def extract_and_update_models(zip_filepath):
    if not zip_filepath:
        return gr.update(), gr.update(), "❌ कृपया कोई ज़िप फाइल अपलोड करें।"
    try:
        with zipfile.ZipFile(zip_filepath, 'r') as zip_ref:
            zip_ref.extractall(EXTRACT_FOLDER)
            
        choices_main = get_model_choices(show_mb=False)
        choices_delete = get_delete_model_choices(show_mb=True)
        new_value_main = choices_main[0][1] if choices_main and choices_main[0][1] != "none" else None
        new_value_del = choices_delete[0][1] if choices_delete and choices_delete[0][1] != "none" else None
        
        return (gr.update(choices=choices_main, value=new_value_main), 
                gr.update(choices=choices_delete, value=new_value_del), 
                "✅ मॉडल सफलतापूर्वक अपलोड हो गया!")
    except Exception as e:
        return gr.update(), gr.update(), f"❌ एरर: {str(e)}"

def add_model_from_gdrive(url):
    if not url:
        return gr.update(), gr.update(), "❌ कृपया गूगल ड्राइव का लिंक डालें।"
    if gdown is None:
         return gr.update(), gr.update(), "❌ gdown पैकेज लोड नहीं हुआ।"
    try:
        if "folder" in url or "drive.google.com/drive/folders/" in url:
            gdown.download_folder(url, output=EXTRACT_FOLDER, quiet=False, use_cookies=False)
        else:
            temp_zip = "temp_gdrive.zip"
            gdown.download(url, temp_zip, quiet=False, fuzzy=True)
            if zipfile.is_zipfile(temp_zip):
                with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
                    zip_ref.extractall(EXTRACT_FOLDER)
            if os.path.exists(temp_zip):
                os.remove(temp_zip)
                
        choices_main = get_model_choices(show_mb=False)
        choices_delete = get_delete_model_choices(show_mb=True)
        new_value_main = choices_main[0][1] if choices_main and choices_main[0][1] != "none" else None
        new_value_del = choices_delete[0][1] if choices_delete and choices_delete[0][1] != "none" else None
        
        return (gr.update(choices=choices_main, value=new_value_main), 
                gr.update(choices=choices_delete, value=new_value_del), 
                "✅ गूगल ड्राइव से मॉडल सफलतापूर्वक अपलोड हो गया!")
    except Exception as e:
        return gr.update(), gr.update(), f"❌ ड्राइव डाउनलोड एरर: {str(e)}"

def delete_model(model_path):
    if not model_path or model_path == "none":
        return gr.update(), gr.update(), "❌ कृपया डिलीट करने के लिए कोई मॉडल चुनें।"
        
    base_name = os.path.basename(model_path).replace(".onnx", "")
    if base_name in DEFAULT_MODELS:
        return gr.update(), gr.update(), "⚠️ यह एक डिफ़ॉल्ट मॉडल है, इसे डिलीट नहीं किया जा सकता!"
        
    try:
        if os.path.exists(model_path):
            os.remove(model_path)
        json_path_1 = model_path + ".json"
        json_path_2 = model_path.replace(".onnx", ".json")
        if os.path.exists(json_path_1):
            os.remove(json_path_1)
        if os.path.exists(json_path_2):
            os.remove(json_path_2)
        time.sleep(0.5)
        
        choices_main = get_model_choices(show_mb=False)
        choices_delete = get_delete_model_choices(show_mb=True)
        new_value_main = choices_main[0][1] if choices_main and choices_main[0][1] != "none" else None
        new_value_del = choices_delete[0][1] if choices_delete and choices_delete[0][1] != "none" else None
        
        return (gr.update(choices=choices_main, value=new_value_main), 
                gr.update(choices=choices_delete, value=new_value_del), 
                "✅ मॉडल और फाइलें परमानेंटली डिलीट हो गईं!")
    except Exception as e:
        return gr.update(), gr.update(), f"❌ एरर: {str(e)}"

def on_page_load():
    choices_main = get_model_choices(show_mb=False)
    choices_delete = get_delete_model_choices(show_mb=True)
    val_main = choices_main[0][1] if choices_main and choices_main[0][1] != "none" else None
    val_del = choices_delete[0][1] if choices_delete and choices_delete[0][1] != "none" else None
    return (gr.update(choices=choices_main, value=val_main), 
            gr.update(choices=choices_delete, value=val_del))

def clear_audio_player():
    return gr.update(value=None), gr.update(value=""), "⏳ प्रक्रिया शुरू हो रही है... कृपया प्रतीक्षा करें"

def generate_audio(text, model_name, speed, pitch, pause_duration, apply_enhance, do_transliterate, do_autopunctuate, input_secret_key):
    if input_secret_key != MY_SECRET_KEY:
        return None, text, "❌ एरर: अनऑथराइज्ड एक्सेस! सीक्रेट पासवर्ड गलत है।"

    if not text.strip():
        return None, text, "❌ कृपया स्क्रिप्ट बॉक्स में कुछ लिखें।"
    
    if model_name != "none" and not os.path.exists(model_name):
        base_name = os.path.basename(model_name).replace(".onnx", "")
        if base_name in DEFAULT_MODELS:
            try:
                BASE_URL = "https://huggingface.co/Aatika/Aatika-TTS-Voices/resolve/main"
                onnx_url = f"{BASE_URL}/{base_name}.onnx"
                json_url = f"{BASE_URL}/{base_name}.onnx.json"
                urllib.request.urlretrieve(onnx_url, model_name)
                urllib.request.urlretrieve(json_url, f"{model_name}.json")
            except Exception as e:
                return None, text, f"❌ मॉडल डाउनलोड फेल हो गया: {str(e)}"
        else:
            return None, text, "❌ वॉयस मॉडल फाइल नहीं मिली। कृपया पहले मॉडल अपलोड करें।"
            
    config_path = model_name + ".json"
    if not os.path.exists(config_path):
        alt_config_path = model_name.replace(".onnx", ".json")
        if os.path.exists(alt_config_path):
            config_path = alt_config_path
        else:
            return None, text, "❌ एरर: मॉडल की सेटिंग (.json) फाइल नहीं मिली!"

    processed_text = clean_and_transliterate_script(text, do_transliterate=do_transliterate, do_autopunctuate=do_autopunctuate)
    
    unique_id = uuid.uuid4().hex[:8]
    timestamp = int(time.time() * 1000)
    raw_audio = f"raw_audio_{unique_id}_{timestamp}.wav"
    final_audio = f"news_audio_{unique_id}_{timestamp}.wav"
    
    if apply_enhance:
        piper_speed = 1.0 / speed 
        target_pitch = pitch
    else:
        piper_speed = 1.0   
        target_pitch = 1.0  
    
    cmd = [
        "piper", 
        "--model", model_name, 
        "--config", config_path,
        "--output_file", raw_audio,
        "--length_scale", str(piper_speed),
        "--sentence_silence", str(pause_duration)
    ]
    
    try:
        subprocess.run(cmd, input=processed_text.encode('utf-8'), check=True)
        
        target_audio = raw_audio
        pitch_audio = f"pitch_audio_{unique_id}_{timestamp}.wav"
        
        if apply_enhance and target_pitch != 1.0:
            audio_filter = f"aresample=22050,asetrate=22050*{target_pitch},atempo=1/{target_pitch}"
            subprocess.run(["ffmpeg", "-y", "-i", raw_audio, "-af", audio_filter, pitch_audio], 
                         check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            target_audio = pitch_audio

        if apply_enhance:
            if PYDUB_AVAILABLE:
                audio = AudioSegment.from_wav(target_audio)
                audio = audio.set_channels(1)
                audio = audio.high_pass_filter(80)
                audio = audio.normalize()
                audio.export(final_audio, format="wav")
            else:
                enhance_cmd = [
                    "ffmpeg", "-y", "-i", target_audio, 
                    "-ac", "1", 
                    "-af", "highpass=f=80,loudnorm=I=-14:TP=-1.5:LRA=11",
                    final_audio
                ]
                subprocess.run(enhance_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            shutil.copy(target_audio, final_audio)
            
        if os.path.exists(raw_audio):
            os.remove(raw_audio)
        if os.path.exists(pitch_audio):
            os.remove(pitch_audio)
            
        return final_audio, processed_text, "✅ ऑडियो तैयार है!"
    except subprocess.CalledProcessError as e:
        return None, processed_text, f"❌ मॉडल क्रैश हो गया। (Exit Code: {e.returncode})"
    except Exception as e:
        return None, processed_text, f"❌ एरर: {str(e)}"

# मोबाइल पेस्ट के लिए जावास्क्रिप्ट
paste_js = """
async (text, trans, punct) => {
    try {
        const clipboardText = await navigator.clipboard.readText();
        return [clipboardText, trans, punct];
    } catch (err) {
        alert("Clipboard एक्सेस नहीं मिला। कृपया मैन्युअली पेस्ट करें।");
        return [text, trans, punct];
    }
}
"""

# --- UI डिज़ाइन ---
with gr.Blocks(title="Aatika AI Studio Pro") as demo:
    gr.Markdown("<center><h2>🎙️ आर्यन न्यूज़ टेक - AI वॉयस स्टूडियो (Pro)</h2></center>")
    
    with gr.Row():
        with gr.Column(scale=1):
            with gr.Accordion("📂 नया वॉयस मॉडल अपलोड करें", open=False):
                gr.Markdown("### 1. ज़िप (Zip) फाइल से अपलोड करें:")
                upload_box = gr.File(label="Zip फाइल अपलोड करें", file_types=[".zip"])
                upload_btn = gr.Button("अपलोड और सेव करें (Zip)", variant="secondary")
                
                gr.Markdown("---")
                gr.Markdown("### 2. गूगल ड्राइव (Google Drive) लिंक से अपलोड करें:")
                gdrive_input = gr.Textbox(label="Google Drive URL डालें", placeholder="https://drive.google.com/...")
                gdrive_btn = gr.Button("ड्राइव से डाउनलोड और सेव करें ☁️", variant="primary")
                upload_status = gr.Markdown("")
                
        with gr.Column(scale=1):
            with gr.Accordion("🗑️ कस्टम मॉडल डिलीट करें (डिफ़ॉल्ट सुरक्षित हैं)", open=False):
                initial_choices_delete = get_delete_model_choices(show_mb=True)
                delete_dropdown = gr.Dropdown(
                    choices=initial_choices_delete, 
                    value=initial_choices_delete[0][1] if initial_choices_delete else None, 
                    label="हटाने के लिए कस्टम मॉडल चुनें", 
                    interactive=True
                )
                delete_btn = gr.Button("मॉडल परमानेंट डिलीट करें", variant="stop")
                delete_status = gr.Markdown("")
                
    # --- कस्टम डिक्शनरी UI ---
    with gr.Accordion("📝 कस्टम शब्दकोश (अपवादों के लिए)", open=False):
        gr.Markdown("सिस्टम अब HDFC, IMD जैसे कैपिटल शब्दों को अपने आप समझ लेगा। इसका उपयोग सिर्फ तब करें जब कोई खास शब्द गलत ट्रांसलेट हो रहा हो।")
        with gr.Row():
            eng_word_input = gr.Textbox(label="अंग्रेजी शब्द", placeholder="WHO", scale=1)
            hin_word_input = gr.Textbox(label="हिंदी अनुवाद", placeholder="डब्ल्यूएचओ", scale=1)
            add_word_btn = gr.Button("✅ शब्द सेव करें", variant="primary", scale=1)
        
        dict_status = gr.Markdown("")
        
    gr.Markdown("---")
    
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("""
            💡 **नया फीचर:** अब सिस्टम खुद समझ जाएगा कि न्यूज़ एंकर को कहाँ रुकना है। यह अपने-आप लाइनों के अंत में फुल-स्टॉप (।) लगा देगा!
            """)
            
            text_input = gr.Textbox(label="अपनी न्यूज़ स्क्रिप्ट यहाँ पेस्ट करें:", lines=6)
            
            with gr.Row():
                paste_btn = gr.Button("📋 पेस्ट (Paste)", size="sm", variant="secondary")
                convert_btn = gr.Button("✨ ऑटो-फॉर्मेट और कन्वर्ट", size="sm", variant="primary")
                clear_btn = gr.Button("🗑️ मिटाएं", size="sm")
                
            char_count_display = gr.Markdown("📝 **अक्षरों की संख्या:** 0")
            
            transliterate_checkbox = gr.Checkbox(
                label="🌐 जनरेट करते समय अंग्रेजी शब्दों को हिंदी में लिखें (e.g., Bonus -> बोनस, HDFC -> एचडीएफसी)", 
                value=True
            )
            auto_punctuate_checkbox = gr.Checkbox(
                label="✍️ ऑटो-विराम चिह्न - सही जगह रुकने के लिए खुद फुल-स्टॉप (।) लगाएगा", 
                value=True
            )
            
            initial_choices_main = get_model_choices(show_mb=False)
            model_dropdown = gr.Dropdown(
                choices=initial_choices_main, 
                value=initial_choices_main[0][1] if initial_choices_main else None, 
                label="🤖 वॉयस मॉडल चुनें", 
                interactive=True
            )
            active_model_display = gr.Markdown(update_active_model_display(initial_choices_main[0][1] if initial_choices_main else None))
            
            with gr.Row():
                speed_slider = gr.Slider(minimum=0.5, maximum=2.0, value=0.9, step=0.1, label="⚡ स्पीड")
                pitch_slider = gr.Slider(minimum=0.7, maximum=1.3, value=1.0, step=0.05, label="🎵 पिच")
                pause_slider = gr.Slider(minimum=0.0, maximum=2.0, value=0.4, step=0.1, label="⏸️ ठहराव")
            
            enhance_checkbox = gr.Checkbox(
                label="🎙️ स्टूडियो एनहांसमेंट लागू करें", 
                value=True
            )
            
            secret_key_input = gr.Textbox(
                label="🔒 सीक्रेट पासवर्ड", 
                type="password", 
                value=MY_SECRET_KEY
            )

            generate_btn = gr.Button("🚀 न्यूज़ ऑडियो जनरेट करें", variant="primary")
            status_text = gr.Markdown("")
            
        with gr.Column(scale=1):
            audio_output = gr.Audio(label="तैयार न्यूज़ ऑडियो 🎧", type="filepath", autoplay=False)
            processed_script_output = gr.Textbox(
                label="प्रोसेस हुई स्क्रिप्ट (यहाँ ऑटो-सेटअप देख सकते हैं)", 
                lines=8, 
                interactive=False
            )

    # इवेंट्स
    demo.load(fn=on_page_load, inputs=[], outputs=[model_dropdown, delete_dropdown])
    text_input.change(fn=count_characters, inputs=text_input, outputs=char_count_display)
    
    # डिक्शनरी में शब्द जोड़ने का इवेंट
    add_word_btn.click(
        fn=add_new_custom_word,
        inputs=[eng_word_input, hin_word_input, secret_key_input],
        outputs=[dict_status]
    )
    
    def process_pasted_text(text, trans, punct):
        return clean_and_transliterate_script(text, do_transliterate=trans, do_autopunctuate=punct)

    paste_btn.click(
        fn=process_pasted_text, 
        inputs=[text_input, transliterate_checkbox, auto_punctuate_checkbox], 
        outputs=[text_input], 
        js=paste_js
    )
    
    convert_btn.click(
        fn=lambda t, trans, punct: clean_and_transliterate_script(t, do_transliterate=trans, do_autopunctuate=punct), 
        inputs=[text_input, transliterate_checkbox, auto_punctuate_checkbox], 
        outputs=[text_input]
    )
    
    clear_btn.click(lambda: "", outputs=text_input)
    
    model_dropdown.change(fn=update_active_model_display, inputs=[model_dropdown], outputs=[active_model_display])
    
    upload_btn.click(fn=extract_and_update_models, inputs=[upload_box], outputs=[model_dropdown, delete_dropdown, upload_status]
    ).then(fn=update_active_model_display, inputs=[model_dropdown], outputs=[active_model_display])

    gdrive_btn.click(fn=add_model_from_gdrive, inputs=[gdrive_input], outputs=[model_dropdown, delete_dropdown, upload_status]
    ).then(fn=update_active_model_display, inputs=[model_dropdown], outputs=[active_model_display])
    
    delete_btn.click(fn=delete_model, inputs=[delete_dropdown], outputs=[model_dropdown, delete_dropdown, delete_status]
    ).then(fn=update_active_model_display, inputs=[model_dropdown], outputs=[active_model_display])

    generate_btn.click(fn=clear_audio_player, inputs=None, outputs=[audio_output, processed_script_output, status_text]
    ).then(
        fn=generate_audio, 
        inputs=[text_input, model_dropdown, speed_slider, pitch_slider, pause_slider, enhance_checkbox, transliterate_checkbox, auto_punctuate_checkbox, secret_key_input], 
        outputs=[audio_output, processed_script_output, status_text],
        api_name="generate_tts"
    )

if __name__ == "__main__":
    demo.launch()
