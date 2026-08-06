"""
fenix_core.py
Núcleo espiritual de Fénix Teshuá con soporte para rotación automática de 5 API Keys
para Cerebras (alumno) y NVIDIA (maestro), persistencia en Supabase y generación de
voz mística (edge-tts). Usa la librería estándar de Python para ambos proveedores,
evitando dependencias externas (sin SDK de Groq, Cerebras ni openai).
"""

import os
import json
import re
import asyncio
import tempfile
import time
import subprocess
import base64
import hashlib
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone

from supabase import create_client
import pypdf
import edge_tts

# --- Pools Globales de Claves de Inferencia para evitar Rate Limits ---
CEREBRAS_KEYS_POOL = []
NVIDIA_KEYS_POOL = []

# Carga de claves iniciales (Soporta variables CEREBRAS_KEY, CEREBRAS_KEY_1 a CEREBRAS_KEY_5)
for suffix in ["", "_1", "_2", "_3", "_4", "_5"]:
    c_key = os.environ.get(f"CEREBRAS_KEY{suffix}") or os.environ.get(f"CEREBRAS_API_KEY{suffix}")
    if c_key and c_key not in CEREBRAS_KEYS_POOL:
        CEREBRAS_KEYS_POOL.append(c_key)

    n_key = os.environ.get(f"NVIDIA_KEY{suffix}") or os.environ.get(f"NVIDIA_API_KEY{suffix}")
    if n_key and n_key not in NVIDIA_KEYS_POOL:
        NVIDIA_KEYS_POOL.append(n_key)

# Fallbacks si no están numeradas
if not CEREBRAS_KEYS_POOL and os.environ.get("CEREBRAS_KEY"):
    CEREBRAS_KEYS_POOL.append(os.environ.get("CEREBRAS_KEY"))
if not NVIDIA_KEYS_POOL and os.environ.get("NVIDIA_KEY"):
    NVIDIA_KEYS_POOL.append(os.environ.get("NVIDIA_KEY"))

# Inicialización del cliente Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

sb = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# Configuración de modelos
# Alumno: Cerebras (gpt-oss-120b, rapidísimo en su hardware wafer-scale)
# Maestro: NVIDIA NIM, probando en cadena varios modelos confirmados por el
# usuario (con curl, todos devolvieron 200) antes de caer al respaldo de Cerebras.
MODELO_FENIX = "gpt-oss-120b"

# ALUMNO (la respuesta que lee la persona): AHORA NVIDIA primero con un modelo
# pequeño y rápido, y Cerebras de respaldo. La cadena empieza por el 8B (mini,
# instantáneo y muy estable) para cumplir "rápido y pequeño que no dé fallos";
# si tu cuenta no lo tuviera habilitado, rota solo a los modelos que ya
# confirmaste con curl (200) antes de caer al respaldo de Cerebras. Cambia el
# primer nombre si quieres otro modelo mini.
MODELOS_ALUMNO_NVIDIA = [
    "meta/llama-3.3-70b-instruct",
    "nvidia/llama-3.3-nemotron-super-49b-v1",
    "meta/llama-3.1-8b-instruct",
]

MODELOS_MAESTRO_NVIDIA = [
    # PRIMERO el modelo pequeño y rápido: evalúa en segundos y evita los
    # read-timeout en cadena que daban los gigantes (49b/70b/675b tardaban
    # más de lo que aguantaba el timeout y caían uno tras otro a Cerebras).
    # Los grandes quedan de respaldo por si el 8b fallara o no estuviera
    # habilitado en tu cuenta.
    "meta/llama-3.1-8b-instruct",
    "nvidia/llama-3.3-nemotron-super-49b-v1",
    "meta/llama-3.3-70b-instruct",
    "mistralai/mistral-large-3-675b-instruct-2512",
]
MODELO_MAESTRO_CEREBRAS = "gpt-oss-120b"

# Visión (gratis vía NVIDIA NIM, reutiliza el mismo pool NVIDIA_KEYS_POOL).
# Se prueban en cadena: si el 90b falla o se agota, se cae al 11b.
MODELOS_VISION_NVIDIA = [
    "meta/llama-3.2-90b-vision-instruct",
    "meta/llama-3.2-11b-vision-instruct",
]

PERSONALIDAD_BASE = (
    "Responde ÚNICAMENTE con base en el contenido que se te proporciona más abajo "
    "(fragmentos de la base de datos, lecciones y contexto). No inventes ni añadas "
    "información que no esté en ese contenido; si no encuentras la respuesta ahí, dilo "
    "con honestidad en vez de rellenar con suposiciones.\n\n"
    "Escribes SIEMPRE en prosa fluida y hablada, como quien habla en voz alta, nunca como "
    "un documento o manual técnico. Por eso NUNCA uses formato Markdown de ningún tipo: nada "
    "de encabezados ('#', '##', '###'), nada de negritas ni cursivas con asteriscos o guiones "
    "bajos ('**texto**', '_texto_'), nada de líneas separadoras ('---'), nada de listas con "
    "guiones. Si necesitas enumerar pasos o ideas, hazlo dentro de tu propia prosa "
    "('primero...', 'luego...', 'y por último...'), nunca con símbolos de lista. "
    "Nunca escribas etiquetas de evaluación como '(maestro: ...)': eso es metadato interno, no parte de tu voz."
)

# Configuración de Edge-TTS
VOZ_FENIX = "es-ES-AlvaroNeural"
VOZ_PITCH = "-22Hz"
VOZ_RATE = "-6%"

# Filtro de eco/reverberación de post-proceso (ffmpeg -af). None o "" = sin eco.
# Cada voz mística puede tener su propia "firma" de resonancia en vez de una sola.
VOZ_ECO_FILTRO = None

# Firma de eco del "Eco del Anciano": corto y cercano, como una cámara o caverna.
ECO_CAVERNA = "aecho=0.7:0.7:40|150:0.15|0.20,volume=1.00"

# Firma de eco de la "Voz de Teshuá": tres capas, decaimiento largo y difuso,
# pensada para sonar como una resonancia que se expande hacia el origen en vez
# de rebotar cerca del oyente — el eco del Retorno, no el de una habitación.
ECO_TESHUA = "aecho=0.9:0.05:50|400|700:0.20|0.20|0.01,volume=1.00"

# FIX BUSQUEDA: stopwords en español. Antes el filtro era solo len(palabra) > 3,
# y palabras como "dime", "todos", "sobre" o "puede" pasaban el corte, aparecen en
# casi cualquier chunk y convertian la puntuacion por coincidencias en ruido puro.
STOPWORDS_ES = {
    "para", "como", "sobre", "dime", "dame", "dice", "dicen", "todo", "todos",
    "todas", "toda", "donde", "cuando", "porque", "pero", "este", "esta",
    "estos", "estas", "tiene", "tienen", "hace", "hacer", "desde", "hasta",
    "entre", "segun", "según", "cual", "cuál", "cuales", "cuáles", "quien",
    "quién", "quienes", "puede", "pueden", "puedo", "quiero", "quieres",
    "algo", "alguien", "cosa", "cosas", "muy", "más", "menos", "también",
    "tambien", "ellos", "ellas", "nosotros", "vosotros", "ustedes", "usted",
    "gustaria", "gustaría", "podrias", "podrías", "sabes", "saber", "eres",
    "esto", "eso", "aquello", "aqui", "aquí", "alli", "allí", "unos", "unas",
}

_ACENTOS = str.maketrans("áéíóúü", "aeiouu")


def _palabras_clave(texto: str, max_palabras: int = 6):
    """Extrae las palabras significativas de una pregunta (sin stopwords),
    devolviendo tambien la variante sin acentos para ampliar coincidencias."""
    if not texto:
        return []
    crudas = re.findall(r"[a-záéíóúüñ]{4,}", texto.lower())
    palabras = []
    for w in crudas:
        if w in STOPWORDS_ES or w in palabras:
            continue
        palabras.append(w)
        if len(palabras) >= max_palabras:
            break
    # Variantes sin acento (p.ej. "oración" tambien busca "oracion")
    variantes = []
    for w in palabras:
        variantes.append(w)
        sin = w.translate(_ACENTOS)
        if sin != w and sin not in variantes:
            variantes.append(sin)
    return variantes


def actualizar_claves_dinamicas(lista_cerebras, lista_nvidia):
    """Actualiza en caliente los pools mutando las listas existentes sin romper referencias.
    FIX SEGURIDAD/ESTABILIDAD: antes esta funcion vaciaba SIEMPRE los dos pools,
    asi que una llamada con casillas vacias dejaba el sistema entero sin claves.
    Ahora solo reemplaza el pool para el que llegan claves nuevas no vacias."""
    global CEREBRAS_KEYS_POOL, NVIDIA_KEYS_POOL
    c = [k.strip() for k in (lista_cerebras or []) if k and k.strip()]
    n = [k.strip() for k in (lista_nvidia or []) if k and k.strip()]
    if c:
        CEREBRAS_KEYS_POOL.clear()
        CEREBRAS_KEYS_POOL.extend(c)
    if n:
        NVIDIA_KEYS_POOL.clear()
        NVIDIA_KEYS_POOL.extend(n)
    print(f"Pools actualizados dinámicamente. Cerebras: {len(CEREBRAS_KEYS_POOL)} claves | NVIDIA: {len(NVIDIA_KEYS_POOL)} claves.")


