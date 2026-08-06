# References:

# https://www.stockfish.online/docs.php (API)
# https://www.stockfish.online/ (FEN to image)

import re
import gradio as gr
import gradio.utils, requests
from typing import Optional, List, Dict, Any

# MCP server functions

def position_evaluation(fen):
    """Chess position evaluation. Get best move with continuation in UCI notation for chess position in FEN.

    Args:
        fen (str): Chess position in FEN
        
    Returns:
        tuple: (result, error) - Best move with continuation in UCI notation
    """
    is_valid = validate_input(fen)
    
    if not is_valid:
        msg = f"Invalid input"
        gr.Warning(msg)
        return None, msg
    
    print("")
    
    print(f"🤖 Chess position_evaluation: fen={fen}")
    
    url = "https://stockfish.online/api/s/v2.php"
    params = {"fen": fen, "depth": 12}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        result = response.json()
        
        print(f"🤖 Chess position_evaluation: result={result}")
        
        return result, None
    
    except requests.exceptions.RequestException as e:
        return None, str(e)

# Helper functions

def _noop(*args, **kwargs):
    pass

gradio.utils.watchfn_spaces = _noop

def validate_input(fen):
    fen_pattern = r'\b([rnbqkpRNBQKP1-8\/]+\s+[wb]\s+(?:-|[KQkq]+)\s+(?:-|[a-h][36])\s+\d+\s+\d+)\b'

    return re.search(fen_pattern, fen)

# Graphical user interface

mcp = gr.Interface(
    fn=position_evaluation,
    inputs =  [gr.Textbox(label = "Forsyth-Edwards Notation (FEN)", value = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", max_length = 75)],
    outputs = [gr.Textbox(label = "Evaluation", interactive = False)],
    title="Stockfish Chess Engine",
    description="Chess position evaluation by top open source chess engine"
)

mcp.launch(mcp_server=True, ssr_mode=False)