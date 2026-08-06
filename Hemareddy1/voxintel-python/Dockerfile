# python_services/Dockerfile
#
# Built for Hugging Face Spaces' Docker SDK (free CPU Spaces get 16GB RAM —
# this service needs real memory for spaCy + torch + sentence-transformers
# loaded together, which a 512MB free web-service tier elsewhere can't give
# it without crash-looping on out-of-memory kills).
#
# HF Spaces conventions this follows:
#   - listens on port 7860 (HF's fixed default, set via EXPOSE + gunicorn --bind)
#   - runs as a non-root "user" (uid 1000) with a writable $HOME, because
#     sentence-transformers and NLTK both download model weights/data into
#     the home directory's cache on first use, and HF's runtime doesn't
#     grant write access outside $HOME to non-root processes.
FROM python:3.12-slim

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR /home/user/app

COPY --chown=user . .

# Same spaCy-model workaround used for the Render deploy: `spacy download`
# can resolve a malformed release URL for some spacy versions, so install
# the matching en_core_web_sm wheel directly instead.
RUN pip install --no-cache-dir --user -r requirements.txt \
    && pip install --no-cache-dir --user https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl \
    && python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords'); nltk.download('averaged_perceptron_tagger')"

EXPOSE 7860

CMD ["gunicorn", "--bind", "0.0.0.0:7860", "--timeout", "120", "app:app"]
