from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import io
import sys
import contextlib

app = FastAPI()

# Allow your other website to talk to this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/run")
async def run_code(request: Request):
    data = await request.json()
    code = data.get("code", "")
    input_data = data.get("input", "")
    
    # Fast in-memory buffer
    output = io.StringIO()
    sys.stdin = io.StringIO(input_data)
    
    try:
        with contextlib.redirect_stdout(output):
            exec(code)
        result = output.getvalue()
    except Exception as e:
        result = f"Error: {str(e)}"
        
    return {"output": result}