def rotar_clave_cerebras_fallida():
    """Mueve la clave fallida al final para reintentar con la siguiente de inmediato."""
    global CEREBRAS_KEYS_POOL
    if len(CEREBRAS_KEYS_POOL) > 1:
        CEREBRAS_KEYS_POOL.append(CEREBRAS_KEYS_POOL.pop(0))
        print("🔄 Clave de Cerebras rotada debido a límites de cuota o error.")


def rotar_clave_nvidia_fallida():
    """Mueve la clave de NVIDIA fallida al final de la cola."""
    global NVIDIA_KEYS_POOL
    if len(NVIDIA_KEYS_POOL) > 1:
        NVIDIA_KEYS_POOL.append(NVIDIA_KEYS_POOL.pop(0))
        print("🔄 Clave de NVIDIA rotada debido a límites de cuota o error.")


def _extraer_contenido(mensaje: dict) -> str:
    """Extrae el texto de un mensaje de la API de forma robusta.
    FIX ERROR 'content': algunos modelos de razonamiento devuelven el texto
    real en 'reasoning_content' cuando 'content' viene vacío o ausente (p.ej.
    tras rotar de clave o con ciertos parámetros de reasoning_effort). Antes
    se indexaba directamente ["content"], y un mensaje sin esa clave lanzaba
    un KeyError sin control que rompía el ciclo del bot de fondo."""
    contenido = mensaje.get("content")
    if contenido:
        return contenido
    contenido = mensaje.get("reasoning_content")
    if contenido:
        return contenido
    raise RuntimeError(f"Respuesta sin 'content' ni 'reasoning_content': {mensaje}")


def llamar_nvidia_nim_directo(api_key: str, model: str, prompt: str) -> str:
    """Realiza la solicitud HTTP nativa a NVIDIA NIM sin requerir el módulo SDK de OpenAI."""
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=45) as response:
        res_data = json.loads(response.read().decode("utf-8"))
        return _extraer_contenido(res_data["choices"][0]["message"])


def llamar_nvidia_nim_chat(api_key: str, model: str, messages: list,
                           temperature: float = 0.5, max_tokens: int = 2048,
                           timeout: int = 45) -> str:
    """Igual que llamar_nvidia_nim_directo, pero acepta la LISTA de mensajes
    completa (system + historial + user). La necesita el Alumno para mandar
    su personalidad, las lecciones y el contexto documental, no solo un prompt
    suelto. Mismo endpoint OpenAI-compatible de NVIDIA NIM."""
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        res_data = json.loads(response.read().decode("utf-8"))
        return _extraer_contenido(res_data["choices"][0]["message"])


def llamar_nvidia_vision_directo(api_key: str, model: str, pregunta: str, imagen_b64: str, mime_type: str = "image/jpeg") -> str:
    """Consulta un modelo de visión de NVIDIA NIM (gratis, mismo endpoint OpenAI-compatible
    que llamar_nvidia_nim_directo). La imagen viaja como data-URL en base64 dentro del
    campo 'image_url', que es el formato que exige la API de NIM para VLMs."""
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": pregunta},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{imagen_b64}"}}
                ]
            }
        ],
        "max_tokens": 1024,
        "temperature": 0.2,
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=40) as response:
        res_data = json.loads(response.read().decode("utf-8"))
        return _extraer_contenido(res_data["choices"][0]["message"])


def describir_imagen(ruta_imagen: str, pregunta: str = "") -> str:
    """Describe una imagen usando visión gratuita de NVIDIA NIM, con la misma rotación
    de claves y cadena de modelos de respaldo que usa el resto del sistema."""
    if not NVIDIA_KEYS_POOL:
        return "⚠️ No hay ninguna clave de NVIDIA configurada, así que Fénix no puede 'ver' imágenes todavía. Añade una en el panel de Configuración."

    pregunta_final = pregunta.strip() or (
        "Describe esta imagen con todo el detalle posible: elementos, colores, "
        "composición, ambiente y cualquier texto visible."
    )

    mime_type = "image/png" if ruta_imagen.lower().endswith(".png") else "image/jpeg"

    try:
        with open(ruta_imagen, "rb") as f:
            imagen_b64 = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        return f"⚠️ No se pudo leer la imagen: {e}"

    for modelo_actual in MODELOS_VISION_NVIDIA:
        for _ in range(len(NVIDIA_KEYS_POOL)):
            try:
                return llamar_nvidia_vision_directo(
                    api_key=NVIDIA_KEYS_POOL[0],
                    model=modelo_actual,
                    pregunta=pregunta_final,
                    imagen_b64=imagen_b64,
                    mime_type=mime_type,
                )
            except Exception as e:
                print(f"Error en Visión NVIDIA ({modelo_actual}): {e}. Rotando clave.")
                rotar_clave_nvidia_fallida()
        print(f"⚠️ Modelo de visión {modelo_actual} agotó todas las claves. Probando siguiente.")

    return "⚠️ Todos los modelos de visión de NVIDIA fallaron o agotaron su cuota gratuita. Intenta de nuevo en unos minutos."


