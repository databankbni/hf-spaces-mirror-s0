import re
import json
import argparse


def parse_annotated_text(text: str) -> list[dict]:
    sentences_raw = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    results = []

    for sent in sentences_raw:
        labels_found = re.findall(r'<([^>]+)>', sent)
        all_labels = []
        for group in labels_found:
            merged = "_".join(l.strip() for l in group.split(','))
            all_labels.append(merged)

        # <EP, CGA, P> -> <EP_CGA_P>
        sent_normalized = re.sub(
            r'<([^>]+)>',
            lambda m: '<' + '_'.join(l.strip() for l in m.group(1).split(',')) + '>',
            sent
        )

        clean = re.sub(r'\s*<[^>]+>', '', sent_normalized).strip()
        clean = re.sub(r'\s+', ' ', clean)

        results.append({
            "etiquetas": all_labels,
            "input": clean,
            "output": re.sub(r'[<>]', '', sent_normalized).strip()
        })
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Convierte texto anotado con etiquetas <TAG> a JSON estructurado."
    )
    parser.add_argument("-i", "--input", required=True, help="Archivo de texto de entrada (.txt)")
    parser.add_argument("-o", "--output", required=True, help="Archivo de salida (.json)")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        text = f.read()

    results = parse_annotated_text(text)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"Procesadas {len(results)} frases → {args.output}")


if __name__ == "__main__":
    main()
