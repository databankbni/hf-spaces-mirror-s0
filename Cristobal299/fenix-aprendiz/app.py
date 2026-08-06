# -*- coding: utf-8 -*-
"""
app.py
Interfaz de usuario mística (Frontend) basada en Gradio para Fénix Aprendiz.

Incluye el Bot de Inquietudes Humanas: una "preparación del oráculo" que sube
automáticamente +1 nivel por día (tope 100) y genera 10 inquietudes diarias,
rotando entre categorías (miedos existenciales, crisis de fe, propósito de vida,
debates bíblicos, consejo espiritual, alma y más allá) con profundidad creciente
según el nivel, sin repetir temas recientes.

Compatible con todas las versiones de Gradio (sin type="messages" ni parámetros experimentales).
"""

import os
import time
import threading
from datetime import datetime, timedelta
import gradio as gr
import fenix_core  # Importamos para inyectar voces místicas de forma dinámica
from fenix_core import (
    ciclo_completo,
    procesar_pdf,
    consultar_pdf,
    generar_voz,
    guardar_conversacion,
    cargar_conversaciones,
    revisar_conversaciones_pendientes,
    actualizar_claves_dinamicas,
    llamar_cerebras_directo,
    rotar_clave_cerebras_fallida,
    CEREBRAS_KEYS_POOL,
    NVIDIA_KEYS_POOL,
    describir_imagen,
    generar_imagen_ia,
    cargar_galeria_imagenes,
    texto_biblioteca,
    borrar_libro,
    listar_libros,
    guardar_gratitud,
    listar_gratitudes,
    guardar_historia,
    listar_historias,
)
from fenix_progreso import obtener_progreso, registrar_pregunta
from gradio_theme_fenix import apply_fenix_theme, FENIX_CSS, fenix_header, fenix_footer

# --- Experto en Hebreo (pestaña opcional). Import defensivo: si faltara
# hebreo.py, el resto del Space sigue funcionando igual y la pestaña avisa. ---
try:
    from hebreo import formatear_consulta_hebreo
except Exception as _e_heb:
    print(f"Aviso: no se pudo cargar hebreo.py ({_e_heb}). La pestaña de hebreo saldrá vacía.")
    def formatear_consulta_hebreo(_consulta):
        return ("El módulo de hebreo no está cargado en el Space. "
                "Sube hebreo.py y lexico_hebreo.json y reconstruye.")

SUFIJO_MAESTRO = "\n\n_(maestro:"

# El orbe se acelera al enviar y vuelve solo a su ritmo normal a los 14s.
# FIX CRÍTICO: cuando 'js' y 'fn' van en el MISMO evento con 'inputs' definidos,
# Gradio pasa esos inputs como argumentos a la función JS y usa lo que ELLA
# devuelva como los valores reales que llegan a 'fn'. La versión anterior no
# aceptaba ni devolvía nada, así que Gradio mandaba 'undefined' (-> None) en
# vez del mensaje real, y por eso 'responder()' recibía mensaje=None y petaba.
# Ahora la JS recibe (mensaje, historial, voz) y los devuelve TAL CUAL, usando
# la función solo para el efecto visual como efecto secundario.
JS_ORBE_PENSANDO = """
(mensaje, historial, voz, pdf) => {
    const orbe = document.querySelector('.orbe-luz');
    if (orbe) {
        orbe.classList.add('orbe-pensando');
        setTimeout(() => orbe.classList.remove('orbe-pensando'), 14000);
    }
    return [mensaje, historial, voz, pdf];
}
"""

# Analizador de volumen real de la voz de Fénix (Web Audio API), inyectado UNA
# vez en <head> con demo.launch(head=...) para que sobreviva a que Gradio
# reemplace el <audio> en cada respuesta nueva. Engancha un AnalyserNode al
# elemento de audio y, mientras suena, traduce el volumen instantáneo en la
# escala/brillo del orbe. Nota: los navegadores exigen un gesto del usuario
# para arrancar el AudioContext; como esto se dispara tras pulsar "Enviar",
# ese requisito ya queda cubierto.
SCRIPT_ANALIZADOR_VOZ = """
<script>
(function () {
    function iniciarAnalizadorVoz() {
        const audioEl = document.querySelector('#audio_voz_fenix audio');
        const orbe = document.querySelector('.orbe-luz');
        if (!audioEl || !orbe || audioEl._fenixConectado) return;
        audioEl._fenixConectado = true;

        try {
            if (!window._fenixAudioCtx) {
                window._fenixAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
            }
            const ctx = window._fenixAudioCtx;
            const source = ctx.createMediaElementSource(audioEl);
            const analyser = ctx.createAnalyser();
            analyser.fftSize = 64;
            source.connect(analyser);
            analyser.connect(ctx.destination);
            const datos = new Uint8Array(analyser.frequencyBinCount);

            function animar() {
                if (audioEl.paused || audioEl.ended) return;
                analyser.getByteFrequencyData(datos);
                const promedio = datos.reduce((a, b) => a + b, 0) / datos.length;
                const escala = 1 + (promedio / 255) * 0.6;
                const halo = 15 + (promedio / 255) * 60;
                orbe.style.transform = `scale(${escala})`;
                orbe.style.boxShadow = `0 0 ${halo}px ${halo / 2}px rgba(212,175,55,0.85)`;
                requestAnimationFrame(animar);
            }

            const limpiar = () => {
                orbe.classList.remove('orbe-hablando');
                orbe.style.transform = '';
                orbe.style.boxShadow = '';
            };

            audioEl.addEventListener('play', () => {
                if (ctx.state === 'suspended') ctx.resume();
                orbe.classList.add('orbe-hablando');
                animar();
            });
            audioEl.addEventListener('pause', limpiar);
            audioEl.addEventListener('ended', limpiar);
        } catch (e) {
            console.warn('Analizador de voz de Fénix no disponible:', e);
        }
    }

    // El <audio> de Gradio se crea/renueva de forma asíncrona; se observa el
    // DOM para engancharse en cuanto aparezca, en esta carga y en las siguientes.
    const obs = new MutationObserver(iniciarAnalizadorVoz);
    obs.observe(document.body, { childList: true, subtree: true });
    iniciarAnalizadorVoz();
})();
</script>
"""

