"""
hebreo.py
=========
Capa de EXPERTO EN HEBREO para el Space del Jardín, hecha aparte para NO tocar
nada de fenix_core.py. Es determinista: consulta un diccionario (léxico Strong)
que tú mismo curas y devuelve el dato REAL (raíz, transliteración, nº Strong,
glosa, tu traducción al español). No inventa. La IA no interviene en la consulta;
solo aparece, opcionalmente, como "locutor" al final para redactar en español
lo que el diccionario YA dijo — con la correa muy corta (prohibido inventar).

Filosofía (la lección del aprendiz): un chat abierto con "todo el hebreo dentro"
predica; un experto de verdad CONSULTA datos estructurados y solo entonces habla.

── CÓMO ENCHUFARLO (no toca fenix_core.py ni app.py más que para importarlo) ──
1) Sube tu diccionario Strong como fichero JSON en el Space (junto a este .py).
   Por defecto se busca 'lexico_hebreo.json'. Cambia RUTA_LEXICO si tiene otro
   nombre. Formato admitido: dict {"H1234": {...}} O lista [{...}, ...].
2) En app.py:
       from hebreo import formatear_consulta_hebreo, explicar_hebreo
   y en una pestaña nueva de Gradio, un Textbox + botón ->
       formatear_consulta_hebreo(texto)            # 100% sin IA
   o, si quieres que lo redacte en prosa:
       explicar_hebreo(texto, con_ia=True)         # dato + locutor IA
3) Nada más. Si el JSON no existe o falla, las funciones lo dicen con calma y
   el resto del Space sigue igual.

NOTA sobre tus campos: no sé los nombres EXACTOS de las claves de tu JSON, así
que CAMPOS más abajo prueba varios alias comunes. Si tu diccionario usa otros
nombres, añádelos ahí (es la única línea que quizá tengas que tocar) y dímelo
para dejarlo clavado.
"""

import os
import re
import json
import unicodedata

# --------------------------------------------------------------------------
# Configuración
# --------------------------------------------------------------------------

# Fichero JSON con tu léxico Strong (súbelo al Space, junto a este archivo).
RUTA_LEXICO = os.environ.get("RUTA_LEXICO", "lexico_hebreo.json")

# Alias de nombres de campo: para cada dato que mostramos, la lista de posibles
# claves en TU JSON, en orden de preferencia. Si tu diccionario usa otro nombre,
# añádelo a la lista correspondiente. Es lo único que quizá debas ajustar.
CAMPOS = {
    "strong":   ["strong", "numero", "id", "strong_number", "num"],
    "hebreo":   ["lemma", "hebreo", "palabra", "word", "original", "heb", "lema"],
    "translit": ["translit", "transliteracion", "xlit", "pron", "pronunciacion",
                 "transliteration"],
    "raiz":     ["raiz", "root", "shoresh", "raiz_es"],
    "gloss_en": ["gloss", "gloss_en", "strongs_def", "definicion_en", "ingles",
                 "meaning", "definition"],
    "es":       ["translation_es", "es", "espanol", "español", "traduccion",
                 "traduccion_es", "significado", "definicion", "glosa_es"],
    "morf":     ["morf", "morfologia", "pos", "tipo", "part_of_speech"],
}

# --------------------------------------------------------------------------
# Normalización del hebreo (para que la búsqueda case con o sin puntos/vocales)
# --------------------------------------------------------------------------

# Rango de niqud (vocales), teamim (cantilación) y marcas que quitamos para
# comparar solo las consonantes. También pasamos finales a su forma normal.
_DIACRITICOS_HEB = re.compile(r"[\u0591-\u05C7]")   # teamim + niqud + meteg, etc.
_FINALES = {"\u05DA": "\u05DB",  # ך -> כ
            "\u05DD": "\u05DE",  # ם -> מ
            "\u05DF": "\u05E0",  # ן -> נ
            "\u05E3": "\u05E4",  # ף -> פ
            "\u05E5": "\u05E6"}  # ץ -> צ
