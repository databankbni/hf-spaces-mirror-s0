# -*- coding: utf-8 -*-
import gradio as gr

# Paleta Fénix: negro profundo + dorado, con el orbe como corazón visual del Oráculo
FENIX_CSS = """
:root {
    --fenix-negro: #0a0908;
    --fenix-negro-panel: #151210;
    --fenix-dorado: #d4af37;
    --fenix-dorado-claro: #f2cf6e;
    --fenix-dorado-brillo: rgba(212, 175, 55, 0.55);
}

/* --- Fondo general: negro con un leve resplandor dorado ambiental --- */
body, .gradio-container {
    background: radial-gradient(ellipse at 50% -10%, #241a08 0%, var(--fenix-negro) 55%) !important;
    color: var(--fenix-dorado-claro) !important;
    font-family: 'Georgia', 'Times New Roman', serif;
}

h1, h2, h3, h4 {
    color: var(--fenix-dorado) !important;
    text-shadow: 0 0 12px var(--fenix-dorado-brillo);
    letter-spacing: 0.5px;
}

/* Paneles / bloques de Gradio */
.gr-box, .gr-panel, .block, .form {
    background: var(--fenix-negro-panel) !important;
    border: 1px solid rgba(212, 175, 55, 0.35) !important;
}

/* Pestañas */
.tab-nav button {
    color: var(--fenix-dorado-claro) !important;
    background: transparent !important;
}
.tab-nav button.selected {
    color: var(--fenix-negro) !important;
    background: var(--fenix-dorado) !important;
    font-weight: bold;
    box-shadow: 0 0 14px var(--fenix-dorado-brillo);
}

/* Botones */
button, .gr-button {
    background: linear-gradient(180deg, #2a2214, #0f0d09) !important;
    color: var(--fenix-dorado) !important;
    border: 1px solid var(--fenix-dorado) !important;
    transition: box-shadow 0.25s ease, transform 0.15s ease;
}
button:hover, .gr-button:hover {
    box-shadow: 0 0 18px var(--fenix-dorado-brillo);
    transform: translateY(-1px);
}

/* Textboxes / Dropdowns */
textarea, input, select, .gr-input {
    background: var(--fenix-negro-panel) !important;
    color: var(--fenix-dorado-claro) !important;
    border: 1px solid rgba(212, 175, 55, 0.4) !important;
}

/* Chatbot: texto legible en negro/dorado.
   FIX LEGIBILIDAD: Gradio 6 cambió el marcado interno del Chatbot (ya no usa
   las clases .message.user/.message.bot de antes), así que en vez de apostar
   por nombres de clase exactos que pueden volver a cambiar, se fuerza el
   color y el fondo con selectores amplios por subcadena, que cazan cualquier
   variante ("message", "bubble", "chat", "panel", "bot-row", "user-row", etc.)
   y también el contenido ya renderizado como Markdown ("prose"). */
[class*="message"], [class*="bubble"], [class*="chat-row"], [class*="panel"],
[class*="bot-row"], [class*="user-row"], .prose, .prose * {
    color: var(--fenix-dorado-claro) !important;
    background-color: #100d0a !important;
}
/* Los enlaces dentro de una respuesta deben distinguirse del resto del texto */
.prose a {
    color: var(--fenix-dorado) !important;
    text-decoration: underline;
}
/* Bloques de código: fondo aún más oscuro para que no se confundan con el resto */
.prose pre, .prose code {
    background-color: #050403 !important;
    color: #f2cf6e !important;
}

footer {
    margin-top: 20px;
    text-align: center;
    font-size: 0.85em;
    color: var(--fenix-dorado);
    opacity: 0.7;
}

/* --- El Orbe de Fénix: cuerpo de energía negro y dorado --- */
.orbe-contenedor {
    position: relative;
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 24px 0 30px 0;
    height: 140px;
}

.orbe-luz {
    width: 90px;
    height: 90px;
    border-radius: 50%;
    background: radial-gradient(circle, #fff6da 0%, var(--fenix-dorado-claro) 30%, var(--fenix-dorado) 55%, rgba(10,9,8,0.9) 100%);
    box-shadow: 0 0 35px 16px var(--fenix-dorado-brillo);
    animation: latido_divino 3s infinite alternate ease-in-out;
    z-index: 2;
}

@keyframes latido_divino {
    0% {
        transform: scale(0.9);
        opacity: 0.75;
        box-shadow: 0 0 22px 10px rgba(212, 175, 55, 0.35);
    }
    100% {
        transform: scale(1.15);
        opacity: 1;
        box-shadow: 0 0 55px 26px rgba(242, 207, 110, 0.75);
    }
}

/* Estado "pensando": el orbe se acelera y arde más intenso mientras Fénix responde */
.orbe-luz.orbe-pensando {
    animation: latido_pensando 0.7s infinite alternate ease-in-out !important;
}
@keyframes latido_pensando {
    0% {
        transform: scale(1);
        opacity: 0.9;
        box-shadow: 0 0 30px 14px rgba(212, 175, 55, 0.65);
    }
    100% {
        transform: scale(1.35);
        opacity: 1;
        box-shadow: 0 0 80px 40px rgba(255, 221, 130, 0.95);
    }
}

/* Estado "hablando": el volumen REAL de la voz controla el orbe por JS
   (transform/box-shadow inline), así que aquí se apaga la animación CSS
   para que no compita con esos valores frame a frame. */
.orbe-luz.orbe-hablando {
    animation: none !important;
}

/* Brasas ascendiendo alrededor del orbe */
.brasa {
    position: absolute;
    bottom: 30px;
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: var(--fenix-dorado-claro);
    box-shadow: 0 0 8px 3px var(--fenix-dorado-brillo);
    opacity: 0;
    animation: ascender 3.2s infinite ease-in;
}
.brasa:nth-child(1) { left: 42%; animation-delay: 0s; }
.brasa:nth-child(2) { left: 50%; animation-delay: 1.1s; }
.brasa:nth-child(3) { left: 58%; animation-delay: 2.1s; }
.brasa:nth-child(4) { left: 46%; animation-delay: 1.6s; }

@keyframes ascender {
    0%   { transform: translateY(0) scale(1);   opacity: 0; }
    15%  { opacity: 1; }
    100% { transform: translateY(-110px) scale(0.3); opacity: 0; }
}

/* Letras hebreas de TESHUÁ (Tav · Shin · Vav · Ayin · He) flotando junto al orbe */
.letra-hebrea {
    position: absolute;
    bottom: 25px;
    font-size: 24px;
    color: var(--fenix-dorado-claro);
    text-shadow: 0 0 10px var(--fenix-dorado-brillo);
    opacity: 0;
    animation: flotar_hebreo 5.5s infinite ease-in;
    font-family: 'Times New Roman', serif;
}
.letra-1 { left: 12%; animation-delay: 0s; }
.letra-2 { left: 82%; animation-delay: 1.1s; }
.letra-3 { left: 25%; animation-delay: 2.3s; }
.letra-4 { left: 70%; animation-delay: 3.4s; }
.letra-5 { left: 48%; animation-delay: 4.4s; }

@keyframes flotar_hebreo {
    0%   { transform: translateY(0) rotate(0deg);   opacity: 0; }
    12%  { opacity: 0.9; }
    100% { transform: translateY(-140px) rotate(18deg); opacity: 0; }
}
"""

def apply_fenix_theme():
    """
    Returns a Gradio theme object in black-and-gold tones, as the base
    underneath the FENIX_CSS overrides above.
    """
    return gr.themes.Soft(primary_hue="amber", neutral_hue="zinc")

def fenix_header(title: str, description: str):
    """
    Inserts a header at the top of the interface.
    """
    with gr.Row():
        gr.Markdown(f"# {title}")
        gr.Markdown(f"{description}")

def fenix_footer():
    """
    Inserts a footer at the bottom of the interface.
    """
    with gr.Row():
        gr.Markdown("© 2026 Fenix TESHUÁ. Todos los derechos reservados.")