def generar_imagen_ia(prompt: str, guardar_en_supabase: bool = True, ancho: int = 1024, alto: int = 1024):
    """Genera una imagen con la API de Inference de Hugging Face (modelo FLUX.1-schnell,
    Apache 2.0, con franja gratuita mensual real vía HF_TOKEN). Se usa HF porque Cristóbal
    ya opera en ese ecosistema (Spaces) y reutiliza el mismo token, sin darse de alta en
    un proveedor nuevo. Guarda la imagen localmente y opcionalmente la sube a Supabase
    Storage + registra el prompt en 'fenix_imagenes_generadas' para historial consultable.
    Devuelve (ruta_local, url_publica_o_None, mensaje_estado)."""
    if not prompt or not prompt.strip():
        return None, None, "⚠️ Escribe una descripción para la imagen."

    hf_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    if not hf_token:
        return None, None, "⚠️ Falta configurar HF_TOKEN (tu token de Hugging Face) como secreto del Space para poder generar imágenes."

    prompt_limpio = prompt.strip()

    try:
        from huggingface_hub import InferenceClient
        cliente = InferenceClient(token=hf_token)
        imagen_pil = cliente.text_to_image(
            prompt_limpio,
            model="black-forest-labs/FLUX.1-schnell",
            width=ancho,
            height=alto,
        )
    except Exception as e:
        return None, None, f"⚠️ Error generando la imagen con Hugging Face: {e}"

    semilla = int.from_bytes(os.urandom(4), "big")
    nombre_archivo = f"fenix_img_{int(time.time())}_{semilla}.jpg"
    ruta_local = os.path.join(tempfile.gettempdir(), nombre_archivo)
    imagen_pil.convert("RGB").save(ruta_local, "JPEG", quality=92)

    with open(ruta_local, "rb") as f:
        imagen_bytes = f.read()

    url_publica = None
    estado = "✅ Imagen creada."

    if guardar_en_supabase and sb:
        try:
            sb.storage.from_("fenix-imagenes").upload(
                nombre_archivo,
                imagen_bytes,
                {"content-type": "image/jpeg"},
            )
            url_publica = sb.storage.from_("fenix-imagenes").get_public_url(nombre_archivo)
            sb.table("fenix_imagenes_generadas").insert({
                "prompt": prompt_limpio,
                "nombre_archivo": nombre_archivo,
                "url_publica": url_publica,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
            estado = "✅ Imagen creada y guardada en tu galería de Supabase."
        except Exception as e:
            print(f"Aviso: no se pudo guardar en Supabase Storage/tabla: {e}")
            estado = "✅ Imagen creada (no se pudo subir a Supabase, revisa que exista el bucket 'fenix-imagenes')."

    return ruta_local, url_publica, estado


def cargar_galeria_imagenes(limite: int = 30):
    """Carga el historial de imágenes generadas desde Supabase para mostrarlas en una galería."""
    if not sb:
        return []
    try:
        res = (
            sb.table("fenix_imagenes_generadas")
            .select("url_publica, prompt, created_at")
            .order("created_at", desc=True)
            .limit(limite)
            .execute()
        )
        return [(fila["url_publica"], fila["prompt"]) for fila in (res.data or []) if fila.get("url_publica")]
    except Exception as e:
        print(f"Error cargando galería de imágenes: {e}")
        return []


def llamar_cerebras_directo(api_key: str, model: str, messages: list, temperature: float = 0.5,
                             max_tokens: int = None, timeout: int = 300, reasoning_effort: str = None) -> str:
    """Realiza la solicitud HTTP nativa a Cerebras (endpoint compatible con OpenAI),
    sin requerir el SDK cerebras-cloud-sdk. Acepta una lista de mensajes completa
    (system/user/assistant) para poder mandar historial y contexto completos.
    reasoning_effort ("low"/"medium"/"high") es un parámetro estándar de OpenAI
    que Cerebras soporta de forma nativa para gpt-oss-120b: baja el "pensamiento"
    interno del modelo para dejar más presupuesto de tokens a la respuesta final
    y evitar que se corte a medias."""
    url = "https://api.cerebras.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        # FIX ERROR 1010 (Cloudflare): el User-Agent por defecto de urllib
        # ("Python-urllib/3.x") lo bloquea el WAF de Cloudflare por firma de
        # bot. curl pasaba sin problema, así que imitamos un cliente normal.
        "User-Agent": "curl/8.4.0",
        "Accept": "*/*",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return _extraer_contenido(res_data["choices"][0]["message"])
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Cerebras HTTP {e.code}: {detalle}") from None


def cargar_lecciones_relevantes(pregunta: str = "", limite: int = 8):
    """Recupera de Supabase las lecciones que mas se parecen a la pregunta actual.

    FIX APRENDIZAJE (doble):
    1) Antes solo se reinyectaban lecciones con veredicto 'bien'. Las correcciones
       del maestro cuando Fénix FALLA (veredicto 'mal') son precisamente las
       lecciones valiosas, y se estaban tirando. Ahora se usan todas: el campo
       'correccion_maestro' siempre contiene la version final aprobada.
    2) Antes 'relevantes' era mentira: traia las 8 mas recientes sin mirar la
       pregunta. Ahora trae un lote amplio y elige por coincidencia de palabras
       clave con la pregunta actual (con las recientes como desempate).
    """
    if not sb:
        return []
    try:
        res = (
            sb.table("fenix_lecciones")
            .select("pregunta, correccion_maestro, veredicto, created_at")
            .order("created_at", desc=True)
            .limit(120)
            .execute()
        )
        candidatas = res.data or []
        if not candidatas:
            return []

        # Deduplicar por pregunta (el bug de re-revision generaba duplicadas)
        vistas = set()
        unicas = []
        for l in candidatas:
            clave = (l.get("pregunta") or "").strip().lower()[:120]
            if clave and clave not in vistas:
                vistas.add(clave)
                unicas.append(l)

        palabras = set(_palabras_clave(pregunta, max_palabras=8))
        if palabras:
            def puntuar(l):
                texto = ((l.get("pregunta") or "") + " " + (l.get("correccion_maestro") or "")).lower()
                texto_sin = texto.translate(_ACENTOS)
                return sum(1 for p in palabras if p in texto or p in texto_sin)

            unicas.sort(key=puntuar, reverse=True)
            relevantes = [l for l in unicas[:limite] if puntuar(l) > 0]
            if relevantes:
                return relevantes

        # Sin pregunta o sin coincidencias: las mas recientes como antes
        return unicas[:limite]
    except Exception as e:
        print("Error cargando lecciones místicas:", e)
        return []


def formatear_contexto_docs(docs) -> str:
    if not docs:
        return ""
    # FIX: se incluye el nombre del libro y el numero de fragmento para que
    # Fénix pueda citar la obra por su nombre ("segun tu libro TESHUÁ...").
    bloque = "Fragmentos relevantes de tus libros espirituales indexados (prioriza esta información):\n"
    for d in docs:
        nombre = d.get("nombre_archivo") or "libro"
        idx = d.get("chunk_index", "?")
        bloque += f"- [{nombre} · fragmento {idx}] {(d.get('contenido') or '')[:1100]}\n"
    return bloque


def construir_system_prompt(contexto_docs: str = "", pregunta: str = "", nombre_jardin: str = ""):
    prompt = PERSONALIDAD_BASE

    lecciones = cargar_lecciones_relevantes(pregunta)
    if lecciones:
        extra = "\n\nLecciones sagradas aprendidas de tu maestro (aplícalas):\n"
        for l in lecciones:
            preg = (l.get("pregunta") or "")[:80]
            correccion = (l.get("correccion_maestro") or "")[:150]
            extra += f"- Ante algo como \"{preg}\" -> responde en la línea de: {correccion}\n"
        prompt += extra

    if contexto_docs:
        prompt += "\n\n" + contexto_docs

    if nombre_jardin:
        prompt += contexto_progreso_y_gratitudes(nombre_jardin)

    return prompt


def preguntar_fenix(pregunta: str, historial=None, contexto_docs: str = "", nombre_jardin: str = "", clave_usuario: str = None):
    historial = historial or []
    mensajes = [{"role": "system", "content": construir_system_prompt(contexto_docs, pregunta, nombre_jardin)}]
    mensajes += historial
    mensajes.append({"role": "user", "content": pregunta})

    # --- 1) PRIMERO NVIDIA: modelo pequeño, rápido y fiable ---
    # Recorre la cadena MODELOS_ALUMNO_NVIDIA y, para cada modelo, prueba todas
    # las claves del pool rotándolas ante cualquier error. Solo si NVIDIA entero
    # falla se baja al respaldo de Cerebras de más abajo.
    if NVIDIA_KEYS_POOL:
        for modelo_actual in MODELOS_ALUMNO_NVIDIA:
            for _ in range(len(NVIDIA_KEYS_POOL)):
                try:
                    return llamar_nvidia_nim_chat(
                        api_key=NVIDIA_KEYS_POOL[0],
                        model=modelo_actual,
                        messages=mensajes,
                        temperature=0.5,
                        max_tokens=2048,
                    )
                except Exception as e:
                    print(f"Error en Alumno NVIDIA ({modelo_actual}): {e}. Rotando clave.")
                    rotar_clave_nvidia_fallida()
            print(f"⚠️ Alumno: el modelo NVIDIA {modelo_actual} agotó sus claves. Probando siguiente.")
        print("⚠️ Alumno: NVIDIA no respondió con ningún modelo. Cayendo al respaldo de Cerebras.")

    # --- 2) RESPALDO Cerebras (la lógica de siempre) ---
    # Si la persona guardó su propia clave de Cerebras en el móvil, se
    # intenta primero con esa (así no consume el pool compartido); si
    # falla, cae al pool normal exactamente igual que siempre.
    claves_a_probar = CEREBRAS_KEYS_POOL
    if clave_usuario:
        claves_a_probar = [clave_usuario] + CEREBRAS_KEYS_POOL

    if not claves_a_probar:
        raise RuntimeError("⚠️ No hay NVIDIA disponible ni ninguna clave de Cerebras de respaldo configurada.")

    for _ in range(max(len(claves_a_probar), 2)):
        try:
            return llamar_cerebras_directo(
                api_key=claves_a_probar[0],
                model=MODELO_FENIX,
                messages=mensajes,
                temperature=0.5,
                max_tokens=4096,
                reasoning_effort="low"
            )
        except Exception as e:
            print(f"Error en Alumno Cerebras (respaldo): {e}. Reintentando con clave rotada.")
            if "429" in str(e) or "token_quota_exceeded" in str(e):
                time.sleep(15)
            if claves_a_probar is CEREBRAS_KEYS_POOL:
                rotar_clave_cerebras_fallida()
            else:
                claves_a_probar = CEREBRAS_KEYS_POOL

    raise RuntimeError("Todas las API keys de NVIDIA y de Cerebras de respaldo del Alumno han fallado.")


def _limpiar_correccion(texto: str) -> str:
    if not texto:
        return texto
    texto = texto.strip()
    if re.match(r"^pregunta\s*:", texto, re.IGNORECASE):
        partes = re.split(r"respuesta(?:\s+de\s+f[ée]nix)?\s*:\s*", texto, maxsplit=1, flags=re.IGNORECASE)
        if len(partes) == 2:
            return partes[1].strip()
    return texto


def preguntar_maestro(pregunta: str, respuesta_fenix: str, contexto_docs: str = ""):
    bloque_contexto = contexto_docs or "(No se encontraron pasajes específicos en los libros; evalúa con tu criterio espiritual general.)"

    prompt_maestro = f"""Eres un revisor que evalúa si una respuesta se ajusta fielmente al contenido de la base de datos.

Pregunta original:
\"\"\"{pregunta}\"\"\"

Respuesta a evaluar:
\"\"\"{respuesta_fenix}\"\"\"

Pasajes oficiales cargados en Supabase (única fuente permitida):
{bloque_contexto}

Evalúa la respuesta en base a:
1. FIDELIDAD A LA FUENTE: ¿Se apoya solo en los pasajes de arriba, sin inventar ni añadir contenido que no esté ahí?
2. CLARIDAD: ¿Responde de forma directa y comprensible a la pregunta, usando ese contenido?

Si la respuesta se aparta de los pasajes o inventa información, el veredicto es "mal" y en 'correccion' escribes tú la versión que sí se ciñe al contenido de la base de datos.

Responde ÚNICAMENTE con un JSON plano válido (sin backticks de markdown fuera del objeto ni comentarios):
{{"veredicto": "bien" o "mal", "correccion": "escribe aquí la respuesta final completa como guía", "categoria": "tema espiritual"}}

Reglas:
- En 'correccion' escribe directamente la guía espiritual en primera persona para el buscador, lista para reproducir.
- No uses etiquetas como "Fénix:" ni menciones que eres el maestro evaluando.
- El campo 'correccion' se lee en voz alta con un sintetizador de voz, así que escríbelo en prosa fluida y
  hablada, SIN formato Markdown de ningún tipo: nada de encabezados (#, ##), nada de negritas o cursivas con
  asteriscos/guiones bajos, nada de líneas separadoras (---), nada de listas con guiones o numeración. Si hay
  varios pasos o ideas, enlázalos con palabras dentro del propio texto, nunca con símbolos de lista."""

    usando_nvidia = len(NVIDIA_KEYS_POOL) > 0
    texto = ""

    if usando_nvidia:
        exito_nvidia = False
        for modelo_actual in MODELOS_MAESTRO_NVIDIA:
            for _ in range(len(NVIDIA_KEYS_POOL)):
                try:
                    # Consulta limpia e instantánea usando HTTP directo sin dependencias
                    texto = llamar_nvidia_nim_directo(
                        api_key=NVIDIA_KEYS_POOL[0],
                        model=modelo_actual,
                        prompt=prompt_maestro
                    )
                    exito_nvidia = True
                    break
                except Exception as e:
                    print(f"Error en Maestro NVIDIA ({modelo_actual}): {e}. Rotando clave.")
                    rotar_clave_nvidia_fallida()
            if exito_nvidia:
                break
            print(f"⚠️ Modelo {modelo_actual} agotó todas las claves. Probando siguiente modelo de la cadena.")

        if not exito_nvidia:
            print("⚠️ Los 3 modelos de NVIDIA fallaron. Delegando evaluación al respaldo de Cerebras.")
            usando_nvidia = False

    if not usando_nvidia:
        for _ in range(max(len(CEREBRAS_KEYS_POOL), 2)):
            try:
                texto = llamar_cerebras_directo(
                    api_key=CEREBRAS_KEYS_POOL[0],
                    model=MODELO_MAESTRO_CEREBRAS,
                    messages=[{"role": "user", "content": prompt_maestro}],
                    temperature=0.1,
                    max_tokens=4096,
                    reasoning_effort="low"
                ).strip()
                break
            except Exception as e:
                print(f"Error en Maestro Cerebras (respaldo): {e}. Rotando clave.")
                if "429" in str(e) or "token_quota_exceeded" in str(e):
                    time.sleep(15)
                rotar_clave_cerebras_fallida()
        else:
            raise RuntimeError("Todas las API keys de NVIDIA (3 modelos) y Cerebras de respaldo para el Maestro han fallado.")

    texto = texto.replace("```json", "").replace("```", "").strip()
    try:
        datos = json.loads(texto)
        datos["correccion"] = _limpiar_correccion(datos.get("correccion", respuesta_fenix))
        return datos
    except Exception:
        return {"veredicto": "mal", "correccion": respuesta_fenix, "categoria": "misticismo"}


def guardar_leccion(pregunta, respuesta_fenix, evaluacion):
    if not sb:
        return
    try:
        sb.table("fenix_lecciones").insert(
            {
                "pregunta": pregunta,
                "respuesta_fenix": respuesta_fenix,
                "correccion_maestro": evaluacion.get("correccion", ""),
                "veredicto": evaluacion.get("veredicto", "mal"),
                "categoria": evaluacion.get("categoria", ""),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ).execute()
    except Exception as e:
        print("Error guardando lección mística:", e)


def _bloque_pdf_adjunto(ruta_pdf: str, pregunta: str, max_frag: int = 6) -> str:
    """Lee un PDF adjuntado EN EL CHAT y devuelve un bloque de contexto con sus
    fragmentos más relacionados con la pregunta, listo para inyectar en el
    system prompt del Alumno (y que también vea el Maestro). Devuelve "" si no
    hay PDF o no se pudo leer, para que el chat siga funcionando igual sin
    adjunto. No guarda nada en la biblioteca: es solo para esta conversación."""
    if not ruta_pdf:
        return ""
    try:
        texto = extraer_texto_pdf(ruta_pdf)
    except Exception as e:
        print(f"Aviso: no se pudo leer el PDF adjunto del chat: {e}")
        return ""
    if not texto.strip():
        return ("El buscador adjuntó un PDF pero no tiene texto legible "
                "(suele ser un PDF escaneado, que es una imagen). Pídele con "
                "delicadeza que lo pase por un OCR o suba una versión en texto.")

    chunks = trocear_texto(texto, tam_chunk=1400)
    palabras = set(_palabras_clave(pregunta, max_palabras=10))

    def _p(frag: str) -> int:
        t = (frag or "").lower()
        ts = t.translate(_ACENTOS)
        return sum(1 for p in palabras if p in t or p in ts)

    if palabras:
        ordenados = sorted(chunks, key=_p, reverse=True)
        relevantes = [c for c in ordenados if _p(c) > 0][:max_frag]
    else:
        relevantes = []
    if not relevantes:
        relevantes = chunks[:max_frag]

    bloque = ("El buscador ha adjuntado un PDF a esta conversación. Apóyate en su "
              "contenido para responder lo que te pregunta:\n")
    for i, c in enumerate(relevantes):
        bloque += f"\n[PDF adjunto · fragmento {i}]\n{c[:1200]}\n"
    return bloque


def ciclo_completo(pregunta, historial=None, nombre_jardin: str = "", clave_usuario: str = None,
                   ruta_pdf_adjunto: str = None):
    docs = cargar_contexto_pdf(pregunta)
    contexto_docs = formatear_contexto_docs(docs)

    # Si la persona adjuntó un PDF en el chat, sus fragmentos se suman al
    # contexto (van delante, con prioridad) para que el Alumno lo analice y
    # el Maestro lo tenga en cuenta al evaluar.
    bloque_adjunto = _bloque_pdf_adjunto(ruta_pdf_adjunto, pregunta)
    if bloque_adjunto:
        contexto_docs = (bloque_adjunto + "\n\n" + contexto_docs) if contexto_docs else bloque_adjunto

    respuesta = preguntar_fenix(pregunta, historial, contexto_docs, nombre_jardin, clave_usuario)
    evaluacion = preguntar_maestro(pregunta, respuesta, contexto_docs)
    guardar_leccion(pregunta, respuesta, evaluacion)
    respuesta_final = respuesta if evaluacion["veredicto"] == "bien" else evaluacion["correccion"]

    if nombre_jardin:
        leccion_mencionada = _detectar_leccion_mencionada(respuesta_final)
        if leccion_mencionada is not None:
            actualizar_progreso(nombre_jardin, leccion_mencionada)

    return respuesta_final, evaluacion


def extraer_texto_pdf(ruta_pdf: str) -> str:
    """Extrae texto de un PDF de forma robusta. Si una página falla (PDF raro,
    mal codificado), la salta en vez de reventar la ingesta entera."""
    lector = pypdf.PdfReader(ruta_pdf)
    partes = []
    for num, pagina in enumerate(lector.pages):
        try:
            partes.append(pagina.extract_text() or "")
        except Exception as e:
            print(f"⚠️ Página {num} ilegible, se salta: {e}")
    return "\n".join(partes)


def trocear_texto(texto: str, tam_chunk: int = 1200):
    """Trocea el texto SIN partir palabras a la mitad: corta por el último
    espacio antes del límite, para que cada fragmento sea legible completo."""
    texto = texto.strip()
    if not texto:
        return []
    chunks = []
    i = 0
    n = len(texto)
    while i < n:
        fin = min(i + tam_chunk, n)
        if fin < n:
            # retrocede hasta el último espacio para no cortar una palabra
            corte = texto.rfind(" ", i, fin)
            if corte > i:
                fin = corte
        chunk = texto[i:fin].strip()
        if chunk:
            chunks.append(chunk)
        i = fin
    return chunks


def guardar_documento(nombre_archivo: str, chunks: list) -> int:
    """Guarda los fragmentos en lotes (no uno a uno): mucho más rápido y
    fiable para libros grandes. Inserta de 100 en 100; si un lote falla,
    reintenta ese lote fragmento a fragmento para no perder el libro entero."""
    if not sb:
        return 0
    guardados = 0
    ahora = datetime.now(timezone.utc).isoformat()
    filas = [
        {
            "nombre_archivo": nombre_archivo,
            "chunk_index": idx,
            "contenido": chunk,
            "created_at": ahora,
        }
        for idx, chunk in enumerate(chunks)
    ]
    LOTE = 100
    for inicio in range(0, len(filas), LOTE):
        lote = filas[inicio:inicio + LOTE]
        try:
            sb.table("fenix_documentos").insert(lote).execute()
            guardados += len(lote)
        except Exception as e:
            print(f"Lote {inicio}-{inicio+len(lote)} falló ({e}); reintentando uno a uno.")
            for fila in lote:
                try:
                    sb.table("fenix_documentos").insert(fila).execute()
                    guardados += 1
                except Exception as e2:
                    print(f"  Fragmento {fila['chunk_index']} perdido: {e2}")
    return guardados


def documento_ya_existe(nombre_archivo: str) -> bool:
    """Comprueba si un libro con ese nombre ya está cargado, para no
    duplicarlo si lo subes dos veces sin querer."""
    if not sb:
        return False
    try:
        r = (sb.table("fenix_documentos")
               .select("id")
               .eq("nombre_archivo", nombre_archivo)
               .limit(1)
               .execute())
        return bool(r.data)
    except Exception:
        return False


def guardar_conversacion(mensaje_usuario: str, respuesta_fenix: str, revisado: bool = True):
    """FIX RE-REVISION: cada turno en vivo ya pasa por el maestro dentro de
    ciclo_completo, asi que se guarda con revisado=True. Antes quedaba en False
    y el boton 'Revisar historial' volvia a evaluar lo ya evaluado, generando
    lecciones duplicadas en cada pulsacion."""
    if not sb:
        return
    fila = {
        "mensaje_usuario": mensaje_usuario,
        "respuesta_fenix": respuesta_fenix,
        "revisado": revisado,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        sb.table("fenix_conversaciones").insert(fila).execute()
    except Exception as e:
        # Red de seguridad: si la columna 'revisado' aun no existe en la tabla
        # (falta ejecutar el SQL de migracion), guardamos sin ella para no
        # perder jamas una conversacion.
        print("Aviso guardando conversación (reintento sin 'revisado'):", e)
        try:
            fila.pop("revisado", None)
            sb.table("fenix_conversaciones").insert(fila).execute()
        except Exception as e2:
            print("Error guardando conversación mística:", e2)


# Prefijo con el que el bot autónomo (preparación del oráculo) guarda sus
# inquietudes en la MISMA tabla fenix_conversaciones (ver bucle_inquietudes_
# espirituales en app.py). Nos sirve para reconocer y, cuando haga falta,
# ocultar esas filas sin necesidad de tocar la base de datos.
MARCA_BOT_RIO = "[Bot Autónomo"


def cargar_conversaciones(limite: int = 40, incluir_bot: bool = True):
    """Devuelve el historial como lista de mensajes {role, content}.

    incluir_bot=True  -> río completo, con las inquietudes del bot autónomo
                         (así lo usa la web del Space / el Oráculo, donde el
                         bot SÍ debe verse como 'preparación del oráculo').
    incluir_bot=False -> SOLO conversaciones de personas, sin el bot. Es lo
                         que pide la app móvil para el Río de Conversación:
                         un cauce limpio de humanos, sin el bot de fondo.
    """
    if not sb:
        return []
    try:
        res = (
            sb.table("fenix_conversaciones")
            .select("mensaje_usuario, respuesta_fenix, created_at")
            .order("created_at", desc=True)
            .limit(limite)
            .execute()
        )
        filas = list(reversed(res.data or []))
        mensajes = []
        for fila in filas:
            mensaje_usuario = fila["mensaje_usuario"]
            if (
                not incluir_bot
                and isinstance(mensaje_usuario, str)
                and mensaje_usuario.lstrip().startswith(MARCA_BOT_RIO)
            ):
                continue  # fila del bot autónomo: fuera del Río móvil
            mensajes.append({"role": "user", "content": mensaje_usuario})
            mensajes.append({"role": "assistant", "content": fila["respuesta_fenix"]})
        return mensajes
    except Exception as e:
        print("Error cargando conversaciones:", e)
        return []


def _extraer_respuesta_limpia(texto_guardado: str) -> str:
    return (texto_guardado or "").split("\n\n_(maestro:")[0].strip()


def revisar_conversaciones_pendientes(limite: int = 20) -> str:
    if not sb:
        return "Supabase no está configurado."
    try:
        res = (
            sb.table("fenix_conversaciones")
            .select("id, mensaje_usuario, respuesta_fenix")
            .eq("revisado", False)
            .order("created_at", desc=False)
            .limit(limite)
            .execute()
        )
        pendientes = res.data or []
    except Exception as e:
        return f"Error trayendo pendientes: {e}"

    if not pendientes:
        return "✅ Todas las conversaciones espirituales están revisadas por el maestro."

    nuevas_lecciones = 0
    for fila in pendientes:
        pregunta = fila["mensaje_usuario"]
        respuesta_limpia = _extraer_respuesta_limpia(fila["respuesta_fenix"])
        try:
            docs = cargar_contexto_pdf(pregunta)
            contexto_docs = formatear_contexto_docs(docs)
            evaluacion = preguntar_maestro(pregunta, respuesta_limpia, contexto_docs)
            guardar_leccion(pregunta, respuesta_limpia, evaluacion)
            if evaluacion.get("veredicto") == "bien":
                nuevas_lecciones += 1
            sb.table("fenix_conversaciones").update({"revisado": True}).eq("id", fila["id"]).execute()
        except Exception as e:
            print(f"Error revisando conversación {fila.get('id')}: {e}")

    return f"🎓 Revisadas {len(pendientes)} conversaciones. {nuevas_lecciones} nuevas lecciones místicas aprendidas."


def listar_libros() -> list:
    """Devuelve la lista de libros cargados en la biblioteca (nombre y nº de
    fragmentos de cada uno), para poder elegir cuál borrar."""
    if not sb:
        return []
    try:
        # FIX BIBLIOTECA: Supabase/PostgREST devuelve como MAXIMO 1000 filas por
        # peticion. Sin paginar, la biblioteca se quedaba clavada en "1000
        # fragmentos" aunque hubiera muchos mas guardados, y los libros nuevos
        # (a partir de la fila 1000) ni siquiera aparecian. Ahora leemos TODA la
        # tabla por bloques de 1000 hasta que se acaba. La Tanaj entera cabe.
        conteo = {}
        inicio = 0
        TAM = 1000
        while True:
            r = (sb.table("fenix_documentos")
                   .select("nombre_archivo")
                   .range(inicio, inicio + TAM - 1)
                   .execute())
            filas = r.data or []
            for fila in filas:
                nombre = fila.get("nombre_archivo", "?")
                conteo[nombre] = conteo.get(nombre, 0) + 1
            if len(filas) < TAM:
                break
            inicio += TAM
        return sorted(conteo.items())
    except Exception as e:
        print(f"Error listando libros: {e}")
        return []


def texto_biblioteca() -> str:
    """Resumen legible de la biblioteca para mostrar en la interfaz."""
    libros = listar_libros()
    if not libros:
        return "📚 La biblioteca está vacía."
    total = sum(n for _, n in libros)
    lineas = [f"📚 {len(libros)} libros · {total} fragmentos en total:\n"]
    for nombre, n in libros:
        lineas.append(f"• {nombre} — {n} fragmentos")
    return "\n".join(lineas)


def borrar_libro(nombre_archivo: str) -> str:
    """Borra de la biblioteca TODOS los fragmentos de un libro concreto.
    Reversible solo volviendo a subir el PDF."""
    if not sb:
        return "⚠️ Supabase no está configurado."
    if not nombre_archivo:
        return "Elige un libro de la lista antes de borrar."
    try:
        (sb.table("fenix_documentos")
           .delete()
           .eq("nombre_archivo", nombre_archivo)
           .execute())
        return f"🗑️ '{nombre_archivo}' eliminado de la biblioteca de Fénix."
    except Exception as e:
        return f"⚠️ No se pudo borrar '{nombre_archivo}': {e}"


def procesar_pdf(ruta_pdf: str, nombre_archivo: str = None) -> str:
    nombre_archivo = nombre_archivo or os.path.basename(ruta_pdf)
    if not sb:
        return "⚠️ Supabase no está configurado."
    if documento_ya_existe(nombre_archivo):
        return f"📚 '{nombre_archivo}' ya estaba cargado. No se ha duplicado (si quieres recargarlo, bórralo antes de la biblioteca)."
    texto = extraer_texto_pdf(ruta_pdf)
    if not texto.strip():
        return (f"No se pudo extraer texto de '{nombre_archivo}'. "
                "Suele pasar con PDFs escaneados (son imágenes, no texto). "
                "Pásalo antes por un OCR o busca una versión en texto.")
    chunks = trocear_texto(texto)
    guardados = guardar_documento(nombre_archivo, chunks)
    if guardados == 0:
        return f"⚠️ No se pudo inyectar ninguna sección de '{nombre_archivo}'."
    aviso = "" if guardados == len(chunks) else f" ({len(chunks) - guardados} fragmentos se perdieron, revisa el log)"
    return f"📄 '{nombre_archivo}' procesado: {guardados}/{len(chunks)} fragmentos espirituales guardados en la base de datos.{aviso}"


def cargar_contexto_pdf(pregunta: str, limite: int = 10):
    """Recupera fragmentos relevantes buscando EN TODA la biblioteca.

    FIX BUSQUEDA (el bug principal): la version anterior traia solo los 80
    chunks mas recientes de la tabla entera (order created_at + limit 80) y
    puntuaba palabras sobre esos 80. Con TESHUÁ y el resto de libros dentro,
    el 95% de la biblioteca era invisible: por eso Fénix no encontraba tu
    propio libro. Ahora la busqueda por palabras clave se hace EN EL SERVIDOR
    con ilike sobre toda la tabla, y solo se puntúa/ordena el resultado.
    """
    if not sb or not pregunta:
        return []
    palabras = _palabras_clave(pregunta, max_palabras=8)
    try:
        candidatos = []
        if palabras:
            filtros = ",".join(f"contenido.ilike.%{p}%" for p in palabras)
            # MAS INFORMACION: se amplia el lote de candidatos de 60 a 300 para
            # que la puntuacion por palabras clave tenga de donde elegir en una
            # biblioteca grande (Tanaj entera). Solo los 'limite' mejores acaban
            # en el prompt, asi que esto mejora la punteria sin inflar el mensaje.
            res = (
                sb.table("fenix_documentos")
                .select("nombre_archivo, chunk_index, contenido")
                .or_(filtros)
                .limit(300)
                .execute()
            )
            candidatos = res.data or []

        if not candidatos:
            # Fallback: sin palabras utiles o sin coincidencias, se degrada al
            # comportamiento antiguo (chunks recientes) para no dejar a Fénix
            # completamente a ciegas.
            res = (
                sb.table("fenix_documentos")
                .select("nombre_archivo, chunk_index, contenido")
                .order("created_at", desc=True)
                .limit(50)
                .execute()
            )
            candidatos = res.data or []
            if not candidatos:
                return []

        objetivo = set(palabras)

        def puntuar(chunk):
            texto = (chunk.get("contenido") or "").lower()
            texto_sin = texto.translate(_ACENTOS)
            return sum(1 for p in objetivo if p in texto or p in texto_sin)

        candidatos.sort(key=puntuar, reverse=True)
        mejores = [c for c in candidatos[:limite] if puntuar(c) > 0]
        return mejores if mejores else candidatos[:limite]
    except Exception as e:
        print("Error cargando contexto documental:", e)
        return []


def consultar_pdf(ruta_pdf: str, pregunta: str) -> str:
    """Examina un PDF recién subido y responde A FONDO, cruzándolo con el
    conocimiento indexado en la base de datos (Supabase).

    CLAVE: aquí NO se usa la personalidad de oráculo de Fénix (que pide
    respuestas cortas, habladas y sin estructura); esa persona hacía que el
    análisis saliera pobre y breve. En su lugar se usa un prompt propio de
    'analista' que pide una respuesta completa y bien explicada, más contexto
    del documento y un presupuesto de tokens mayor. No guarda el PDF en la
    biblioteca (para eso está procesar_pdf / 'Memoria Documental')."""
    if not ruta_pdf:
        return "Sube un PDF y escribe tu pregunta para que Fénix lo examine."
    if not (pregunta or "").strip():
        return "Escribe qué quieres saber sobre el documento."

    try:
        texto = extraer_texto_pdf(ruta_pdf)
    except Exception as e:
        return f"⚠️ No se pudo leer el PDF: {e}"

    if not texto.strip():
        return ("No se pudo extraer texto de este PDF. Suele pasar con PDFs "
                "escaneados (son imágenes, no texto). Pásalo antes por un OCR "
                "o busca una versión en texto.")

    # Del PDF, los fragmentos más relacionados con la pregunta, pero ahora
    # MÁS y MÁS LARGOS, para que el modelo tenga material de sobra que analizar.
    chunks = trocear_texto(texto, tam_chunk=1400)
    palabras = set(_palabras_clave(pregunta, max_palabras=10))

    def _puntuar(fragmento: str) -> int:
        t = (fragmento or "").lower()
        ts = t.translate(_ACENTOS)
        return sum(1 for p in palabras if p in t or p in ts)

    if palabras:
        ordenados = sorted(chunks, key=_puntuar, reverse=True)
        relevantes = [c for c in ordenados if _puntuar(c) > 0][:8]
    else:
        relevantes = []
    if not relevantes:
        # Sin coincidencias claras: usamos el arranque del documento.
        relevantes = chunks[:8]

    bloque_pdf = "FRAGMENTOS DEL PDF A EXAMINAR:\n"
    for i, c in enumerate(relevantes):
        bloque_pdf += f"\n[Fragmento {i}]\n{c[:1300]}\n"

    # Además, el conocimiento que ya vive indexado en la base de datos.
    docs_bd = cargar_contexto_pdf(pregunta)
    bloque_bd = formatear_contexto_docs(docs_bd)

    contexto = bloque_pdf
    if bloque_bd:
        contexto += "\n\n" + bloque_bd

    system_prompt = (
        "Eres Fénix examinando un documento para la persona que te lo ha traído. "
        "Tu tarea NO es dar una sentencia mística breve, sino ANALIZAR el documento "
        "a fondo y responder su pregunta de forma completa, clara y bien explicada. "
        "Apóyate en los fragmentos del PDF (cítalos o parafraséalos cuando ayude) y, "
        "si viene al caso, relaciónalo con el conocimiento de tus libros indexados. "
        "Si el documento no contiene lo que se te pregunta, dilo con honestidad en vez "
        "de inventar. Extiéndete lo que haga falta para que la respuesta tenga sustancia; "
        "puedes usar varios párrafos y enumeraciones si aclaran."
    )
    mensajes = [
        {"role": "system", "content": system_prompt},
        {"role": "user",
         "content": f"{contexto}\n\nPREGUNTA: {pregunta}\n\nAnaliza el documento y responde a fondo."},
    ]

    # Para 'analizar bien' priorizamos modelos más capaces (con el timeout de
    # 45s y la rotación de claves ya no se cuelgan como antes) y damos un
    # presupuesto amplio de tokens. Cerebras (gpt-oss-120b, el más capaz que
    # tienes) queda de respaldo final.
    modelos_analisis = [
        "meta/llama-3.3-70b-instruct",
        "nvidia/llama-3.3-nemotron-super-49b-v1",
        "meta/llama-3.1-8b-instruct",
    ]
    if NVIDIA_KEYS_POOL:
        for modelo_actual in modelos_analisis:
            for _ in range(len(NVIDIA_KEYS_POOL)):
                try:
                    return llamar_nvidia_nim_chat(
                        api_key=NVIDIA_KEYS_POOL[0],
                        model=modelo_actual,
                        messages=mensajes,
                        temperature=0.4,
                        max_tokens=3500,
                    )
                except Exception as e:
                    print(f"Error examinando PDF NVIDIA ({modelo_actual}): {e}. Rotando clave.")
                    rotar_clave_nvidia_fallida()
            print(f"⚠️ Examinar PDF: el modelo NVIDIA {modelo_actual} agotó sus claves. Probando siguiente.")

    if CEREBRAS_KEYS_POOL:
        for _ in range(max(len(CEREBRAS_KEYS_POOL), 2)):
            try:
                return llamar_cerebras_directo(
                    api_key=CEREBRAS_KEYS_POOL[0],
                    model=MODELO_FENIX,
                    messages=mensajes,
                    temperature=0.4,
                    max_tokens=4096,
                    reasoning_effort="low",
                )
            except Exception as e:
                print(f"Error examinando PDF Cerebras (respaldo): {e}. Rotando clave.")
                if "429" in str(e) or "token_quota_exceeded" in str(e):
                    time.sleep(15)
                rotar_clave_cerebras_fallida()

    return ("⚠️ Fénix no pudo examinar el documento ahora mismo (todos los modelos "
            "fallaron o agotaron su cuota). Intenta de nuevo en un momento.")


def _quitar_markdown_para_voz(texto: str) -> str:
    """Quita cualquier símbolo de Markdown que se haya colado en la respuesta,
    para que edge-tts no lea literalmente asteriscos, almohadillas o guiones.
    Es una red de seguridad extra: el prompt ya pide no usar Markdown, pero
    si el modelo se despista, esto evita que la voz diga "asterisco" o
    "almohadilla" en vez de simplemente ignorar el símbolo."""
    if not texto:
        return texto
    # Encabezados: "### Texto" -> "Texto"
    texto = re.sub(r"^#{1,6}\s*", "", texto, flags=re.MULTILINE)
    # Líneas separadoras: "---" o "***" solas en una línea
    texto = re.sub(r"^\s*[-*_]{3,}\s*$", "", texto, flags=re.MULTILINE)
    # Negrita/cursiva: **texto**, *texto*, __texto__, _texto_
    texto = re.sub(r"\*\*([^*]+)\*\*", r"\1", texto)
    texto = re.sub(r"\*([^*]+)\*", r"\1", texto)
    texto = re.sub(r"__([^_]+)__", r"\1", texto)
    texto = re.sub(r"_([^_]+)_", r"\1", texto)
    # Viñetas de lista al inicio de línea: "- texto" o "1. texto"
    texto = re.sub(r"^\s*[-•]\s+", "", texto, flags=re.MULTILINE)
    texto = re.sub(r"^\s*\d+\.\s+", "", texto, flags=re.MULTILINE)
    # Colapsar líneas en blanco sobrantes que dejan los encabezados/separadores quitados
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def _aplicar_eco_voz(ruta_mp3: str, filtro: str) -> str:
    """Post-procesa el audio con la firma de eco/reverberación indicada en 'filtro'
    (cadena de filtro -af de ffmpeg, ya presente en el sistema para el pipeline de
    vídeo). Si algo falla (ffmpeg no disponible, etc.) devuelve el audio original."""
    ruta_eco = ruta_mp3.replace(".mp3", "_eco.mp3")
    try:
        comando = [
            "ffmpeg", "-y", "-i", ruta_mp3,
            "-af", filtro,
            "-ar", "44100",
            ruta_eco,
        ]
        resultado = subprocess.run(comando, capture_output=True, timeout=30)
        if resultado.returncode == 0 and os.path.exists(ruta_eco):
            return ruta_eco
        print("Aviso eco de voz: ffmpeg no devolvió éxito, se usa audio original.")
        return ruta_mp3
    except Exception as e:
        print(f"Aviso: no se pudo aplicar el eco a la voz ({e}), se usa audio original.")
        return ruta_mp3


TABLA_IDENTIDADES = "fenix_identidades"


def _normalizar_nombre(nombre: str) -> str:
    """Minúsculas y sin espacios sobrantes, para comparar nombres sin
    depender de mayúsculas o espacios extra que la persona haya tecleado."""
    return re.sub(r"\s+", " ", (nombre or "").strip()).lower()


def _hash_pin(pin: str) -> str:
    """El PIN nunca se guarda en texto plano, solo su hash SHA-256."""
    return hashlib.sha256((pin or "").encode("utf-8")).hexdigest()


def entrar_o_registrar_identidad(nombre: str, pin: str):
    """Identidad ligera del Jardín (Templo de Gratitud, Círculo de Historias,
    Río de Conversación): sin contraseña completa ni sesión compleja, solo
    nombre + PIN de 4 dígitos.

    - Si el nombre no existe en 'fenix_identidades', se crea con ese PIN
      (primer registro).
    - Si el nombre ya existe, se compara el PIN; si coincide, entra; si no,
      se rechaza (para que nadie más pueda "robar" un nombre ya usado).

    Devuelve un dict: {"ok": bool, "mensaje": str, "nombre_visible": str,
    "es_nuevo": bool}. El dispositivo debe guardar localmente el resultado
    si ok=True, para no volver a pedir el PIN en el día a día; el nombre y
    PIN solo se vuelven a usar si la persona cambia de celular.
    """
    nombre_visible = (nombre or "").strip()
    nombre_norm = _normalizar_nombre(nombre)
    pin_limpio = (pin or "").strip()

    if not nombre_norm:
        return {"ok": False, "mensaje": "Escribe tu nombre para entrar al Jardín.", "nombre_visible": "", "es_nuevo": False}
    if not re.fullmatch(r"\d{4}", pin_limpio):
        return {"ok": False, "mensaje": "El PIN debe ser de exactamente 4 números.", "nombre_visible": nombre_visible, "es_nuevo": False}
    if not sb:
        return {"ok": False, "mensaje": "⚠️ Supabase no está configurado en el Space.", "nombre_visible": nombre_visible, "es_nuevo": False}

    pin_hash = _hash_pin(pin_limpio)

    try:
        res = (
            sb.table(TABLA_IDENTIDADES)
            .select("nombre_visible, pin_hash")
            .eq("nombre_normalizado", nombre_norm)
            .limit(1)
            .execute()
        )
        filas = res.data or []

        if filas:
            existente = filas[0]
            if existente.get("pin_hash") != pin_hash:
                return {
                    "ok": False,
                    "mensaje": "Ese nombre ya está en uso con otro PIN. Si es tuyo, escribe el PIN con el que lo creaste; si no, elige otro nombre.",
                    "nombre_visible": nombre_visible,
                    "es_nuevo": False,
                }
            return {
                "ok": True,
                "mensaje": f"Bienvenido de vuelta, {existente.get('nombre_visible') or nombre_visible}.",
                "nombre_visible": existente.get("nombre_visible") or nombre_visible,
                "es_nuevo": False,
            }

        # No existía: se crea ahora mismo.
        sb.table(TABLA_IDENTIDADES).insert({
            "nombre_normalizado": nombre_norm,
            "nombre_visible": nombre_visible,
            "pin_hash": pin_hash,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        return {
            "ok": True,
            "mensaje": f"Bienvenido al Jardín, {nombre_visible}. Guarda bien tu PIN por si cambias de celular.",
            "nombre_visible": nombre_visible,
            "es_nuevo": True,
        }
    except Exception as e:
        print("Error en entrar_o_registrar_identidad:", e)
        return {"ok": False, "mensaje": "No se pudo conectar con el Jardín en este momento. Intenta de nuevo.", "nombre_visible": nombre_visible, "es_nuevo": False}


TABLA_GRATITUDES = "fenix_gratitudes"


TABLA_PROGRESO = "fenix_progreso_leccion"


def cargar_progreso(nombre: str):
    """Devuelve {'leccion_actual': int, 'nombre_visible': str} para 'nombre',
    o None si esa persona todavía no tiene fila de progreso (aún no ha
    dicho su nombre en el Jardín, o nunca ha hablado de lecciones)."""
    nombre_norm = _normalizar_nombre(nombre)
    if not nombre_norm or not sb:
        return None
    try:
        res = (
            sb.table(TABLA_PROGRESO)
            .select("leccion_actual, nombre_visible")
            .eq("nombre_normalizado", nombre_norm)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None
    except Exception as e:
        print("Error en cargar_progreso:", e)
        return None


def actualizar_progreso(nombre: str, leccion: int):
    """Crea o actualiza la lección actual de 'nombre'. Se usa solo cuando el
    propio Fénix, en su respuesta, deja claro que se avanzó de lección
    (ver _detectar_leccion_mencionada) — nunca se adivina desde Android."""
    nombre_visible = (nombre or "").strip()
    nombre_norm = _normalizar_nombre(nombre)
    if not nombre_norm or not sb:
        return
    try:
        sb.table(TABLA_PROGRESO).upsert(
            {
                "nombre_normalizado": nombre_norm,
                "nombre_visible": nombre_visible,
                "leccion_actual": leccion,
                "actualizado_en": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="nombre_normalizado",
        ).execute()
    except Exception as e:
        print("Error en actualizar_progreso:", e)


def _detectar_leccion_mencionada(texto: str):
    """Busca en la respuesta de Fénix una frase tipo 'lección 13' y devuelve
    ese número, o None si no encuentra ninguna. Deliberadamente simple: solo
    se dispara cuando Fénix mismo nombra el número, nunca por conteo de
    mensajes ni heurísticas frágiles del lado Android."""
    if not texto:
        return None
    m = re.search(r"lecci[oó]n\s+(\d{1,3})", texto, re.IGNORECASE)
    if not m:
        return None
    numero = int(m.group(1))
    return numero if 1 <= numero <= 100 else None


def contexto_progreso_y_gratitudes(nombre: str) -> str:
    """Arma el bloque de contexto discreto para inyectar en el system
    prompt: en qué lección va esta persona y sus gratitudes más recientes.
    Devuelve '' si no hay nombre o no hay nada guardado todavía (persona
    nueva, o hablando sin identidad de Jardín)."""
    if not nombre:
        return ""
    progreso = cargar_progreso(nombre)
    gratitudes = listar_gratitudes(nombre, limite=3)

    partes = []
    if progreso:
        partes.append(f"Va por la lección {progreso['leccion_actual']} de 100 del Camino de la Teshuá.")
    if gratitudes:
        textos = "; ".join(g.get("texto", "") for g in gratitudes if g.get("texto"))
        if textos:
            partes.append(f"Últimas gratitudes que dejó en el Templo: {textos}.")

    if not partes:
        return ""

    return (
        f"\n\nContexto privado sobre {nombre.strip()} (úsalo con naturalidad, "
        f"sin citarlo literalmente ni sonar a ficha de datos): " + " ".join(partes)
    )


TABLA_LUCES = "fenix_luces"


def encender_luz(nombre: str, intencion: str):
    """Altar de la Luz: 'enciende' una luz con una intención/plegaria para
    'nombre'. Mismo patrón que guardar_gratitud: exige identidad ya
    registrada en el Jardín, no crea luces huérfanas."""
    nombre_visible = (nombre or "").strip()
    nombre_norm = _normalizar_nombre(nombre)
    intencion_limpia = (intencion or "").strip()

    if not nombre_norm:
        return {"ok": False, "mensaje": "Falta tu nombre para encender la luz."}
    if not intencion_limpia:
        return {"ok": False, "mensaje": "Escribe una intención antes de encender la luz."}
    if not sb:
        return {"ok": False, "mensaje": "⚠️ Supabase no está configurado en el Space."}

    try:
        existe = (
            sb.table(TABLA_IDENTIDADES)
            .select("nombre_visible")
            .eq("nombre_normalizado", nombre_norm)
            .limit(1)
            .execute()
        )
        if not (existe.data or []):
            return {"ok": False, "mensaje": "No encontramos tu identidad en el Jardín. Entra primero desde la puerta principal."}

        sb.table(TABLA_LUCES).insert({
            "nombre_normalizado": nombre_norm,
            "nombre_visible": nombre_visible,
            "intencion": intencion_limpia,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        return {"ok": True, "mensaje": "🕯️ Tu luz quedó encendida en el Altar."}
    except Exception as e:
        print("Error en encender_luz:", e)
        return {"ok": False, "mensaje": "No se pudo encender la luz en este momento. Intenta de nuevo."}


def listar_luces(nombre: str, limite: int = 200):
    """Devuelve las luces encendidas de 'nombre', más recientes primero.
    Por ahora es solo la lista cruda (intención + fecha); la vista tipo
    'altar con velas encendidas' se construye después, en la capa visual."""
    nombre_norm = _normalizar_nombre(nombre)
    if not nombre_norm or not sb:
        return []
    try:
        res = (
            sb.table(TABLA_LUCES)
            .select("intencion, created_at")
            .eq("nombre_normalizado", nombre_norm)
            .order("created_at", desc=True)
            .limit(limite)
            .execute()
        )
        return res.data or []
    except Exception as e:
        print("Error en listar_luces:", e)
        return []


def guardar_gratitud(nombre: str, texto: str):
    """Templo de Gratitud: guarda una gratitud del día para 'nombre'.

    No vuelve a pedir el PIN aquí — la identidad ya se validó una vez en la
    puerta de entrada del Jardín (entrar_o_registrar_identidad) y el
    dispositivo recuerda el nombre localmente. Esta función solo exige que
    el nombre ya exista como identidad registrada, para no crear
    gratitudes "huérfanas" de alguien que nunca entró al Jardín.
    """
    nombre_visible = (nombre or "").strip()
    nombre_norm = _normalizar_nombre(nombre)
    texto_limpio = (texto or "").strip()

    if not nombre_norm:
        return {"ok": False, "mensaje": "Falta tu nombre para guardar la gratitud."}
    if not texto_limpio:
        return {"ok": False, "mensaje": "Escribe algo de gratitud antes de guardar."}
    if not sb:
        return {"ok": False, "mensaje": "⚠️ Supabase no está configurado en el Space."}

    try:
        # Confirma que la identidad exista (mismo patrón de normalización que fenix_identidades).
        existe = (
            sb.table(TABLA_IDENTIDADES)
            .select("nombre_visible")
            .eq("nombre_normalizado", nombre_norm)
            .limit(1)
            .execute()
        )
        if not (existe.data or []):
            return {"ok": False, "mensaje": "No encontramos tu identidad en el Jardín. Entra primero desde la puerta principal."}

        sb.table(TABLA_GRATITUDES).insert({
            "nombre_normalizado": nombre_norm,
            "nombre_visible": nombre_visible,
            "texto": texto_limpio,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        return {"ok": True, "mensaje": "Tu gratitud quedó guardada en el Templo."}
    except Exception as e:
        print("Error en guardar_gratitud:", e)
        return {"ok": False, "mensaje": "No se pudo guardar la gratitud en este momento. Intenta de nuevo."}


def listar_gratitudes(nombre: str, limite: int = 200):
    """Devuelve las gratitudes guardadas de 'nombre', más recientes primero.
    Por ahora es solo la lista cruda (texto + fecha); la vista tipo
    'constelación de luces' se construye después, en la capa visual."""
    nombre_norm = _normalizar_nombre(nombre)
    if not nombre_norm or not sb:
        return []
    try:
        res = (
            sb.table(TABLA_GRATITUDES)
            .select("texto, created_at")
            .eq("nombre_normalizado", nombre_norm)
            .order("created_at", desc=True)
            .limit(limite)
            .execute()
        )
        return res.data or []
    except Exception as e:
        print("Error en listar_gratitudes:", e)
        return []


# =====================================================================
# CÍRCULO DE HISTORIAS — el prado comunal del Jardín.
# A diferencia del Templo (fenix_gratitudes) y el Altar (fenix_luces),
# que son privados de cada persona, el Círculo es COMUNAL: todas las
# historias fluyen juntas (más reciente arriba). Solo se admiten historias
# "luminosas" — que hablen de amor, perdón, esperanza y afines — para
# mantener pura la energía del círculo, tal como pide la visión.
# =====================================================================
TABLA_HISTORIAS = "fenix_historias"

# Raíces (ya sin tildes) que consideramos "luz". Basta con que la historia
# contenga UNA para pasar el filtro. Deliberadamente sencillo y amplio, para
# no frustrar a quien escribe de corazón con otras palabras del mismo campo.
_RAICES_LUMINOSAS = (
    "amor", "amar", "ama", "amo", "perdon", "esperanz", "esper", "luz",
    "gratitud", "gracias", "agradec", "paz", "compasion", "fe ", " fe",
    "bendic", "sanacion", "sanar", "sana", "alma", "despert", "divin",
    "sagrad", "corazon", "humild", "consuelo", "misericord", "union",
    "hermano", "hermana", "teshua", "retorno", "milagro", "renac",
    "renace", "gozo", "alegria", "libertad", "confianza", "serenidad",
)


def _sin_tildes(texto: str) -> str:
    """Minúsculas y sin tildes/diacríticos, para comparar con las raíces."""
    import unicodedata
    base = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in base if unicodedata.category(c) != "Mn")


def _historia_es_luminosa(texto: str) -> bool:
    """True si la historia contiene alguna palabra de luz (amor, perdón,
    esperanza y afines). Es el 'filtro sencillo' de la visión del Círculo."""
    limpio = _sin_tildes(texto)
    return any(raiz.strip() and raiz in limpio for raiz in _RAICES_LUMINOSAS)


def guardar_historia(nombre: str, texto: str):
    """Publica una historia en el Círculo comunal a nombre de 'nombre'.

    Mismo patrón que guardar_gratitud: exige identidad ya registrada en el
    Jardín (no crea historias huérfanas) y, además, aplica el filtro de luz
    para preservar la vibración del círculo."""
    nombre_visible = (nombre or "").strip()
    nombre_norm = _normalizar_nombre(nombre)
    texto_limpio = (texto or "").strip()

    if not nombre_norm:
        return {"ok": False, "mensaje": "Falta tu nombre para compartir tu historia."}
    if not texto_limpio:
        return {"ok": False, "mensaje": "Escribe tu historia antes de compartirla."}
    if len(texto_limpio) > 2000:
        return {"ok": False, "mensaje": "Tu historia es muy larga; compártela en menos de 2000 caracteres."}
    if not _historia_es_luminosa(texto_limpio):
        return {"ok": False, "mensaje": "El Círculo florece con palabras de amor, perdón y esperanza. Vuelve a escribir tu historia desde esa luz. 🌸"}
    if not sb:
        return {"ok": False, "mensaje": "⚠️ Supabase no está configurado en el Space."}

    try:
        existe = (
            sb.table(TABLA_IDENTIDADES)
            .select("nombre_visible")
            .eq("nombre_normalizado", nombre_norm)
            .limit(1)
            .execute()
        )
        if not (existe.data or []):
            return {"ok": False, "mensaje": "No encontramos tu identidad en el Jardín. Entra primero desde la puerta principal."}

        sb.table(TABLA_HISTORIAS).insert({
            "nombre_normalizado": nombre_norm,
            "nombre_visible": nombre_visible,
            "texto": texto_limpio,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        return {"ok": True, "mensaje": "🌸 Tu historia ya florece en el Círculo."}
    except Exception as e:
        print("Error en guardar_historia:", e)
        return {"ok": False, "mensaje": "No se pudo compartir tu historia en este momento. Intenta de nuevo."}


def listar_historias(limite: int = 100):
    """Devuelve las historias del Círculo (de TODAS las personas), más
    recientes primero. Cada una con quién la escribió, el texto y la fecha.
    Es comunal a propósito: el Círculo es un prado compartido, no un diario
    privado como el Templo o el Altar."""
    if not sb:
        return []
    try:
        res = (
            sb.table(TABLA_HISTORIAS)
            .select("nombre_visible, texto, created_at")
            .order("created_at", desc=True)
            .limit(limite)
            .execute()
        )
        return res.data or []
    except Exception as e:
        print("Error en listar_historias:", e)
        return []


def generar_voz(texto: str, voz: str = None, rate: str = None, pitch: str = None, eco_filtro=None) -> str:
    """Genera el audio de la respuesta.

    FIX CONCURRENCIA: voz/rate/pitch/eco_filtro ahora se reciben como
    parámetros de la llamada, en vez de leerse de las variables globales
    VOZ_FENIX/VOZ_RATE/VOZ_PITCH/VOZ_ECO_FILTRO. Antes, con varios usuarios
    hablando a la vez, un usuario podía pisar la voz elegida por otro justo
    antes de que se generara su audio (condición de carrera sobre estado
    global compartido). Si no se pasa un valor, se cae a la global
    correspondiente solo por compatibilidad con código viejo que aún no
    haya sido actualizado para pasar estos parámetros.
    """
    voz = voz or VOZ_FENIX
    rate = rate or VOZ_RATE
    pitch = pitch or VOZ_PITCH
    if eco_filtro is None:
        eco_filtro = VOZ_ECO_FILTRO

    texto_limpio = texto.split("\n\n_(maestro:")[0].strip()
    if not texto_limpio:
        texto_limpio = texto
    texto_limpio = _quitar_markdown_para_voz(texto_limpio)

    ruta_salida = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False).name

    async def _generar(v, r, p):
        communicate = edge_tts.Communicate(texto_limpio, voice=v, rate=r, pitch=p)
        await communicate.save(ruta_salida)

    try:
        try:
            asyncio.run(_generar(voz, rate, pitch))
        except Exception as e:
            # Red de seguridad: si la voz/rate/pitch configurados fallan (p. ej. un
            # nombre de voz inválido), no dejar al usuario sin audio: reintentar con
            # una voz de respaldo que sabemos que siempre existe en edge-tts.
            print(f"Aviso: falló la voz '{voz}' ({e}). Reintentando con voz de respaldo.")
            asyncio.run(_generar("es-ES-AlvaroNeural", "-10%", "0Hz"))

        if eco_filtro:
            return _aplicar_eco_voz(ruta_salida, eco_filtro)
        return ruta_salida
    except Exception as e:
        print("Error generando voz:", e)
        return None
