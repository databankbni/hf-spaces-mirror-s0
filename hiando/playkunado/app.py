from fastapi import FastAPI
from fastapi.responses import FileResponse
import threading
import time
import subprocess
import os

app = FastAPI()

PLAYLIST_FILE = "playlist.m3u"
LOG_FILE = "cron.log"


def generate_playlist():
    while True:
        try:
            with open(LOG_FILE, "a") as f:
                f.write("Generate playlist: " + time.ctime() + "\n")

            # jalankan script generator
            subprocess.run(["python", "generate_playlist.py"])

        except Exception as e:
            with open(LOG_FILE, "a") as f:
                f.write("Error: " + str(e) + "\n")

        time.sleep(1200)  # 20 menit


@app.on_event("startup")
def startup_event():
    thread = threading.Thread(target=generate_playlist)
    thread.daemon = True
    thread.start()


@app.get("/")
def root():
    return {"status": "running"}


@app.get("/playlist.m3u")
def playlist():
    if os.path.exists(PLAYLIST_FILE):
        return FileResponse(PLAYLIST_FILE)
    return {"error": "playlist not found"}


@app.get("/cronlog")
def cronlog():
    if os.path.exists(LOG_FILE):
        return FileResponse(LOG_FILE)
    return {"log": "empty"}