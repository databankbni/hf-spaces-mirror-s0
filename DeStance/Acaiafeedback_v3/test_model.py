import json
import re
import argparse
from collections import Counter
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

MODEL_PATH = "strozz1/t5_ef"
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_PATH)
model.generation_config.max_length = None 

def generate(text, labels):
    prompt = f"epistemic_tagging\nexpected labels: {' | '.join(labels)}\ntext: {text}"
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=256)
    outputs = model.generate(**inputs, max_new_tokens=64, num_beams=4)
    return tokenizer.decode(outputs[0], skip_special_tokens=True)

def normalize(label: str) -> str:
    return label.strip().upper().replace(" ", "_")

def extract_ep_tags(text: str) -> list[str]:
    """Extrae todas las etiquetas EP* de un string de output."""
    return re.findall(r'\bEP\w+', text)

def extract_ef_tags(text: str) -> list[str]:
    """Extrae todas las etiquetas EP* de un string de output."""
    return re.findall(r'\bEF\w+', text)

def tags_match(expected_str: str, predicted_str: str) -> bool:
    """Compara etiquetas como multisets."""
    return Counter(extract_ep_tags(expected_str)) == Counter(extract_ep_tags(predicted_str))

def main():
    parser = argparse.ArgumentParser(
        description="Evalúa el modelo T5 sobre un JSON anotado y calcula el % de acierto."
    )
    parser.add_argument("-i", "--input", required=True, help="JSON de entrada (output del parser)")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    samples = [s for s in data if s["etiquetas"]]
    print(f"Frases con etiquetas: {len(samples)} / {len(data)}\n")

    results = []
    correct = 0

    for i, sample in enumerate(samples, 1):
        input_text = sample["input"]
        labels = [normalize(l) for l in sample["etiquetas"]]
        ep_labels = [l for l in labels if l.startswith("EF")]
        predicted = generate(input_text, ep_labels)

        expected = re.sub(r'\b(?!EF)[A-Z][A-Z_]+\b', '', sample["output"])
        expected = re.sub(r'\s+', ' ', expected).strip()

        hit = tags_match(expected, predicted)
        if hit:
            correct += 1

        results.append({
            "input": input_text,
            "output": expected,
            "ep_labels": ep_labels,
            "predicted": predicted,
            "correct": hit
        })

        status = "✓" if hit else "✗"
        print(f"[{i}/{len(samples)}] {status}")
        print(f"  LABELS:    {labels}")
        print(f"  INPUT:     {input_text}")
        print(f"  EXPECTED:  {expected}  → {extract_ef_tags(expected)}")
        print(f"  PREDICTED: {predicted}  → {extract_ef_tags(predicted)}")
        print()

    accuracy = correct / len(samples) * 100 if samples else 0
    print(f"{'='*50}")
    print(f"ACIERTOS: {correct} / {len(samples)}")
    print(f"ACCURACY: {accuracy:.2f}%")
    print(f"{'='*50}\n")

if __name__ == "__main__":
    main()
