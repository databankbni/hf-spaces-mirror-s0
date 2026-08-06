from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

makaslar = {
    "depoa1": False
}

class MakasDurum(BaseModel):
    durum: bool

@app.get("/makas/{makas_id}")
def durum_getir(makas_id: str):
    return {"durum": makaslar.get(makas_id, False)}

@app.post("/makas/{makas_id}")
def durum_guncelle(makas_id: str, veri: MakasDurum):
    makaslar[makas_id] = veri.durum
    return {"status": "success", "yeni_durum": veri.durum}

@app.get("/", response_class=HTMLResponse)
def ana_sayfa():
    return """
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Sinyalizasyon Makas Masası</title>
        <style>
            body {
                background-color: #16161a;
                color: #ffffff;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                margin: 0;
                padding: 30px;
            }
            h1 {
                font-size: 20px;
                text-transform: uppercase;
                letter-spacing: 2px;
                margin-bottom: 25px;
                color: #a0aec0;
                border-bottom: 2px solid #2d2d34;
                padding-bottom: 10px;
            }
            .switch-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                gap: 25px;
            }
            .switch-card {
                background-color: #000000;
                border: 3px solid #000000;
                border-radius: 35px;
                width: 260px;
                height: 220px;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                align-items: center;
                padding: 20px 15px;
                box-sizing: border-box;
                box-shadow: 0 10px 20px rgba(0,0,0,0.5);
                transition: opacity 0.2s ease;
            }
            .switch-card.locked {
                opacity: 0.6;
                cursor: not-allowed;
            }
            .switch-header {
                font-size: 16px;
                font-weight: bold;
                text-transform: uppercase;
                letter-spacing: 1.5px;
                text-align: center;
                width: 100%;
                padding-bottom: 8px;
                border-bottom: 2px solid #16161a;
            }
            .track-schematic {
                width: 100%;
                height: 100px;
                position: relative;
                cursor: pointer;
            }
            .track {
                position: absolute;
                background-color: #2d2d34;
                height: 6px;
                border-radius: 3px;
                transition: all 0.25s ease;
            }
            .track-input { left: 10px; top: 35px; width: 90px; }
            .track-straight { left: 100px; top: 35px; width: 130px; }
            .track-divergent {
                left: 100px;
                top: 35px;
                width: 80px;
                transform-origin: left center;
                transform: rotate(35deg);
            }
            .switch-blade {
                position: absolute;
                left: 100px;
                top: 35px;
                width: 45px;
                height: 6px;
                background-color: #ffffff;
                border-radius: 3px;
                transform-origin: left center;
                transition: transform 0.2s ease, background-color 0.2s;
                z-index: 5;
                box-shadow: 0 0 8px #ffffff;
            }
            .state-straight .track-input,
            .state-straight .track-straight {
                background-color: #00ff22;
                box-shadow: 0 0 10px rgba(0, 255, 34, 0.7);
            }
            .state-straight .switch-blade {
                transform: rotate(0deg);
                background-color: #00ff22;
                box-shadow: 0 0 10px #00ff22;
            }
            .state-divergent .track-input,
            .state-divergent .track-divergent {
                background-color: #ff7f00;
                box-shadow: 0 0 10px #ff0000;
            }
            .state-divergent .switch-blade {
                transform: rotate(35deg);
                background-color: #ff7f00;
                box-shadow: 0 0 10px #ff0000;
            }
        </style>
    </head>
    <body>
        <h1>ATS Sinyalizasyon & Makas Kontrol Masası</h1>
        <div class="switch-grid">
            <div class="switch-card state-straight" id="panel-depoa1" onclick="toggleSwitch('depoa1')">
                <div class="switch-header">DEPO A1</div>
                <div class="track-schematic">
                    <div class="track track-input"></div>
                    <div class="switch-blade"></div>
                    <div class="track track-straight"></div>
                    <div class="track track-divergent"></div>
                </div>
            </div>
        </div>

        <script>
            let isLocked = false;
            const currentUrl = window.location.origin;

            function toggleSwitch(switchId) {
                if (isLocked) return;

                const card = document.getElementById('panel-' + switchId);
                isLocked = true;
                card.classList.add('locked');
                
                let yeniDurum = false;
                if (card.classList.contains('state-straight')) {
                    card.classList.remove('state-straight');
                    card.classList.add('state-divergent');
                    yeniDurum = true;
                } else {
                    card.classList.remove('state-divergent');
                    card.classList.add('state-straight');
                    yeniDurum = false;
                }

                fetch(`${currentUrl}/makas/${switchId}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ durum: yeniDurum })
                }).catch(err => console.error("Hata:", err));

                setTimeout(function() {
                    isLocked = false;
                    card.classList.remove('locked');
                }, 1000);
            }
        </script>
    </body>
    </html>
    """