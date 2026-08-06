import re
import gradio as gr
from transformers import pipeline
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

# IDs DE MODELOS
ROBERTA_EP_ID  = "DeStance/roberta-ep-stance-v2"
T5_EP_ID       = "DeStance/ep_model_v3"
ROBERTA_EF_ID  = "DeStance/roberta-ef-stance-v2"
T5_EF_ID       = "DeStance/ef_model_v5"  
ROBERTA_EMO_ID     = "DeStance/roberta-emo-stance"
ROBERTA_EMO_BIO_ID = "DeStance/bio-v2"

LABEL_THRESHOLD = 0.99

# ── PROMPT BUILDER 
def build_prompt_from_roberta(frases, scores, threshold=0.5):
    prompts = []
    for frase, preds in zip(frases, scores):
        labels = [p["label"] for p in preds if p["score"] >= threshold]
        labels_str = " | ".join(labels) if labels else "NONE"
        prompt = f"epistemic_tagging\nexpected labels: {labels_str}\ntext: {frase}"
        prompts.append(prompt)
    return prompts

# CARGA DE MODELOS

# EP — generador
tokenizer_ep = AutoTokenizer.from_pretrained(T5_EP_ID)
model_ep = AutoModelForSeq2SeqLM.from_pretrained(T5_EP_ID)

def gen_ep(prompt):
    inputs = tokenizer_ep(prompt, return_tensors="pt", truncation=True, max_length=256)
    outputs = model_ep.generate(**inputs, max_new_tokens=64, num_beams=4)
    text = tokenizer_ep.decode(outputs[0], skip_special_tokens=True)
    return [{"generated_text": text}]

# EF — generador
tokenizer_ef = AutoTokenizer.from_pretrained(T5_EF_ID)
model_ef = AutoModelForSeq2SeqLM.from_pretrained(T5_EF_ID)

def gen_ef(prompt):
    inputs = tokenizer_ef(prompt, return_tensors="pt", truncation=True, max_length=256)
    outputs = model_ef.generate(**inputs, max_new_tokens=64, num_beams=4)
    text = tokenizer_ef.decode(outputs[0], skip_special_tokens=True)
    return [{"generated_text": text}]

# Clasificadores RoBERTa
clf_ep = pipeline("text-classification", model=ROBERTA_EP_ID, tokenizer=ROBERTA_EP_ID, top_k=None)
clf_ef = pipeline("text-classification", model=ROBERTA_EF_ID, tokenizer=ROBERTA_EF_ID, top_k=None)
clf_emo = pipeline("text-classification", model=ROBERTA_EMO_ID, tokenizer=ROBERTA_EMO_ID, top_k=None)
ner_emo = pipeline("token-classification", model=ROBERTA_EMO_BIO_ID, tokenizer=ROBERTA_EMO_BIO_ID, aggregation_strategy="simple")



SENT_SPLIT_RE = re.compile(r"(?<=[\,.!?])\s+")

def split_sentences(text: str):
    text = text.strip()
    if not text:
        return []
    return [s for s in SENT_SPLIT_RE.split(text) if s]

EF_LABEL_RE = re.compile(r"\bEF_[A-Z]+(?:_[A-Z]+)*\b")

def filter_t5_labels(t5_text, preds, threshold, modo_tag):
    bad_label = {
        "EP": "NO_EP",
        "EF": "NO_EF",
        "EMO": "NO_EMO",
    }[modo_tag]

    prefix = {
        "EP": "EP_",
        "EF": "EF_",
        "EMO": "EMO_",
    }[modo_tag]

    allowed_labels = {
        p["label"]
        for p in preds
        if float(p["score"]) >= threshold
        and p["label"] != bad_label
        and p["label"].startswith(prefix)
    }

    def replace_label(match):
        label = match.group(0)

        if label in allowed_labels:
            return label

        return ""

    filtered = EF_LABEL_RE.sub(replace_label, t5_text)

    # Limpieza de espacios y puntuación después de eliminar etiquetas
    filtered = re.sub(r"\s{2,}", " ", filtered)
    filtered = re.sub(r"\s+([,.!?;:])", r"\1", filtered)
    filtered = re.sub(r"([,.!?;:])\s*([,.!?;:])+", r"\1", filtered)

    return filtered.strip()

def snap_span_to_word_boundaries(text, start, end):
    n = len(text)
    start, end = max(0, min(start, n)), max(0, min(end, n))
    while start > 0 and WORD_CHAR_RE.match(text[start]) and WORD_CHAR_RE.match(text[start - 1]):
        start -= 1
    while end < n and WORD_CHAR_RE.match(text[end - 1]) and WORD_CHAR_RE.match(text[end]):
        end += 1
    return start, end

def insert_emo_tags_from_ner(sentence, threshold=0.0):
    spans = ner_emo(sentence)
    ents = []
    for s in spans:
        lab = s.get("entity_group") or s.get("entity") or ""
        m = BIO_TAG_RE.match(lab)
        if not m:
            continue
        sc = float(s.get("score", 0.0))
        if sc < threshold:
            continue
        start, end = snap_span_to_word_boundaries(sentence, int(s["start"]), int(s["end"]))
        if end > start:
            ents.append((start, end, m.group(1), sc))
    if not ents:
        return sentence, 0
    ents.sort(key=lambda x: x[0])
    merged = []
    for st, en, tg, sc in ents:
        if merged and tg == merged[-1][2] and st <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], en), tg, max(merged[-1][3], sc))
        else:
            merged.append((st, en, tg, sc))
    merged.sort(key=lambda x: x[1], reverse=True)
    out = sentence
    for st, en, tg, _ in merged:
        out = out[:en] + f" <<{tg}>>" + out[en:]
    return out, len(merged)

