FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY axora_v2/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
 && useradd -m -u 10001 -s /usr/sbin/nologin axora
RUN mkdir -p /app/services
COPY services/__init__.py services/importer.py services/profile.py /app/services/
COPY axora_v2 /app/axora_v2
USER axora
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=30s \
 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)"
CMD ["uvicorn", "axora_v2.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=127.0.0.1"]
