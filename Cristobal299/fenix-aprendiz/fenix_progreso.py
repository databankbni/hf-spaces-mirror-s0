"""
fenix_progreso.py
Gestión de progreso persistente para los bots autónomos de Fénix (Código y Espiritual).

Por qué existe este archivo:
- Antes el bot de fondo generaba preguntas "a ciegas": sin memoria de qué nivel
  llevaba ni de qué ya había preguntado. Cada reinicio del Space perdía ese contexto.
- Ahora el progreso (nivel 0-100, día actual, preguntas hechas hoy, últimos temas)
  vive en Supabase, en la tabla `fenix_progreso`. Así la "carrera" o la
  "preparación del oráculo" avanza de verdad día a día, sobreviva o no el Space
  a reinicios de Hugging Face.

Requiere la tabla `fenix_progreso` (ver fenix_progreso_schema.sql).
Copia este archivo TAL CUAL en ambos Spaces (Código y Espiritual): es genérico,
no depende de fenix_core, solo necesita SUPABASE_URL y SUPABASE_KEY.
"""

import os
from datetime import date, datetime, timezone
from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

sb = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

NIVEL_MAXIMO = 100


def obtener_progreso(bot_id: str) -> dict:
    """Trae el progreso de un bot ('codigo' o 'espiritual'). Si es la primera vez,
    lo crea en nivel 0. Si cambió el día desde la última consulta, sube el nivel
    en +1 (con tope en 100) y reinicia el contador de preguntas del día.
    """
    hoy = date.today().isoformat()
    vacio = {"bot_id": bot_id, "nivel": 0, "fecha": hoy, "preguntas_hoy": 0, "temas_recientes": []}

    if not sb:
        return vacio

    try:
        res = sb.table("fenix_progreso").select("*").eq("bot_id", bot_id).limit(1).execute()
        filas = res.data or []

        if not filas:
            sb.table("fenix_progreso").insert(vacio).execute()
            return vacio

        fila = filas[0]
        if fila.get("fecha") != hoy:
            nuevo_nivel = min(NIVEL_MAXIMO, (fila.get("nivel") or 0) + 1)
            actualizado = {
                "nivel": nuevo_nivel,
                "fecha": hoy,
                "preguntas_hoy": 0,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            sb.table("fenix_progreso").update(actualizado).eq("bot_id", bot_id).execute()
            fila.update(actualizado)
        return fila
    except Exception as e:
        print(f"⚠️ Error leyendo progreso de '{bot_id}': {e}")
        return vacio


def registrar_pregunta(bot_id: str, tema: str, max_temas_recordados: int = 40):
    """Suma 1 al contador de preguntas del día y guarda el tema para que el
    generador no lo repita en próximas rondas."""
    if not sb:
        return
    try:
        progreso = obtener_progreso(bot_id)
        temas = (progreso.get("temas_recientes") or []) + [tema[:160]]
        temas = temas[-max_temas_recordados:]
        sb.table("fenix_progreso").update({
            "preguntas_hoy": (progreso.get("preguntas_hoy") or 0) + 1,
            "temas_recientes": temas,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("bot_id", bot_id).execute()
    except Exception as e:
        print(f"⚠️ Error registrando pregunta de '{bot_id}': {e}")
