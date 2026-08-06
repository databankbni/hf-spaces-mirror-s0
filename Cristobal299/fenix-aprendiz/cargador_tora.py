# -*- coding: utf-8 -*-
"""
Cargador de la Torá (u otros libros) desde JSON para Fénix Aprendiz.
Extrae el texto de varios formatos JSON comunes y lo deja listo para trocear
e indexar en la biblioteca de Supabase igual que un PDF.

Cómo integrarlo en fenix_core.py:
  1) Pega este archivo como  cargador_tora.py  junto a fenix_core.py.
  2) En fenix_core.py añade una función gemela de procesar_pdf:

        from cargador_tora import extraer_texto_json

        def procesar_json(ruta_json, nombre_archivo=None):
            nombre_archivo = nombre_archivo or os.path.basename(ruta_json)
            if not sb:
                return "Supabase no está configurado."
            if documento_ya_existe(nombre_archivo):
                return f"'{nombre_archivo}' ya estaba cargado. Bórralo antes si quieres recargarlo."
            texto = extraer_texto_json(ruta_json)
            if not texto.strip():
                return f"No pude extraer texto de '{nombre_archivo}'."
            chunks = trocear_texto(texto)
            guardados = guardar_documento(nombre_archivo, chunks)
            return f"'{nombre_archivo}': {guardados}/{len(chunks)} fragmentos indexados."

  3) En app.py, junto al cargador de PDF, añade uno de JSON (gr.File con .json)
     que llame a procesar_json. O súbelo por Termux y llama a procesar_json.
"""
import json


def _es_versiculo(d):
    return isinstance(d, dict) and any(k in d for k in ("he", "es", "texto", "text", "verse", "t"))


def _texto_de_verso(v):
    partes = [str(v[k]).strip() for k in ("he", "es", "texto", "text", "t") if v.get(k)]
    return " ".join(partes)


def extraer_texto_json(ruta_json) -> str:
    """Devuelve un texto plano con referencias (Libro cap:versículo) cuando el
    formato lo permite; si no reconoce la estructura, extrae todas las cadenas."""
    with open(ruta_json, encoding="utf-8") as f:
        data = json.load(f)

    lineas = []

    # Formato Centralita: {"id","es","capitulos":{"1":[{"n","he","es"}]}}
    if isinstance(data, dict) and "capitulos" in data and isinstance(data["capitulos"], dict):
        libro = data.get("es") or data.get("id") or "Libro"
        for cap, versos in data["capitulos"].items():
            if isinstance(versos, list):
                for v in versos:
                    txt = _texto_de_verso(v) if isinstance(v, dict) else str(v)
                    if txt.strip():
                        n = v.get("n", "") if isinstance(v, dict) else ""
                        lineas.append(f"{libro} {cap}:{n} {txt}".strip())
        if lineas:
            return "\n".join(lineas)

    # Lista de versículos: [{"book"/"libro","chapter"/"capitulo","verse"/"versiculo","text"/...}]
    if isinstance(data, list) and data and isinstance(data[0], dict):
        for v in data:
            libro = v.get("book") or v.get("libro") or ""
            cap = v.get("chapter") or v.get("capitulo") or ""
            ver = v.get("verse") or v.get("versiculo") or v.get("n") or ""
            txt = _texto_de_verso(v)
            ref = f"{libro} {cap}:{ver}".strip()
            if txt.strip():
                lineas.append(f"{ref} {txt}".strip())
        if lineas:
            return "\n".join(lineas)

    # Dict anidado: {"Genesis": {"1": {"1": "texto", ...}}}  o  {"Genesis": {"1": ["v1", ...]}}
    if isinstance(data, dict):
        anidado = False
        for libro, caps in data.items():
            if isinstance(caps, dict):
                for cap, versos in caps.items():
                    if isinstance(versos, dict):
                        for ver, txt in versos.items():
                            if isinstance(txt, str) and txt.strip():
                                lineas.append(f"{libro} {cap}:{ver} {txt.strip()}")
                                anidado = True
                    elif isinstance(versos, list):
                        for i, txt in enumerate(versos, 1):
                            t = _texto_de_verso(txt) if isinstance(txt, dict) else str(txt)
                            if t.strip():
                                lineas.append(f"{libro} {cap}:{i} {t.strip()}")
                                anidado = True
        if anidado and lineas:
            return "\n".join(lineas)

    # Fallback universal: recoge TODAS las cadenas de texto del JSON
    def recolectar(x):
        if isinstance(x, str):
            if x.strip():
                lineas.append(x.strip())
        elif isinstance(x, dict):
            for val in x.values():
                recolectar(val)
        elif isinstance(x, list):
            for val in x:
                recolectar(val)
    recolectar(data)
    return "\n".join(lineas)


if __name__ == "__main__":
    import sys
    print(extraer_texto_json(sys.argv[1])[:1500])