BOT_ID = "espiritual"
PREGUNTAS_POR_DIA = 10
INTERVALO_SEGUNDOS = 86400 // PREGUNTAS_POR_DIA  # 8640s ≈ cada 2h24min

# Categorías por las que rota el oráculo. Con 10 preguntas/día y 6 categorías,
# ninguna se queda sin cubrir: en pocos días ya hay cobertura completa y el
# ciclo empieza de nuevo, ahora con más profundidad (según el nivel).
CATEGORIAS_ORACULO = [
    "miedos e inquietudes existenciales (muerte, vacío, soledad, sufrimiento)",
    "crisis de fe y dudas religiosas",
    "búsqueda de propósito y sentido de la vida",
    "debates y controversias de interpretación bíblica (pasajes concretos, "
    "aparentes contradicciones, contexto histórico y teológico)",
    "consejo práctico y consuelo espiritual ante situaciones difíciles de la vida real",
    "preguntas sobre el alma, la reencarnación, el juicio y el más allá",
]

# Mapa de nivel (0-100) -> profundidad esperada. Es la "preparación del oráculo":
# según el nivel actual, las inquietudes generadas ganan matiz y especificidad.
NIVELES_ORACULO = [
    (20, "preguntas introductorias y generales, propias de alguien que recién "
         "empieza a hacerse preguntas grandes sobre la vida"),
    (40, "preguntas más personales e íntimas sobre crisis de fe, pérdida, dolor "
         "y búsqueda de propósito"),
    (60, "debates teológicos con referencias a pasajes bíblicos concretos y sus "
         "posibles contradicciones, matices de traducción o interpretaciones distintas"),
    (80, "dilemas existenciales profundos: el problema del mal, el sufrimiento "
         "injusto, el libre albedrío frente a la voluntad divina, la naturaleza de Dios"),
    (100, "preguntas de altísima profundidad teológica y filosófica, comparando "
          "tradiciones espirituales distintas, cuestionando dogmas asumidos, y "
          "buscando consuelo genuino ante circunstancias extremas de la vida"),
]


def _descripcion_nivel_oraculo(nivel: int) -> str:
    for tope, descripcion in NIVELES_ORACULO:
        if nivel <= tope:
            return descripcion
    return NIVELES_ORACULO[-1][1]


def _categoria_del_turno(nivel: int, preguntas_hoy: int) -> str:
    """Rotación determinista: cada pregunta del día avanza a la siguiente
    categoría, y el nivel desplaza el punto de partida para no caer siempre
    en el mismo orden entre días."""
    indice = (nivel + preguntas_hoy) % len(CATEGORIAS_ORACULO)
    return CATEGORIAS_ORACULO[indice]


