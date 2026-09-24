FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 OMP_THREAD_LIMIT=2 LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-fra libreoffice-calc fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY cmf cmf
COPY config config
COPY tests tests
RUN useradd --create-home --uid 10001 cmf && mkdir /output && chown cmf:cmf /output
USER cmf
ENV CMF_ROOT=/data CMF_OUTPUT=/output CMF_CONFIG=/app/config/star.json
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)"
CMD ["python", "-m", "uvicorn", "cmf.api:app", "--host", "0.0.0.0", "--port", "8000"]
