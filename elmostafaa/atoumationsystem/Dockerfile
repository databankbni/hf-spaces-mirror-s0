FROM node:20-slim

RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-venv \
    ffmpeg \
    fonts-arabeyes \
    fonts-hosny-amiri \
    wget curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deno.land/install.sh | sh && mv /root/.deno/bin/deno /usr/local/bin/deno || true

WORKDIR /app
COPY requirements.txt .
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /fonts && \
    wget -q "https://fonts.gstatic.com/s/amiri/v27/J7aRnpd8CGxBHqUpvrIw74NL.ttf" \
    -O /fonts/Amiri-Regular.ttf || true

RUN mkdir -p /audio /videos /images /fonts /data
COPY fonts/*.otf fonts/*.ttf /fonts/

COPY quran_app.py .
COPY start.sh /start.sh
RUN chmod +x /start.sh

RUN useradd -m -u 1001 appuser && \
    chown -R appuser:appuser /data /audio /videos /images /fonts /app
USER appuser

EXPOSE 7860

CMD ["/start.sh"]