"""
Voice Chess Pro - HF Space
Author : Ahmed Darwish
HF : @engdarwish

Gradio web interface for Voice Chess Pro.
Runs on Hugging Face Spaces.

Features:
- Play vs Stockfish AI (3 difficulty levels)
- Player vs Player (two players, one browser)
- Interactive SVG board (click + text moves)
- Voice move input (speak your move, e.g. "e2 to e4")
- Move history
- Undo / Reset
- PGN export

Fix log (this pass):
- Game state is per-session (gr.State), not a shared global.
- Stockfish is provisioned via packages.txt so the AI opponent
  actually runs on Spaces.
- Added real voice input: browser microphone -> Google Speech
  Recognition (SpeechRecognition/recognize_google, same engine
  as the original desktop version) -> shared move pipeline.
  Voice degrades gracefully (falls back to text-only) if the
  SpeechRecognition package isn't installed on the server.
"""

import chess
import chess.svg
import chess.engine
import gradio as gr
import os

# -------------------------------------------------
# OPTIONAL VOICE SUPPORT
# -------------------------------------------------
# Mirrors the STOCKFISH_PATH pattern below: if the optional
# dependency isn't present, the app degrades gracefully instead
# of crashing - voice input is simply hidden.
try:
    import speech_recognition as sr
    VOICE_AVAILABLE = True
except Exception:
    sr = None
    VOICE_AVAILABLE = False

_recognizer = sr.Recognizer() if VOICE_AVAILABLE else None

# -------------------------------------------------
# STOCKFISH SETUP
# -------------------------------------------------
_SF_PATHS = [
    "/usr/games/stockfish",
    "/usr/bin/stockfish",
    "/usr/local/bin/stockfish",
]


def _find_stockfish():
    for p in _SF_PATHS:
        if os.path.isfile(p):
            return p
    return None


STOCKFISH_PATH = _find_stockfish()

DIFFICULTY = {
    "Easy": {"time": 0.05, "depth": 4},
    "Medium": {"time": 0.20, "depth": 10},
    "Hard": {"time": 1.00, "depth": 18},
}

# -------------------------------------------------
# BOARD RENDERING
# -------------------------------------------------
def render_board(
    board: chess.Board,
    selected_sq=None,
    valid_squares=None,
    last_move: chess.Move = None,
    flipped: bool = False,
    size: int = 420,
) -> str:
    arrows = []
    fill = {}

    if last_move:
        arrows.append(chess.svg.Arrow(
            last_move.from_square, last_move.to_square,
            color="rgba(255,200,50,0.55)"
        ))

    if selected_sq is not None:
        fill[selected_sq] = "rgba(80,160,255,0.55)"

    for sq in (valid_squares or []):
        fill[sq] = "rgba(80,200,80,0.45)"

    if board.is_check():
        ks = board.king(board.turn)
        if ks is not None:
            fill[ks] = "rgba(220,50,50,0.60)"

    svg = chess.svg.board(
        board,
        arrows=arrows,
        fill=fill,
        flipped=flipped,
        size=size,
        coordinates=True,
    )
    return svg


def board_to_html(svg: str) -> str:
    return f"""
<div style="display:flex;justify-content:center;align-items:center;
background:#16161e;padding:10px;border-radius:10px;">
{svg}
</div>"""


# -------------------------------------------------
# MOVE PARSER
# -------------------------------------------------
def parse_move(text: str, board: chess.Board):
    """Try to parse a move string (UCI or SAN). Returns chess.Move or None."""
    text = text.strip().replace(" to ", "").replace("-", "").replace(" ", "")
    try:
        m = chess.Move.from_uci(text.lower())
        if m in board.legal_moves:
            return m
    except Exception:
        pass
    try:
        m = board.parse_san(text)
        if m in board.legal_moves:
            return m
    except Exception:
        pass
    return None


