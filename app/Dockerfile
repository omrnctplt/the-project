FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/srv

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY requirements.txt /srv/requirements.txt
RUN pip install -r /srv/requirements.txt

COPY . /srv/app/

RUN groupadd -r appuser \
    && useradd -r -g appuser -d /srv -s /sbin/nologin appuser \
    && mkdir -p /data /etc/onprem-ai \
    && chown -R appuser:appuser /data /srv /etc/onprem-ai

USER appuser

EXPOSE 7070

HEALTHCHECK --interval=15s --timeout=5s --start-period=25s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:7070/healthz', timeout=2).status==200 else 1)"

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7070", "--workers", "1", "--proxy-headers"]
