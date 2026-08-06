"""
Sala AI - FastAPI Entrypoint
"""
import logging
from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from chatbot.routes import router as chatbot_router
from dashboard.routes import router as dashboard_router
from chatbot.rag import load_product_db, load_wiki_db, restore_wiki_db_from_backup
from chatbot.auth import verify_admin, verify_demo_user
from db.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("SalaAI")

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting Sala AI - initializing analytics database...")
    init_db()
    log.info("Loading product vector DB...")
    load_product_db()
    log.info("Restoring wiki vector DB from backup (if configured)...")
    restore_wiki_db_from_backup()
    log.info("Loading wiki vector DB...")
    load_wiki_db()
    log.info("Sala AI ready.")
    yield
    log.info("Shutting down Sala AI.")

app = FastAPI(title="Sala AI", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this to sala.lk domain in production
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(chatbot_router)
app.include_router(dashboard_router)

# Serve static files (widget JS, images, etc.) from dashboard/static
app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")

@app.get("/")
async def root():
    return {"status": "Sala AI running"}

@app.get("/admin")
async def admin_page(username: str = Depends(verify_admin)):
    return FileResponse("dashboard/static/admin.html")

@app.get("/demo")
async def demo_page(username: str = Depends(verify_demo_user)):
    return FileResponse("dashboard/static/demo.html") # rebuild trigger