# -------------------------------------------------
# VOICE TRANSCRIPTION
# -------------------------------------------------
def transcribe_audio(audio_path: str):
    """
    Transcribe a recorded audio file to text using Google's free
    Speech Recognition API (same engine as the original desktop
    Voice Chess Pro). Returns (text_or_None, error_message_or_None).
    """
    if not VOICE_AVAILABLE:
        return None, "Voice input isn't available on this server (SpeechRecognition not installed)."
    if not audio_path:
        return None, "No audio recorded. Please try again."

    try:
        with sr.AudioFile(audio_path) as source:
            audio = _recognizer.record(source)
        text = _recognizer.recognize_google(audio)
        return text, None
    except sr.UnknownValueError:
        return None, "Sorry, I couldn't understand that. Please try again or type your move."
    except sr.RequestError:
        return None, "Speech recognition service is unavailable right now. Please type your move."
    except Exception as e:
        return None, f"Voice recognition error: {e}"


# -------------------------------------------------
# MOVE HISTORY FORMATTER
# -------------------------------------------------
def format_history(history: list) -> str:
    if not history:
        return "*No moves yet*"
    lines = []
    i = 0
    while i < len(history):
        n = i // 2 + 1
        w = history[i]["san"]
        b = history[i + 1]["san"] if i + 1 < len(history) else "..."
        lines.append(f"**{n}.** {w} {b}")
        i += 2
    return "\n".join(lines[-15:])  # show last 15 moves


# -------------------------------------------------
# GAME STATE - one instance per browser session
# (held in gr.State, NOT a module-level global)
# -------------------------------------------------
class GameState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.board = chess.Board()
        self.history: list = []
        self.mode: str = "pvai"  # 'pvp' | 'pvai'
        self.difficulty: str = "Medium"
        self.flipped: bool = False
        self.selected_sq = None
        self.valid_sqs: list = []
        self.status_msg: str = ""
        self.game_over: bool = False

    def push(self, move: chess.Move):
        san = self.board.san(move)
        col = "W" if self.board.turn == chess.WHITE else "B"
        self.board.push(move)
        self.history.append({"move": move, "san": san, "color": col})

    def undo(self):
        if not self.history:
            return False
        self.board.pop()
        self.history.pop()
        if self.mode == "pvai" and self.history:
            self.board.pop()
            self.history.pop()
        return True

    def check_game_over(self):
        b = self.board
        if b.is_checkmate():
            w = "Black" if b.turn == chess.WHITE else "White"
            return f"Checkmate - {w} Wins!"
        if b.is_stalemate():
            return "Stalemate - Draw"
        if b.is_insufficient_material():
            return "Draw (Insufficient Material)"
        if b.is_fifty_moves():
            return "Draw (50-Move Rule)"
        if b.is_repetition(3):
            return "Draw (3-Fold Repetition)"
        return None

    def get_stockfish_move(self):
        if not STOCKFISH_PATH:
            return None
        try:
            cfg = DIFFICULTY[self.difficulty]
            with chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH) as sf:
                result = sf.play(self.board, chess.engine.Limit(
                    time=cfg["time"], depth=cfg["depth"]
                ))
            return result.move
        except Exception as e:
            print(f"[Stockfish error] {e}")
            return None


def _refresh(gs: GameState):
    svg = render_board(
        gs.board,
        last_move=gs.board.peek() if gs.board.move_stack else None,
        selected_sq=gs.selected_sq,
        valid_squares=gs.valid_sqs,
        flipped=gs.flipped,
    )
    html = board_to_html(svg)
    hist = format_history(gs.history)
    stat = gs.status_msg
    return html, hist, stat


