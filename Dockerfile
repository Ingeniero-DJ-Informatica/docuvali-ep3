# Imagen de la API y del worker de DocuVali (misma imagen, distinto comando)
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
# Tesseract: OCR local para leer imágenes sin AWS (EXTRACTOR=local)
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-spa \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

COPY app/ app/
COPY model/__init__.py model/inference.py model/
COPY model/artifacts/model.json model/artifacts/metrics.json model/artifacts/

# Usuario sin privilegios (buena práctica de seguridad)
RUN useradd --uid 1000 --create-home docuvali && mkdir -p /data/uploads && chown -R docuvali /data
USER docuvali
ENV MODEL_JSON=/srv/model/artifacts/model.json DATA_DIR=/data
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)" || exit 1
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
