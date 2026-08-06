#!/bin/bash

# Sanal ortamı aktif et (Eğer yoksa hata verme)
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# API'yi başlat
if [ "$1" = "--background" ]; then
    echo "🚀 InvestGuide API arka planda başlatılıyor... (Loglar api.log dosyasına yazılıyor)"
    nohup uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4 > api.log 2>&1 &
    echo "✅ Başlatıldı. Durdurmak için: 'pkill uvicorn'"
else
    echo "🚀 InvestGuide API başlatılıyor (0.0.0.0:8000)..."
    exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
fi