_ES_HEBREO = re.compile(r"[\u0590-\u05FF]")
_STRONG_RE = re.compile(r"^[hH]?0*(\d{1,5})$")


def _normalizar_hebreo(txt: str) -> str:
    """Deja solo consonantes hebreas: quita niqud/cantilación, maqaf y espacios,
    y convierte letras finales (ך ם ן ף ץ) a su forma normal, para que la misma
    palabra case esté donde esté en el versículo."""
    if not txt:
        return ""
    t = unicodedata.normalize("NFC", txt)
    t = _DIACRITICOS_HEB.sub("", t)
    t = t.replace("\u05BE", "").replace("\u05C0", "").replace("\u05C3", "")
    t = "".join(_FINALES.get(c, c) for c in t)
    return "".join(c for c in t if _ES_HEBREO.match(c))


def _normalizar_strong(txt: str):
    """'H1234', 'h01234', '1234' -> 'H1234'. Devuelve None si no es un Strong."""
    if not txt:
        return None
    m = _STRONG_RE.match(txt.strip())
    return f"H{int(m.group(1))}" if m else None


def _sin_tildes_min(txt: str) -> str:
    base = unicodedata.normalize("NFD", (txt or "").lower())
    return "".join(c for c in base if unicodedata.category(c) != "Mn")


def _campo(entrada: dict, clave_logica: str) -> str:
    """Lee un dato de una entrada probando los alias de CAMPOS por orden."""
    for k in CAMPOS.get(clave_logica, []):
        if k in entrada and entrada[k] not in (None, "", []):
            v = entrada[k]
            return ", ".join(map(str, v)) if isinstance(v, list) else str(v)
    return ""


# --------------------------------------------------------------------------
# Carga e indexado del léxico (una sola vez, cacheado en memoria)
# --------------------------------------------------------------------------

_LEXICO = None          # lista de entradas normalizadas
_IDX_STRONG = None      # {'H1234': entrada}
_IDX_HEBREO = None      # {consonantes: [entradas]}
_ERROR_CARGA = None     # mensaje si algo falló al cargar


def _cargar_lexico():
    """Carga el JSON del disco y construye los índices. Idempotente: si ya está
    cargado no vuelve a leer. Tolera dict {'H..':{}} o lista [{}]."""
    global _LEXICO, _IDX_STRONG, _IDX_HEBREO, _ERROR_CARGA
    if _LEXICO is not None or _ERROR_CARGA is not None:
        return

    if not os.path.exists(RUTA_LEXICO):
        _ERROR_CARGA = (f"No encuentro el diccionario '{RUTA_LEXICO}'. Súbelo al "
                        f"Space (o ajusta RUTA_LEXICO en hebreo.py).")
        return
    try:
        with open(RUTA_LEXICO, "r", encoding="utf-8") as f:
            crudo = json.load(f)
    except Exception as e:
        _ERROR_CARGA = f"No pude leer '{RUTA_LEXICO}': {e}"
        return

    entradas = []
    if isinstance(crudo, dict):
        # dict {"H1234": {...}} — metemos la clave dentro como strong si falta.
        for clave, val in crudo.items():
            if isinstance(val, dict):
                val = dict(val)
                if not _campo(val, "strong"):
                    val["strong"] = clave
                entradas.append(val)
    elif isinstance(crudo, list):
        entradas = [e for e in crudo if isinstance(e, dict)]

    _IDX_STRONG, _IDX_HEBREO = {}, {}
    for e in entradas:
        s = _normalizar_strong(_campo(e, "strong"))
        if s:
            _IDX_STRONG.setdefault(s, e)
        heb = _normalizar_hebreo(_campo(e, "hebreo"))
        if heb:
            _IDX_HEBREO.setdefault(heb, []).append(e)

    _LEXICO = entradas


