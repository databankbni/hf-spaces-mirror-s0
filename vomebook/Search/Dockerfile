FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY app.py build_fulltext_db.py prepare_fulltext_index.py start.sh ./

COPY static/ static/

COPY data/ data/

COPY CCRD/ CCRD/

COPY CW/ CW/

EXPOSE 7860

CMD ["sh", "/app/start.sh"]
