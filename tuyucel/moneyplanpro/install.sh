#!/bin/bash

# AlmaLinux / RHEL / CentOS Install Script for InvestGuide Backend
echo "🚀 InvestGuide Backend kurulumu başlıyor (AlmaLinux)..."

# Sistem güncel mi ve gerekli temel araçlar var mı?
sudo dnf update -y
sudo dnf install -y python39 python39-devel python3-pip gcc tar zip

# Python venv oluştur
echo "📦 Sanal ortam oluşturuluyor..."
python3.9 -m venv venv
source venv/bin/activate

# Bağımlılıkları yükle
echo "📥 Python paketleri yükleniyor..."
pip install --upgrade pip
pip install -r requirements.txt

# İzinleri ayarla
chmod +x start.sh

echo "------------------------------------------------"
echo "✅ Kurulum tamamlandı!"
echo "▶️  Başlatmak için: ./start.sh"
echo "------------------------------------------------"