# --------------------------------------------------------------------------
# Consulta (el corazón determinista — SIN IA)
# --------------------------------------------------------------------------

def consultar_hebreo(consulta: str, max_resultados: int = 8):
    """Busca en el léxico y devuelve una lista de entradas (dicts crudos de TU
    JSON). Detecta sola qué le preguntas:
      · nº Strong  ('H430', '430')      -> match exacto por número
      · hebreo     ('אלהים', con o sin puntos) -> match por consonantes
      · español/inglés ('dios', 'light') -> entradas cuya glosa lo contenga
    Es determinista: nunca inventa. Lista vacía = no está en tu diccionario."""
    _cargar_lexico()
    if _ERROR_CARGA:
        return []
    consulta = (consulta or "").strip()
    if not consulta:
        return []

    # 1) ¿Es un número de Strong?
    s = _normalizar_strong(consulta)
    if s and s in _IDX_STRONG:
        return [_IDX_STRONG[s]]

    # 2) ¿Lleva letras hebreas? -> búsqueda por consonantes
    if _ES_HEBREO.search(consulta):
        heb = _normalizar_hebreo(consulta)
        if heb in _IDX_HEBREO:
            return _IDX_HEBREO[heb][:max_resultados]
        # tolerante: prefijo (por si arrastra artículo/conjunción vav, he, etc.)
        parciales = [ent for clave, lista in _IDX_HEBREO.items()
                     if heb and (clave.endswith(heb) or heb.endswith(clave))
                     for ent in lista]
        return parciales[:max_resultados]

    # 3) Palabra en español/inglés -> buscar dentro de glosa_es y gloss_en
    objetivo = _sin_tildes_min(consulta)
    aciertos = []
    for e in (_LEXICO or []):
        campos = _sin_tildes_min(_campo(e, "es") + " | " + _campo(e, "gloss_en"))
        if objetivo and objetivo in campos:
            # exacto de palabra puntúa más que "contenido dentro de otra"
            peso = 2 if re.search(rf"\b{re.escape(objetivo)}\b", campos) else 1
            aciertos.append((peso, e))
    aciertos.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in aciertos[:max_resultados]]


def _formatear_entrada(e: dict) -> str:
    """Una entrada del léxico -> texto limpio y legible (sin IA)."""
    strong   = _normalizar_strong(_campo(e, "strong")) or _campo(e, "strong")
    hebreo   = _campo(e, "hebreo")
    translit = _campo(e, "translit")
    raiz     = _campo(e, "raiz")
    es       = _campo(e, "es")
    gloss    = _campo(e, "gloss_en")
    morf     = _campo(e, "morf")

    cabecera = " · ".join(p for p in [hebreo, translit, strong] if p)
    lineas = [cabecera or "(entrada)"]
    if es:
        lineas.append(f"Español: {es}")
    if gloss and gloss.lower() not in es.lower():
        lineas.append(f"Glosa: {gloss}")
    if raiz:
        lineas.append(f"Raíz: {raiz}")
    if morf:
        lineas.append(f"Morfología: {morf}")
    return "\n".join(lineas)


def formatear_consulta_hebreo(consulta: str, max_resultados: int = 8) -> str:
    """Punto de entrada 100% SIN IA para la interfaz: devuelve el/los resultados
    ya formateados, o un mensaje claro si no hay diccionario o no hay match."""
    _cargar_lexico()
    if _ERROR_CARGA:
        return f"⚠️ {_ERROR_CARGA}"
    res = consultar_hebreo(consulta, max_resultados)
    if not res:
        return (f"No encuentro «{consulta}» en el diccionario. Puede que aún no "
                f"esté curada esa palabra, o que lleve un prefijo (artículo, vav) "
                f"que conviene quitar.")
    if len(res) == 1:
        return _formatear_entrada(res[0])
    bloques = [f"{i+1}. {_formatear_entrada(e)}" for i, e in enumerate(res)]
    return f"{len(res)} coincidencias para «{consulta}»:\n\n" + "\n\n".join(bloques)