# ANOTADOR UI 
def anotador(texto, threshold, max_len, modo):
    texto = texto.strip()
    if not texto:
        return "Introduce algún texto", ""

    if modo == "EF":
        gen, clf, modo_tag, bad_label = gen_ef, clf_ef, "EF", "NO_EF"
    elif modo == "EMO":
        gen, clf, modo_tag, bad_label = None, clf_emo, "EMO", "NO_EMO"
    else:
        gen, clf, modo_tag, bad_label = gen_ep, clf_ep, "EP", "NO_EP"

    frases = split_sentences(texto) or [texto]
    all_raw = clf(frases)

    frases_anotadas = []
    for s, preds in zip(frases, all_raw):
        if modo_tag == "EMO":
            out_s, _ = insert_emo_tags_from_ner(s, threshold=threshold)
        elif any((p["label"] != bad_label) and (p["score"] >= threshold) for p in preds):
            prompt = build_prompt_from_roberta([s], [preds], threshold=threshold)[0]
            t5_raw = gen(prompt)[0]["generated_text"]
            out_s = filter_t5_labels(t5_raw, preds, threshold, modo_tag)
            print(f"PROMPT: {prompt}\nT5 RAW: {t5_raw}\nFILTERED: {out_s}\n")
        else:
            out_s = s
        frases_anotadas.append(out_s)

    generado = " ".join(frases_anotadas)

    lineas = []
    for i, preds in enumerate(all_raw, start=1):
        for p in sorted(preds, key=lambda p: p["score"], reverse=True):
            if p["score"] >= threshold:
                lineas.append(f"[{modo_tag}][S{i}] {p['label']}  {p['score']:.3f}")
    listado = "\n".join(lineas) if lineas else "No hay etiquetas (>= umbral)."
    return generado, listado

# API
def classify(text: str, model_choice: str = "ep_model"):
    text = text.strip()
    if not text:
        return {"annotated": "", "labels": []}

    if model_choice == "ep_model":
        gen, clf, modo_tag, bad_label = gen_ep, clf_ep, "EP", "NO_EP"
    elif model_choice == "ef_model":
        gen, clf, modo_tag, bad_label = gen_ef, clf_ef, "EF", "NO_EF"
    elif model_choice == "emo_model":
        gen, clf, modo_tag, bad_label = None, clf_emo, "EMO", "NO_EMO"
    else:
        return {"annotated": "", "labels": []}

    frases = split_sentences(text) or [text]
    all_raw = clf(frases)

    annotated_parts = []
    for s, preds in zip(frases, all_raw):
        if modo_tag == "EMO":
            out_s, _ = insert_emo_tags_from_ner(s, threshold=LABEL_THRESHOLD)
        elif any((p["label"] != bad_label) and (p["score"] >= LABEL_THRESHOLD) for p in preds):
            prompt = build_prompt_from_roberta([s], [preds], threshold=LABEL_THRESHOLD)[0]
            t5_raw = gen(prompt)[0]["generated_text"]
            out_s = filter_t5_labels(t5_raw, preds, LABEL_THRESHOLD, modo_tag)
        else:
            out_s = s
        annotated_parts.append(out_s)

    BAD_LABELS = {"NO_EP", "NO_EF", "NO_EMO"}
    labels = [
        {"label": f"[{modo_tag}][S{i}] {p['label']}", "score": float(p["score"])}
        for i, preds in enumerate(all_raw, start=1)
        for p in preds
        if float(p["score"]) >= LABEL_THRESHOLD and p["label"] not in BAD_LABELS
    ]

    return {"annotated": " ".join(annotated_parts), "labels": labels}

# GRADIO UI 
with gr.Blocks() as demo:
    gr.Markdown("# Anotador (EP / EF / EMO) con T5 + RoBERTa")
    with gr.Row():
        inp_txt = gr.Textbox(lines=6, label="Texto limpio")
    with gr.Row():
        thr     = gr.Slider(0.0, 1.0, value=0.5, step=0.01, label="Umbral mínimo (RoBERTa)")
        max_len = gr.Slider(32, 512, value=256, step=8, label="Longitud máxima generación (T5)")
        modo    = gr.Radio(choices=["EP", "EF", "EMO"], value="EP", label="Tipo de anotación")
    with gr.Row():
        out_anotado = gr.Textbox(lines=6, label="Texto anotado")
        out_labels  = gr.Textbox(lines=8, label="Etiquetas")
    btn = gr.Button("Anotar")
    btn.click(anotador, inputs=[inp_txt, thr, max_len, modo], outputs=[out_anotado, out_labels])

    hidden_text  = gr.Textbox(visible=False)
    hidden_model = gr.Textbox(visible=False)
    hidden_out   = gr.JSON(visible=False)
    hidden_btn   = gr.Button(visible=False)
    hidden_btn.click(fn=classify, inputs=[hidden_text, hidden_model], outputs=[hidden_out], api_name="predict")

if __name__ == "__main__":
    demo.launch()
    