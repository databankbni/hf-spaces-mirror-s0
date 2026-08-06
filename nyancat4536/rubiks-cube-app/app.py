from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import kociemba

app = FastAPI()

class CubeState(BaseModel):
    state: str

@app.post("/solve")
def solve_cube(cube: CubeState):
    try:
        # Kociemba requires exactly the 54 length string (UBL...) to optimally solve it
        solution = kociemba.solve(cube.state)
        return {"solution": solution}
    except Exception as e:
        return {"error": "Invalid cube! Check colors or twisted corners."}

@app.get("/")
def read_root():
    with open("index.html", "r") as f:
        return HTMLResponse(content=f.read(), status_code=200)