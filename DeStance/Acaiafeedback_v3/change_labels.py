import re
import json

INPUT_FILES = {
    "EP": "data_ep.json",
    "EF": "data_ef.json"
}

OUTPUT_FILES = {
    "EP": "data_ready_ep.json",
    "EF": "data_ready_ef.json"
}

# FUNCIÓN GENERAL

def process_file(main_label: str, input_file: str, output_file: str):
    other_label = "EF" if main_label == "EP" else "EP"

    main_tag_pattern = re.compile(
        rf"<\s*{main_label}\s*,\s*([^,>\s]+)\s*(?:,\s*([^>\s]+))?\s*>"
    )
    other_tag_pattern = re.compile(
        rf"<\s*{other_label}\s*,\s*[^>]+>"
    )

    def replace_main_tags(text: str) -> str:
        def repl(match):
            part1 = match.group(1).strip()
            part2 = match.group(2).strip() if match.group(2) else None
            return (
                f"{main_label}_{part1}_{part2}"
                if part2 else f"{main_label}_{part1}"
            )
        return main_tag_pattern.sub(repl, text)

    def remove_other_tags(text: str) -> str:
        return other_tag_pattern.sub("", text)

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    updated_data = []

    for item in data:
        text = item.get("output_text", "")
        if main_tag_pattern.search(text) or other_tag_pattern.search(text):
            new_text = replace_main_tags(text)
            new_text = remove_other_tags(new_text)
            new_text = re.sub(r"\s+", " ", new_text).strip()

            item["output_text"] = new_text
            updated_data.append(item)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(updated_data, f, indent=4, ensure_ascii=False)

    print(
        f"✔ {output_file} generado con {len(updated_data)} ítems "
        f"(procesando {main_label})"
    )

# MAIN

def main():
    for label in ("EP", "EF"):
        process_file(
            main_label=label,
            input_file=INPUT_FILES[label],
            output_file=OUTPUT_FILES[label]
        )


if __name__ == "__main__":
    main()
