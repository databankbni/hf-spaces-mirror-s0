FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .
COPY deploy ./deploy
COPY models ./models
COPY calculator/predict_meta.json ./calculator/predict_meta.json
ENV PORT=7860
EXPOSE 7860
CMD ["python", "server.py"]