def _segundos_hasta_manana() -> int:
    ahora = datetime.now()
    manana = (ahora + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
    return max(60, int((manana - ahora).total_seconds()))


def identidad_login_ui(nombre, pin):
    """Envoltorio para el Jardín (Templo de Gratitud, Círculo de Historias,
    Río de Conversación): expone entrar_o_registrar_identidad como endpoint
    de API propio ('identidad_login'), separado por completo del chat
    ('responder'). Devuelve un JSON en texto plano para que el cliente
    Android lo parsee fácil, sin depender de un formato de salida nuevo."""
    import json as _json
    resultado = fenix_core.entrar_o_registrar_identidad(nombre, pin)
    return _json.dumps(resultado, ensure_ascii=False)


def gratitud_guardar_ui(nombre, texto):
    """Envoltorio de API para guardar una gratitud del Templo. Devuelve
    JSON en texto plano: {"ok": bool, "mensaje": str}."""
    import json as _json
    resultado = guardar_gratitud(nombre, texto)
    return _json.dumps(resultado, ensure_ascii=False)


def gratitud_listar_ui(nombre):
    """Envoltorio de API para listar las gratitudes guardadas de 'nombre'.
    Devuelve JSON en texto plano: una lista de {"texto":..., "created_at":...}."""
    import json as _json
    resultado = listar_gratitudes(nombre)
    return _json.dumps(resultado, ensure_ascii=False)


def circulo_publicar_ui(nombre, texto):
    """Envoltorio de API para publicar una historia en el Círculo comunal.
    Devuelve JSON en texto plano: {"ok": bool, "mensaje": str}."""
    import json as _json
    resultado = guardar_historia(nombre, texto)
    return _json.dumps(resultado, ensure_ascii=False)


def circulo_listar_ui():
    """Envoltorio de API para listar TODAS las historias del Círculo, más
    recientes primero. Devuelve JSON: lista de
    {"nombre_visible":..., "texto":..., "created_at":...}."""
    import json as _json
    resultado = listar_historias()
    return _json.dumps(resultado, ensure_ascii=False)


def altar_encender_ui(nombre, intencion):
    """Envoltorio de API para encender una luz en el Altar. Devuelve
    JSON en texto plano: {"ok": bool, "mensaje": str}."""
    import json as _json
    resultado = fenix_core.encender_luz(nombre, intencion)
    return _json.dumps(resultado, ensure_ascii=False)


def altar_listar_ui(nombre):
    """Envoltorio de API para listar las luces encendidas de 'nombre'.
    Devuelve JSON en texto plano: una lista de {"intencion":..., "created_at":...}."""
    import json as _json
    resultado = fenix_core.listar_luces(nombre)
    return _json.dumps(resultado, ensure_ascii=False)


def _ciclo_con_voz(mensaje, historial, voz_seleccionada, nombre_jardin="", clave_usuario=None, incluir_bot_en_vista=True, ruta_pdf_adjunto=None):
    """Lógica compartida de un turno de chat + generación de audio.
    La usan tanto responder() (la web del Space, sin cambios de comportamiento)
    como responder_movil() (el endpoint nuevo y explícito para la app Android,
    que además puede mandar nombre_jardin para que Fénix use el contexto del
    Jardín — lección actual y gratitudes recientes — y clave_usuario para
    usar la clave personal de Cerebras de esa persona si la guardó).

    incluir_bot_en_vista controla si el río devuelto (historial_view_out)
    incluye las inquietudes del bot autónomo. La web lo deja en True (sin
    cambios); la app móvil lo pasa en False para ver SOLO a las personas."""
    if not mensaje.strip():
        return historial, "", None, cargar_conversaciones(limite=300, incluir_bot=incluir_bot_en_vista)

    historial = historial or []

    # 🧹 Purificación del historial para evitar Error 400 en la API de Cerebras
    # FIX DOBLE MAESTRO: ademas de normalizar el formato, se limpia el sufijo
    # "_(maestro: ...)" de los mensajes del asistente ANTES de enviarlos a Cerebras.
    historial_limpio = []
    for msg in historial:
        if isinstance(msg, dict) and "role" in msg and "content" in msg:
            contenido = msg["content"]
            if msg["role"] == "assistant" and isinstance(contenido, str):
                contenido = contenido.split(SUFIJO_MAESTRO)[0].strip()
            historial_limpio.append({
                "role": msg["role"],
                "content": contenido
            })

    config_voces = {
        "Anciano Sabio (Hombre Místico)": {
            "voice": "es-ES-AlvaroNeural", "rate": "-14%", "pitch": "-12Hz", "eco_filtro": None
        },
        "Eco del Anciano (Voz Serena)": {
            "voice": "es-ES-AlvaroNeural", "rate": "-10%", "pitch": "-16Hz", "eco_filtro": fenix_core.ECO_CAVERNA
        },
        "Voz de Teshuá (El Retorno)": {
            "voice": "es-ES-AlvaroNeural", "rate": "-17%", "pitch": "-19Hz", "eco_filtro": fenix_core.ECO_TESHUA
        },
        "Guía Solemne (Hombre Profundo)": {
            "voice": "es-ES-AlvaroNeural", "rate": "-6%", "pitch": "-22Hz", "eco_filtro": None
        },
        "Oráculo Celestial (Mujer Sacra)": {
            "voice": "es-ES-ElviraNeural", "rate": "-10%", "pitch": "-6Hz", "eco_filtro": None
        },
        "Esencia Cálida (Voz Pausada)": {
            "voice": "es-MX-DaliaNeural", "rate": "-9%", "pitch": "-3Hz", "eco_filtro": None
        }
    }

    cfg = config_voces.get(voz_seleccionada, config_voces["Anciano Sabio (Hombre Místico)"])

    respuesta, evaluacion = ciclo_completo(mensaje, historial_limpio, nombre_jardin, clave_usuario, ruta_pdf_adjunto)
    respuesta = respuesta.split(SUFIJO_MAESTRO)[0].strip()
    texto_final = f"{respuesta}\n\n_(maestro: {evaluacion['veredicto']} · {evaluacion['categoria']})_"

    historial.append({"role": "user", "content": mensaje})
    historial.append({"role": "assistant", "content": texto_final})

    guardar_conversacion(mensaje, texto_final)

    # FIX CONCURRENCIA: la voz elegida por ESTE usuario se pasa directo a
    # generar_voz, en vez de guardarse en una variable global de fenix_core.
    # Así, si otro usuario manda un mensaje al mismo tiempo con otra voz
    # elegida, no se pisan entre sí.
    audio_path = generar_voz(
        respuesta,
        voz=cfg["voice"],
        rate=cfg["rate"],
        pitch=cfg["pitch"],
        eco_filtro=cfg.get("eco_filtro"),
    )
    historial_actualizado = cargar_conversaciones(limite=300, incluir_bot=incluir_bot_en_vista)

    return historial, "", audio_path, historial_actualizado


def responder(mensaje, historial, voz_seleccionada, pdf_adjunto=None):
    ruta_pdf = pdf_adjunto if isinstance(pdf_adjunto, str) else getattr(pdf_adjunto, "name", None)
    return _ciclo_con_voz(mensaje, historial, voz_seleccionada, nombre_jardin="", clave_usuario=None, ruta_pdf_adjunto=ruta_pdf)


def responder_movil(mensaje, historial, voz_seleccionada, clave_usuario, nombre_jardin):
    """Endpoint explícito para la app Android (api_name='fenix_chat_movil').
    Igual que responder(), pero recibiendo clave_usuario (la clave personal
    de Cerebras guardada en el móvil, o "" si usa el pool compartido) y
    nombre_jardin (para el contexto de lección+gratitudes del Jardín, o ""
    si esa persona no tiene identidad ahí todavía)."""
    return _ciclo_con_voz(
        mensaje, historial, voz_seleccionada,
        nombre_jardin=nombre_jardin or "",
        clave_usuario=(clave_usuario or None),
        incluir_bot_en_vista=False,  # el Río móvil muestra SOLO a las personas
    )

def subir_pdf(archivo):
    if archivo is None:
        return "Por favor, selecciona un archivo PDF válido.", gr.update()
    resultado = procesar_pdf(archivo)
    # Refresca la lista de la biblioteca y el desplegable tras subir
    nombres = [n for n, _ in listar_libros()]
    return resultado + "\n\n" + texto_biblioteca(), gr.update(choices=nombres, value=None)

def examinar_pdf(archivo, pregunta):
    """Pestaña 'Examinar PDF': lee el PDF subido y responde la pregunta
    cruzándolo con el conocimiento ya indexado en la base de datos. No guarda
    el PDF en la biblioteca (para eso está la pestaña 'Memoria Documental')."""
    if archivo is None:
        return "Sube un PDF y escribe tu pregunta para que Fénix lo examine."
    if not (pregunta or "").strip():
        return "Escribe qué quieres saber sobre el documento."
    return consultar_pdf(archivo, pregunta)


def refrescar_biblioteca():
    nombres = [n for n, _ in listar_libros()]
    return texto_biblioteca(), gr.update(choices=nombres, value=None)

def borrar_libro_ui(nombre):
    estado = borrar_libro(nombre)
    nombres = [n for n, _ in listar_libros()]
    return estado + "\n\n" + texto_biblioteca(), gr.update(choices=nombres, value=None)

def responder_vision(ruta_imagen, pregunta_imagen):
    if ruta_imagen is None:
        return "Sube o pega una imagen primero para que Fénix pueda describirla."
    return describir_imagen(ruta_imagen, pregunta_imagen or "")


def responder_creacion_imagen(prompt_imagen):
    ruta_local, url_publica, estado = generar_imagen_ia(prompt_imagen)
    galeria = cargar_galeria_imagenes()
    return ruta_local, estado, galeria


def refrescar_galeria():
    return cargar_galeria_imagenes()


def controlar_musica(seleccion):
    mapeo_canciones = {
        "Canción 1 (Espiritual)": "cancion_1.mp3",
        "Canción 2 (Meditación)": "cancion_2.mp3",
        "Canción 3 (Sacra)": "cancion_3.mp3",
        "Canción 4 (Armonía)": "cancion_4.mp3",
        "Canción 5 (Celestial)": "cancion_5.mp3",
        "Canción 6 (Mística)": "cancion_6.mp3"
    }

    if seleccion == "Silencio":
        return None, "_Atmósfera en silencio._"

    archivo_objetivo = mapeo_canciones.get(seleccion)
    if archivo_objetivo and os.path.exists(archivo_objetivo):
        return archivo_objetivo, f"🎵 **Sonando ahora:** {seleccion}"
    else:
        return None, f"⚠️ El archivo `{archivo_objetivo}` no está en el Space. Súbelo para escucharlo."

def guardar_claves_usuario(pin_admin, c1, c2, c3, c4, n1, n2, n3, n4):
    pin_real = os.environ.get("FENIX_ADMIN_PIN", "")
    if not pin_real:
        return "🔒 Panel bloqueado: define el secret FENIX_ADMIN_PIN en los Settings del Space para habilitarlo."
    if (pin_admin or "").strip() != pin_real.strip():
        return "🔒 Código de administrador incorrecto."

    cerebras_list = [c1, c2, c3, c4]
    nvidia_list = [n1, n2, n3, n4]
    if not any(k and k.strip() for k in cerebras_list + nvidia_list):
        return "⚠️ No se aplicó nada: todas las casillas están vacías."
    actualizar_claves_dinamicas(cerebras_list, nvidia_list)
    return "✅ ¡Pool de claves actualizado en caliente! Los modelos ahora rotarán entre estas credenciales."


def estado_progreso_oraculo() -> str:
    """Muestra en la pestaña de configuración cómo va la preparación del oráculo."""
    progreso = obtener_progreso(BOT_ID)
    nivel = progreso.get("nivel", 0)
    preguntas_hoy = progreso.get("preguntas_hoy", 0)
    descripcion = _descripcion_nivel_oraculo(nivel)
    categoria_actual = _categoria_del_turno(nivel, preguntas_hoy)
    return (
        f"🔮 **Nivel de preparación:** {nivel}/100\n\n"
        f"**Profundidad de hoy:** {descripcion}\n\n"
        f"**Próxima categoría:** {categoria_actual}\n\n"
        f"**Inquietudes generadas hoy:** {preguntas_hoy}/{PREGUNTAS_POR_DIA}"
    )


# =====================================================================
# BOT DE INQUIETUDES HUMANAS INTEGRADO (BACKGROUND THREAD)
# Preparación del oráculo: sube +1 nivel por día, 10 inquietudes/día,
# rotando categorías y con profundidad creciente segun el nivel.
# =====================================================================
def bucle_inquietudes_espirituales():
    time.sleep(5)
    print("✨ [Nube] Iniciando el Bot de Inquietudes Existenciales (preparación del oráculo)...")

    historial_simulado = []

    while True:
        try:
            progreso = obtener_progreso(BOT_ID)
            nivel = progreso.get("nivel", 0)
            preguntas_hoy = progreso.get("preguntas_hoy", 0)

            if preguntas_hoy >= PREGUNTAS_POR_DIA:
                print(f"💤 [Bot Oráculo] Meta diaria cumplida (nivel {nivel}/100). Esperando al día siguiente...")
                time.sleep(_segundos_hasta_manana())
                continue

            c_key = fenix_core.CEREBRAS_KEYS_POOL[0] if fenix_core.CEREBRAS_KEYS_POOL else (os.environ.get("CEREBRAS_KEY") or os.environ.get("CEREBRAS_API_KEY"))
            if not c_key:
                print("⚠️ [Bot Nube] Esperando configuración de la clave de Cerebras...")
                time.sleep(30)
                continue

            categoria = _categoria_del_turno(nivel, preguntas_hoy)
            descripcion_nivel = _descripcion_nivel_oraculo(nivel)

            temas_previos = progreso.get("temas_recientes") or []
            evitar = ""
            if temas_previos:
                lista = "\n".join(f"- {t[:100]}" for t in temas_previos[-10:])
                evitar = f"\n\nNO repitas ni parafrasees estas inquietudes ya usadas recientemente:\n{lista}"

            prompt_generador_crisis = (
                f"Eres un simulador de la psique humana real, atrapada en el sufrimiento, la duda "
                f"existencial y la búsqueda de la verdad. Estás generando la inquietud del nivel "
                f"{nivel} de 100 en la preparación progresiva de un oráculo espiritual. "
                f"Hoy debes enfocarte en esta categoría concreta: {categoria}. "
                f"El grado de profundidad correspondiente a este nivel es: {descripcion_nivel}. "
                "Redacta UNA pregunta o inquietud extremadamente profunda, sincera y de la mejor "
                "calidad posible para ese nivel y esa categoría. Escribe en primera persona, como un "
                "buscador desesperado, un filósofo atormentado, alguien con miedo genuino, o alguien "
                "cuestionando un pasaje concreto de la Biblia." + evitar +
                "\nDevuelve ÚNICAMENTE la inquietud mística cruda, sin introducciones corporativas, "
                "saludos ni preámbulos."
            )

            try:
                inquietud_generada = llamar_cerebras_directo(
                    api_key=c_key,
                    model=fenix_core.MODELO_FENIX,
                    messages=[{"role": "system", "content": prompt_generador_crisis},
                              {"role": "user", "content": "Genera la inquietud ahora."}],
                    temperature=0.95,
                    # gpt-oss-120b es un modelo razonador: con 220 tokens se los
                    # gastaba TODOS "pensando" y nunca escribía la respuesta
                    # (llegaba 'reasoning' sin 'content'). reasoning_effort=low
                    # recorta el pensamiento interno y max_tokens=700 deja
                    # presupuesto de sobra para la pregunta final.
                    max_tokens=700,
                    reasoning_effort="low"
                ).strip()
            except Exception:
                rotar_clave_cerebras_fallida()
                raise

            respuesta, evaluacion = ciclo_completo(inquietud_generada, historial_simulado)

            texto_persistido = f"{respuesta}\n\n_(maestro: {evaluacion['veredicto']} · {evaluacion['categoria']})_"
            guardar_conversacion(f"[Bot Autónomo · Nivel {nivel}/100 · {categoria}] {inquietud_generada}", texto_persistido)
            registrar_pregunta(BOT_ID, inquietud_generada)

            historial_simulado.append({"role": "user", "content": inquietud_generada})
            historial_simulado.append({"role": "assistant", "content": respuesta})
            if len(historial_simulado) > 6:
                historial_simulado = historial_simulado[-6:]

            print(f"✅ [Bot Oráculo] Inquietud {preguntas_hoy + 1}/{PREGUNTAS_POR_DIA} del nivel {nivel}/100 ({categoria}) registrada.")

        except Exception as e:
            print(f"⚠️ [Bot Nube] Error en el ciclo de meditación continua: {e}")

        time.sleep(INTERVALO_SEGUNDOS)

# Lanzar hilo en segundo plano
threading.Thread(target=bucle_inquietudes_espirituales, daemon=True).start()
# =====================================================================


with gr.Blocks(title="Fénix Aprendiz") as demo:
    fenix_header("Fénix Aprendiz", "Una experiencia mística e inmersiva gobernada por Inteligencia Artificial.")

    with gr.Tabs():
        # --- PESTAÑA 1: EL ORÁCULO ---
        with gr.TabItem("🔮 El Oráculo"):
            gr.HTML(
                '<div class="orbe-contenedor">'
                '<div class="brasa"></div><div class="brasa"></div>'
                '<div class="brasa"></div><div class="brasa"></div>'
                '<span class="letra-hebrea letra-1">ת</span>'
                '<span class="letra-hebrea letra-2">ש</span>'
                '<span class="letra-hebrea letra-3">ו</span>'
                '<span class="letra-hebrea letra-4">ע</span>'
                '<span class="letra-hebrea letra-5">ה</span>'
                '<div class="orbe-luz"></div>'
                '</div>'
            )
            with gr.Row():
                with gr.Column(scale=3):
                    chatbot = gr.Chatbot(
                        label="Canal de Comunicación Sagrada",
                        height=520,
                        value=cargar_conversaciones(limite=40),
                    )
                    with gr.Row():
                        txt = gr.Textbox(
                            placeholder="Escríbele a Fénix...",
                            show_label=False,
                            scale=4,
                            lines=1
                        )
                        send_btn = gr.Button("Enviar 🔥", scale=1)

                    pdf_chat = gr.File(
                        label="📎 Adjunta un PDF y pregúntale a Fénix (opcional)",
                        file_types=[".pdf"],
                        height=90,
                    )

                    audio_respuesta = gr.Audio(
                        label="🔊 Voz de Fénix",
                        autoplay=True,
                        elem_id="audio_voz_fenix"
                    )

                with gr.Column(scale=1):
                    gr.Markdown("### 🗣️ Identidad Vocal")
                    selector_voz = gr.Dropdown(
                        choices=[
                            "Anciano Sabio (Hombre Místico)",
                            "Eco del Anciano (Voz Serena)",
                            "Voz de Teshuá (El Retorno)",
                            "Guía Solemne (Hombre Profundo)",
                            "Oráculo Celestial (Mujer Sacra)",
                            "Esencia Cálida (Voz Pausada)"
                        ],
                        value="Guía Solemne (Hombre Profundo)",
                        label="Selecciona la voz de Fénix",
                        interactive=True
                    )

                    gr.Markdown("### 🎶 Ambiente Musical")
                    selector_musica = gr.Dropdown(
                        choices=[
                            "Silencio",
                            "Canción 1 (Espiritual)",
                            "Canción 2 (Meditación)",
                            "Canción 3 (Sacra)",
                            "Canción 4 (Armonía)",
                            "Canción 5 (Celestial)",
                            "Canción 6 (Mística)"
                        ],
                        value="Silencio",
                        label="Elige la melodía de fondo",
                        interactive=True
                    )
                    musica_status = gr.Markdown("_Atmósfera en silencio._")
                    musica_player = gr.Audio(
                        label="Reproductor en Bucle",
                        loop=True,
                        autoplay=True
                    )

        # --- PESTAÑA 2: MEMORIA DOCUMENTAL (SUBIDA DE PDF) ---
        with gr.TabItem("עברית · Experto en Hebreo"):
            gr.Markdown("### Consulta el hebreo: palabra hebrea, nº Strong (H430) o palabra en español")
            with gr.Row():
                heb_in = gr.Textbox(label="Consulta",
                                    placeholder="אלהים  ·  H430  ·  luz", scale=4)
                heb_btn = gr.Button("Consultar 🔍", scale=1)
            heb_out = gr.Textbox(label="Del diccionario", lines=10, interactive=False)
            heb_btn.click(fn=formatear_consulta_hebreo, inputs=heb_in, outputs=heb_out)
            heb_in.submit(fn=formatear_consulta_hebreo, inputs=heb_in, outputs=heb_out)

        with gr.TabItem("📄 Memoria Documental"):
            gr.Markdown("### 📚 Enseña nuevos conocimientos a Fénix")
            gr.Markdown("Al subir un manuscrito en PDF, el sistema lo segmentará y guardará en Supabase. Fénix recurrirá a él en cada dilema.")
            with gr.Row():
                with gr.Column():
                    pdf_input = gr.File(label="Carga tu archivo PDF", file_types=[".pdf"])
                with gr.Column():
                    pdf_status = gr.Markdown("_Esperando un documento sagrado..._")

            gr.Markdown("---")
            gr.Markdown("### 🗂️ Biblioteca de Fénix")
            gr.Markdown("Aquí ves todos los libros cargados. Si alguno no encaja con el mensaje de Teshuá, puedes borrarlo (es reversible: vuelves a subir el PDF cuando quieras).")
            biblioteca_estado = gr.Markdown("_Pulsa actualizar para ver los libros..._")
            with gr.Row():
                selector_libro = gr.Dropdown(label="Elige un libro para borrar", choices=[], value=None, interactive=True)
                btn_actualizar_biblioteca = gr.Button("🔄 Actualizar lista")
                btn_borrar_libro = gr.Button("🗑️ Borrar libro elegido", variant="stop")

        # --- PESTAÑA 2.2: EXAMINAR UN PDF (consulta puntual + base de datos) ---
        with gr.TabItem("🔎 Examinar PDF"):
            gr.Markdown("### 🔎 Sube un PDF y pregúntale a Fénix")
            gr.Markdown("Fénix lee el documento que subas AQUÍ y te responde combinándolo con el conocimiento que ya tiene indexado en la base de datos. Esto es una consulta puntual: no guarda el PDF en la biblioteca (si quieres que lo aprenda para siempre, súbelo en la pestaña 'Memoria Documental').")
            with gr.Row():
                with gr.Column():
                    examinar_pdf_input = gr.File(label="Sube el PDF a examinar", file_types=[".pdf"])
                    examinar_pregunta = gr.Textbox(
                        label="¿Qué quieres preguntarle a este documento?",
                        placeholder="Ej: ¿Qué dice este texto sobre el desapego del ego? Resúmelo y compáralo con tus libros.",
                        lines=3,
                    )
                    examinar_btn = gr.Button("🔎 Examinar y responder", variant="primary")
                with gr.Column():
                    examinar_output = gr.Textbox(
                        label="Respuesta de Fénix",
                        lines=16,
                        interactive=False,
                    )

        # --- PESTAÑA 2.5: VISIÓN Y CREACIÓN DE IMÁGENES (IA GRATUITA) ---
        with gr.TabItem("🖼️ Visión & Creación"):
            gr.Markdown("### 👁️ Ojo de Fénix — describir imágenes")
            gr.Markdown("Sube una imagen y Fénix la describirá usando visión gratuita (NVIDIA NIM).")
            with gr.Row():
                with gr.Column():
                    vision_input = gr.Image(label="Sube una imagen", type="filepath")
                    vision_pregunta = gr.Textbox(
                        label="¿Qué quieres preguntar sobre la imagen? (opcional)",
                        placeholder="Ej: ¿Qué simbolismo espiritual ves aquí?"
                    )
                    vision_btn = gr.Button("👁️ Describir imagen", variant="primary")
                with gr.Column():
                    vision_output = gr.Textbox(label="Descripción de Fénix", lines=10, interactive=False)

            gr.Markdown("---")
            gr.Markdown("### 🎨 Fragua de Imágenes — creación con IA (gratis)")
            gr.Markdown("Describe la imagen que quieres crear. Se genera gratis y queda guardada en tu galería de Supabase.")
            with gr.Row():
                with gr.Column():
                    crear_prompt = gr.Textbox(
                        label="Describe la imagen especial que quieres crear",
                        placeholder="Ej: un ave fénix dorada renaciendo de las cenizas, estilo místico, fondo negro"
                    )
                    crear_btn = gr.Button("🔥 Crear imagen", variant="primary")
                    crear_status = gr.Markdown("_Esperando tu visión..._")
                with gr.Column():
                    crear_output = gr.Image(label="Imagen creada", type="filepath")

            gr.Markdown("#### 🗂️ Galería guardada en Supabase")
            btn_refrescar_galeria = gr.Button("🔄 Refrescar galería")
            galeria_imagenes = gr.Gallery(label="Imágenes especiales creadas", columns=4, height="auto")

        # --- PESTAÑA 3: HISTORIAL ---
        with gr.TabItem("🕰️ Historial"):
            gr.Markdown("### 🕰️ Conversaciones pasadas con Fénix")
            gr.Markdown("Conversaciones unificadas en Supabase. Haz clic en actualizar para traer los últimos retos del bot de fondo.")
            historial_view = gr.Chatbot(
                label="Historial completo",
                height=600,
                value=cargar_conversaciones(limite=300),
            )
            with gr.Row():
                btn_refrescar_historial = gr.Button("🔄 Actualizar historial")
                btn_revisar_lecciones = gr.Button("🎓 Revisar historial y aprender")
            estado_revision = gr.Markdown("_Fénix aprende en tiempo real de cada turno._")

        # --- PESTAÑA 4: MULTI-API KEYS Y PROGRESO ---
        with gr.TabItem("⚙️ Configuración"):
            gr.Markdown("### 🔮 Preparación del Oráculo (0 a 100)")
            gr.Markdown("El bot de fondo sube +1 nivel automáticamente cada día, rota entre 6 categorías (miedos, crisis de fe, propósito, debates bíblicos, consejo, alma/más allá) y genera 10 inquietudes diarias, sin repetir temas.")
            progreso_view = gr.Markdown(estado_progreso_oraculo())
            btn_refrescar_progreso = gr.Button("🔄 Actualizar progreso")

            gr.Markdown("---")
            gr.Markdown("### 🔑 Panel de Multi-API Keys en Caliente")
            gr.Markdown("Configura credenciales alternativas. Requiere el código de administrador (secret `FENIX_ADMIN_PIN` del Space). El sistema rotará automáticamente ante cualquier error de red.")
            admin_pin = gr.Textbox(label="🔐 Código de administrador", type="password")
            with gr.Row():
                with gr.Column():
                    gr.Markdown("#### 🟢 API Keys de Cerebras (Hasta 4)")
                    g_key_1 = gr.Textbox(label="Cerebras Key 1 (Principal)", type="password")
                    g_key_2 = gr.Textbox(label="Cerebras Key 2", type="password")
                    g_key_3 = gr.Textbox(label="Cerebras Key 3", type="password")
                    g_key_4 = gr.Textbox(label="Cerebras Key 4", type="password")

                with gr.Column():
                    gr.Markdown("#### 🟢 API Keys de NVIDIA (Hasta 4)")
                    n_key_1 = gr.Textbox(label="NVIDIA Key 1 (Principal)", type="password")
                    n_key_2 = gr.Textbox(label="NVIDIA Key 2", type="password")
                    n_key_3 = gr.Textbox(label="NVIDIA Key 3", type="password")
                    n_key_4 = gr.Textbox(label="NVIDIA Key 4", type="password")

            btn_guardar_claves = gr.Button("💾 Aplicar y Registrar Claves", variant="primary")
            estado_claves = gr.Markdown("_Pool de claves activo y listo._")

    # --- Endpoint de API "identidad_login" para el Jardín (Templo de
    # Gratitud, Círculo de Historias, Río de Conversación) ---
    # Componentes ocultos: no aparecen en la interfaz visible del chat, solo
    # existen para que Android pueda llamar a gradio_api/call/identidad_login.
    with gr.Row(visible=False):
        identidad_nombre_in = gr.Textbox(label="nombre")
        identidad_pin_in = gr.Textbox(label="pin")
        identidad_resultado_out = gr.Textbox(label="resultado_json")
        identidad_btn = gr.Button("identidad_login")

    identidad_btn.click(
        fn=identidad_login_ui,
        inputs=[identidad_nombre_in, identidad_pin_in],
        outputs=[identidad_resultado_out],
        api_name="identidad_login",
    )

    # --- Endpoints de API del Templo de Gratitud ---
    with gr.Row(visible=False):
        gratitud_nombre_in = gr.Textbox(label="nombre")
        gratitud_texto_in = gr.Textbox(label="texto")
        gratitud_guardar_out = gr.Textbox(label="resultado_json")
        gratitud_guardar_btn = gr.Button("gratitud_guardar")

    gratitud_guardar_btn.click(
        fn=gratitud_guardar_ui,
        inputs=[gratitud_nombre_in, gratitud_texto_in],
        outputs=[gratitud_guardar_out],
        api_name="gratitud_guardar",
    )

    with gr.Row(visible=False):
        gratitud_listar_nombre_in = gr.Textbox(label="nombre")
        gratitud_listar_out = gr.Textbox(label="resultado_json")
        gratitud_listar_btn = gr.Button("gratitud_listar")

    gratitud_listar_btn.click(
        fn=gratitud_listar_ui,
        inputs=[gratitud_listar_nombre_in],
        outputs=[gratitud_listar_out],
        api_name="gratitud_listar",
    )

    # --- Endpoints de API del Altar de la Luz ---
    with gr.Row(visible=False):
        altar_nombre_in = gr.Textbox(label="nombre")
        altar_intencion_in = gr.Textbox(label="intencion")
        altar_encender_out = gr.Textbox(label="resultado_json")
        altar_encender_btn = gr.Button("altar_encender")

    altar_encender_btn.click(
        fn=altar_encender_ui,
        inputs=[altar_nombre_in, altar_intencion_in],
        outputs=[altar_encender_out],
        api_name="altar_encender",
    )

    with gr.Row(visible=False):
        altar_listar_nombre_in = gr.Textbox(label="nombre")
        altar_listar_out = gr.Textbox(label="resultado_json")
        altar_listar_btn = gr.Button("altar_listar")

    altar_listar_btn.click(
        fn=altar_listar_ui,
        inputs=[altar_listar_nombre_in],
        outputs=[altar_listar_out],
        api_name="altar_listar",
    )

    # --- Endpoints de API del Círculo de Historias (comunal) ---
    with gr.Row(visible=False):
        circulo_nombre_in = gr.Textbox(label="nombre")
        circulo_texto_in = gr.Textbox(label="texto")
        circulo_publicar_out = gr.Textbox(label="resultado_json")
        circulo_publicar_btn = gr.Button("circulo_publicar")

    circulo_publicar_btn.click(
        fn=circulo_publicar_ui,
        inputs=[circulo_nombre_in, circulo_texto_in],
        outputs=[circulo_publicar_out],
        api_name="circulo_publicar",
    )

    with gr.Row(visible=False):
        circulo_listar_out = gr.Textbox(label="resultado_json")
        circulo_listar_btn = gr.Button("circulo_listar")

    circulo_listar_btn.click(
        fn=circulo_listar_ui,
        inputs=[],
        outputs=[circulo_listar_out],
        api_name="circulo_listar",
    )


    # --- Endpoint explícito para el chat de la app Android (Jardín) ---
    # Deliberadamente separado de txt.submit/send_btn.click (la web del
    # Space), que no tienen api_name explícito y no deben tocarse. Este es
    # el único endpoint de chat que la app móvil debería llamar de aquí
    # en adelante: FenixApiClient.kt necesita apuntar a "fenix_chat_movil"
    # y mandar el nombre del Jardín (o "" si la persona no tiene identidad).
    with gr.Row(visible=False):
        movil_mensaje_in = gr.Textbox(label="mensaje")
        movil_historial_in = gr.JSON(label="historial")
        movil_voz_in = gr.Textbox(label="voz_seleccionada")
        movil_clave_in = gr.Textbox(label="clave_usuario")
        movil_nombre_in = gr.Textbox(label="nombre_jardin")
        movil_historial_out = gr.JSON(label="historial_out")
        movil_txt_out = gr.Textbox(label="txt_out")
        movil_audio_out = gr.Audio(label="audio_out")
        movil_historial_view_out = gr.JSON(label="historial_view_out")
        movil_btn = gr.Button("fenix_chat_movil")

    movil_btn.click(
        fn=responder_movil,
        inputs=[movil_mensaje_in, movil_historial_in, movil_voz_in, movil_clave_in, movil_nombre_in],
        outputs=[movil_historial_out, movil_txt_out, movil_audio_out, movil_historial_view_out],
        api_name="fenix_chat_movil",
    )

    # Gestión de Eventos
    txt.submit(
        fn=responder,
        inputs=[txt, chatbot, selector_voz, pdf_chat],
        outputs=[chatbot, txt, audio_respuesta, historial_view],
        js=JS_ORBE_PENSANDO
    )
    send_btn.click(
        fn=responder,
        inputs=[txt, chatbot, selector_voz, pdf_chat],
        outputs=[chatbot, txt, audio_respuesta, historial_view],
        js=JS_ORBE_PENSANDO
    )
    btn_refrescar_historial.click(
        fn=lambda: cargar_conversaciones(limite=300),
        outputs=historial_view
    )
    btn_revisar_lecciones.click(
        fn=revisar_conversaciones_pendientes,
        outputs=estado_revision
    )
    vision_btn.click(
        fn=responder_vision,
        inputs=[vision_input, vision_pregunta],
        outputs=[vision_output]
    )
    crear_btn.click(
        fn=responder_creacion_imagen,
        inputs=[crear_prompt],
        outputs=[crear_output, crear_status, galeria_imagenes]
    )
    btn_refrescar_galeria.click(
        fn=refrescar_galeria,
        inputs=[],
        outputs=[galeria_imagenes]
    )
    demo.load(
        fn=refrescar_galeria,
        inputs=[],
        outputs=[galeria_imagenes]
    )

    pdf_input.change(
        fn=subir_pdf,
        inputs=pdf_input,
        outputs=[pdf_status, selector_libro]
    )
    examinar_btn.click(
        fn=examinar_pdf,
        inputs=[examinar_pdf_input, examinar_pregunta],
        outputs=[examinar_output]
    )
    btn_actualizar_biblioteca.click(
        fn=refrescar_biblioteca,
        inputs=None,
        outputs=[biblioteca_estado, selector_libro]
    )
    btn_borrar_libro.click(
        fn=borrar_libro_ui,
        inputs=selector_libro,
        outputs=[biblioteca_estado, selector_libro]
    )
    selector_musica.change(
        fn=controlar_musica,
        inputs=selector_musica,
        outputs=[musica_player, musica_status]
    )
    btn_guardar_claves.click(
        fn=guardar_claves_usuario,
        inputs=[admin_pin, g_key_1, g_key_2, g_key_3, g_key_4, n_key_1, n_key_2, n_key_3, n_key_4],
        outputs=estado_claves
    )
    btn_refrescar_progreso.click(
        fn=estado_progreso_oraculo,
        outputs=progreso_view
    )

    fenix_footer()

if __name__ == "__main__":
    # FIX CONCURRENCIA: sin queue(), Gradio por defecto ya encola las
    # peticiones, pero con concurrency_count=1 implícito en muchas versiones
    # (una petición a la vez para TODO el Space). default_concurrency_limit
    # sube cuántas peticiones de 'responder' (y del resto de botones) se
    # procesan en paralelo. Súbelo con cuidado: cada una consume RAM/CPU del
    # Space y hace una llamada a Cerebras/NVIDIA/Edge-TTS en simultáneo.
    # Con el hardware básico gratuito de HF, 4 es un punto de partida
    # razonable; si tienes hardware pago con más CPU/RAM, puedes subirlo.
    demo.queue(default_concurrency_limit=4, max_size=50)
    demo.launch(theme=apply_fenix_theme(), css=FENIX_CSS, head=SCRIPT_ANALIZADOR_VOZ)