def _apply_move_text(move_text: str, gs: GameState, heard_prefix: str = ""):
    """
    Shared move-application pipeline used by BOTH the text input and
    the voice input, so parsing/AI-reply/game-over logic lives in one
    place only.
    """
    if gs.game_over:
        return _refresh(gs)
    if not move_text or not move_text.strip():
        return _refresh(gs)

    move = parse_move(move_text, gs.board)
    if not move:
        gs.status_msg = f"{heard_prefix}Invalid move: '{move_text}'. Try e.g. **e2e4** or **Nf3**"
        if not STOCKFISH_PATH and gs.mode == "pvai":
            gs.status_msg += " \nStockfish engine not found on this server - AI moves are disabled."
        return _refresh(gs)

    gs.push(move)
    gs.selected_sq = None
    gs.valid_sqs = []

    end = gs.check_game_over()
    if end:
        gs.game_over = True
        gs.status_msg = f"{heard_prefix}{end}"
        return _refresh(gs)

    if gs.mode == "pvai" and gs.board.turn == chess.BLACK:
        if not STOCKFISH_PATH:
            gs.status_msg = f"{heard_prefix}Stockfish engine not available on this server right now."
        else:
            ai_move = gs.get_stockfish_move()
            if ai_move:
                gs.push(ai_move)
                end = gs.check_game_over()
                if end:
                    gs.game_over = True
                    gs.status_msg = f"{heard_prefix}{end}"
                else:
                    turn = "White" if gs.board.turn == chess.WHITE else "Black"
                    gs.status_msg = f"{heard_prefix}{turn} to move"
            else:
                gs.status_msg = f"{heard_prefix}AI could not find a move - engine unavailable."
    else:
        turn = "White" if gs.board.turn == chess.WHITE else "Black"
        chk = " CHECK!" if gs.board.is_check() else ""
        gs.status_msg = f"{heard_prefix}{turn} to move{chk}"

    return _refresh(gs)


def fn_move(move_text: str, gs: GameState):
    """Handle a text move input."""
    result = _apply_move_text(move_text, gs)
    return *result, "", gs


def fn_voice(audio_path: str, gs: GameState):
    """Handle a recorded voice move: transcribe, then reuse the shared pipeline."""
    text, err = transcribe_audio(audio_path)
    if err:
        gs.status_msg = err
        return *_refresh(gs), None, gs

    result = _apply_move_text(text, gs, heard_prefix=f"🎤 Heard: \"{text}\" — ")
    return *result, None, gs


def fn_undo(gs: GameState):
    ok = gs.undo()
    gs.game_over = False
    gs.status_msg = "Move undone." if ok else "Nothing to undo."
    return *_refresh(gs), gs


def fn_reset(gs: GameState):
    gs.reset()
    gs.status_msg = "Board reset. Select mode and start!"
    return *_refresh(gs), gs


def fn_set_mode(mode_label: str, gs: GameState):
    gs.mode = "pvp" if "Player vs Player" in mode_label else "pvai"
    gs.status_msg = f"Mode: **{mode_label}**"
    return *_refresh(gs), gs


def fn_set_difficulty(diff: str, gs: GameState):
    gs.difficulty = diff
    gs.status_msg = f"Difficulty: **{diff}**"
    return *_refresh(gs), gs


def fn_flip(gs: GameState):
    gs.flipped = not gs.flipped
    return *_refresh(gs), gs


def fn_pgn(gs: GameState):
    import chess.pgn
    from datetime import datetime
    game = chess.pgn.Game.from_board(gs.board)
    game.headers["Event"] = "Voice Chess Pro"
    game.headers["Site"] = "Hugging Face Space"
    game.headers["Date"] = datetime.now().strftime("%Y.%m.%d")
    game.headers["White"] = "Player 1"
    game.headers["Black"] = "Player 2" if gs.mode == "pvp" else "Stockfish"
    exporter = chess.pgn.StringExporter()
    return game.accept(exporter)


# -------------------------------------------------
# GRADIO UI
# -------------------------------------------------
CSS = """
#board-html { background: transparent !important; }
.gr-button { font-size: 14px !important; }
footer { display: none !important; }
"""

