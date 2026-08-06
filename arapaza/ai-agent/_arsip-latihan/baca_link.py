import requests
from bs4 import BeautifulSoup

# Link yang mau dibaca (nanti ini dari input kamu)
url = "https://timbanganindonesia.com/product/orion-series/"

# Buka halaman web-nya
# headers ini biar website gak ngira kita robot & nolak
headers = {"User-Agent": "Mozilla/5.0"}
halaman = requests.get(url, headers=headers, timeout=20)

# Rapiin HTML jadi teks
sup = BeautifulSoup(halaman.text, "html.parser")

# Ambil teksnya aja, buang kode-kode web
teks = sup.get_text(separator=" ", strip=True)

# Tampilin 1000 huruf pertama biar gak kepanjangan
print(teks[:1000])