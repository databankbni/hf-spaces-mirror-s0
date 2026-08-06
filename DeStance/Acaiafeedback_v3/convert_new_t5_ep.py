import json
import re

INPUT_FILE = "data_ready_ef.json"
OUTPUT_FILE = "new_t5_ef.json"

LABEL_PATTERN = re.compile(r"\bEF(?:_[A-Z]+)+\b")
with open(INPUT_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

new_data = []

for ex in data:
    output_text = ex["output_text"]

    labels = LABEL_PATTERN.findall(output_text)
    new_ex = {
        "labels": labels,
        "input_text": ex["input_text"],
        "output_text": ex["output_text"]
    }

    new_data.append(new_ex)

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(new_data, f, ensure_ascii=False, indent=4)

print(f"Procesados {len(new_data)} ejemplos")