with gr.Blocks(
    title="Voice Chess Pro - Ahmed Darwish",
    theme=gr.themes.Base(
        primary_hue="blue",
        neutral_hue="slate",
    ),
    css=CSS,
) as demo:

    game_state = gr.State(value=None)  # created fresh per browser session on load

    gr.HTML("""
    <div style="text-align:center; padding:16px 0 8px 0;">
        <h1 style="color:#FFB347; font-size:28px; margin:0;">
            Voice Chess Pro
        </h1>
        <p style="color:#888; font-size:13px; margin:4px 0 0 0;">
            by <strong>Ahmed Darwish</strong> &nbsp;|&nbsp; @engdarwish
        </p>
    </div>
    """)

    if not STOCKFISH_PATH:
        gr.HTML("""
        <div style="text-align:center; color:#e0a030; font-size:12px; padding:0 0 8px 0;">
            Stockfish engine not detected on this server - Player vs AI moves will be disabled
            until the space rebuilds with packages.txt.
        </div>
        """)

    with gr.Row():
        with gr.Column(scale=3):
            board_html = gr.HTML(elem_id="board-html")
            status_md = gr.Markdown("White to move - Enter a move below.")

            with gr.Row():
                move_input = gr.Textbox(
                    placeholder="e.g. e2e4 or Nf3 or e2 to e4",
                    label="Your Move",
                    scale=4,
                    show_label=True,
                )
                move_btn = gr.Button("Move", variant="primary", scale=1)

            if VOICE_AVAILABLE:
                voice_input = gr.Audio(
                    sources=["microphone"],
                    type="filepath",
                    format="wav",
                    label="🎤 Or speak your move (e.g. \"e2 to e4\") — stops listening automatically",
                )
            else:
                gr.HTML("""
                <div style="text-align:center; color:#888; font-size:11px; padding:4px 0;">
                    🎤 Voice input unavailable on this server — use text moves above.
                </div>
                """)

            with gr.Row():
                undo_btn = gr.Button("Undo", scale=1)
                reset_btn = gr.Button("Reset", scale=1)
                flip_btn = gr.Button("Flip Board", scale=1)

        with gr.Column(scale=1):
            gr.Markdown("### Game Settings")

            mode_radio = gr.Radio(
                choices=["Player vs Player", "Player vs Computer (Stockfish)"],
                value="Player vs Computer (Stockfish)",
                label="Game Mode",
            )
            diff_radio = gr.Radio(
                choices=["Easy", "Medium", "Hard"],
                value="Medium",
                label="AI Difficulty",
                visible=True,
            )

            gr.Markdown("### Move History")
            history_md = gr.Markdown("*No moves yet*")

            gr.Markdown("### Export")
            pgn_btn = gr.Button("Get PGN")
            pgn_text = gr.Textbox(label="PGN", lines=6, interactive=False)

    out = [board_html, history_md, status_md]

    def _init_session():
        gs = GameState()
        gs.status_msg = "White to move - Enter a move below."
        html, hist, stat = _refresh(gs)
        return html, hist, stat, gs

    demo.load(_init_session, outputs=[*out, game_state])

    move_btn.click(fn_move, inputs=[move_input, game_state], outputs=[*out, move_input, game_state])
    move_input.submit(fn_move, inputs=[move_input, game_state], outputs=[*out, move_input, game_state])

    if VOICE_AVAILABLE:
        voice_input.stop_recording(
            fn_voice, inputs=[voice_input, game_state], outputs=[*out, voice_input, game_state]
        )

    undo_btn.click(fn_undo, inputs=game_state, outputs=[*out, game_state])
    reset_btn.click(fn_reset, inputs=game_state, outputs=[*out, game_state])
    flip_btn.click(fn_flip, inputs=game_state, outputs=[*out, game_state])

    mode_radio.change(fn_set_mode, inputs=[mode_radio, game_state], outputs=[*out, game_state])
    diff_radio.change(fn_set_difficulty, inputs=[diff_radio, game_state], outputs=[*out, game_state])
    pgn_btn.click(fn_pgn, inputs=game_state, outputs=pgn_text)

    gr.HTML("""
    <div style="text-align:center; color:#555; font-size:12px; padding:12px 0 0 0;">
        Built with python-chess + Gradio &nbsp;|&nbsp;
        Stockfish engine &nbsp;|&nbsp; Google Speech Recognition &nbsp;|&nbsp;
        <a href="https://github.com/eahmeddarwish"
           style="color:#FFB347;">GitHub</a>
    </div>
    """)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
