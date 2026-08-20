FROM denoland/deno:bin-2.4.5 AS deno
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates curl && rm -rf /var/lib/apt/lists/*
COPY --from=deno /deno /usr/local/bin/deno
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN mkdir -p /data/downloads && useradd --create-home --uid 10001 downloadix && chown -R downloadix:downloadix /data /app
USER downloadix
ENV PYTHONUNBUFFERED=1 DOWNLOAD_DIR=/data/downloads PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers"]