# --------------------------------------------------------------------------
# Locutor IA opcional (correa corta): solo REDACTA el dato, no lo inventa.
# Reusa la rotación de claves de fenix_core sin arrastrar la personalidad
# de gurú. Si fenix_core no está o falla, cae al texto determinista.
# --------------------------------------------------------------------------

_SYS_LINGUISTA = (
    "Eres un lingüista del hebreo bíblico, sobrio y preciso. Te paso DATOS ya "
    "verificados de un diccionario Strong sobre una o varias palabras. Tu ÚNICA "
    "tarea es explicarlos en español claro y ordenado. Está PROHIBIDO: inventar "
    "significados, raíces o números que no estén en los datos; añadir interpretación "
    "teológica, mística o devocional; parafrasear la Escritura. Si un dato no consta, "
    "di 'no consta'. Responde en prosa breve, sin markdown."
)


def _frase_ia(datos_texto: str, pregunta: str) -> str:
    """Redacta con IA usando SOLO los datos. Devuelve None si no hay forma de
    llamar al modelo (para caer al texto determinista sin romper nada)."""
    prompt_user = (f"Palabra(s) consultada(s): {pregunta}\n\n"
                   f"Datos del diccionario (única fuente permitida):\n{datos_texto}\n\n"
                   f"Explícalo respetando las reglas.")
    mensajes = [{"role": "system", "content": _SYS_LINGUISTA},
                {"role": "user", "content": prompt_user}]
    try:
        import fenix_core as fc
    except Exception:
        return None

    # NVIDIA primero (pequeño y rápido), Cerebras de respaldo — igual criterio
    # que tu preguntar_fenix, pero con SYSTEM limpio de lingüista.
    try:
        if getattr(fc, "NVIDIA_KEYS_POOL", None):
            for modelo in fc.MODELOS_ALUMNO_NVIDIA:
                for _ in range(len(fc.NVIDIA_KEYS_POOL)):
                    try:
                        return fc.llamar_nvidia_nim_chat(
                            api_key=fc.NVIDIA_KEYS_POOL[0], model=modelo,
                            messages=mensajes, temperature=0.1, max_tokens=1024)
                    except Exception as e:
                        print(f"[hebreo] NVIDIA {modelo} falló: {e}. Roto clave.")
                        fc.rotar_clave_nvidia_fallida()
        if getattr(fc, "CEREBRAS_KEYS_POOL", None):
            for _ in range(max(len(fc.CEREBRAS_KEYS_POOL), 2)):
                try:
                    return fc.llamar_cerebras_directo(
                        api_key=fc.CEREBRAS_KEYS_POOL[0], model=fc.MODELO_FENIX,
                        messages=mensajes, temperature=0.1, max_tokens=1024,
                        reasoning_effort="low")
                except Exception as e:
                    print(f"[hebreo] Cerebras falló: {e}. Roto clave.")
                    fc.rotar_clave_cerebras_fallida()
    except Exception as e:
        print(f"[hebreo] Sin IA disponible: {e}")
    return None


def explicar_hebreo(consulta: str, con_ia: bool = False, max_resultados: int = 8) -> str:
    """Consulta el diccionario (determinista) y, si con_ia=True y hay modelo
    disponible, deja que la IA lo redacte en prosa SIN salirse de esos datos.
    Si la IA no está o falla, devuelve el texto determinista tal cual."""
    base = formatear_consulta_hebreo(consulta, max_resultados)
    if not con_ia or base.startswith("⚠️") or base.startswith("No encuentro"):
        return base
    redaccion = _frase_ia(base, consulta)
    return redaccion.strip() if redaccion else base


# --------------------------------------------------------------------------
# Prueba rápida por consola (no afecta al Space):  python hebreo.py אלהים
# --------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "H430"
    print(formatear_consulta_hebreo(q))
