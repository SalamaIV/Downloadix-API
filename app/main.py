from __future__ import annotations

import hmac
import os
import re
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

import yt_dlp
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .security import UnsafeUrlError, validate_public_url

DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", "/data/downloads")).resolve()
FILE_TTL_SECONDS = int(os.getenv("FILE_TTL_SECONDS", "3600"))
MAX_CONCURRENT_DOWNLOADS = max(1, int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "2")))
MAX_FILE_SIZE_MB = max(25, int(os.getenv("MAX_FILE_SIZE_MB", "500")))
API_KEY = os.getenv("DOWNLOADIX_API_KEY", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
ALLOWED_ORIGINS = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",") if origin.strip()]

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DOWNLOADS, thread_name_prefix="downloadix")
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()


class DownloadRequest(BaseModel):
    url: str = Field(min_length=10, max_length=4096)
    kind: Literal["video", "audio"] = "video"
    quality: str = Field(default="Best", max_length=30)
    format: str = Field(default="MP4", max_length=10)


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if API_KEY and (not x_api_key or not hmac.compare_digest(x_api_key, API_KEY)):
        raise HTTPException(status_code=401, detail="Invalid API key.")


def update_job(job_id: str, **values: object) -> None:
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(values)


def video_height(quality: str) -> int | None:
    match = re.search(r"(\d{3,4})", quality)
    return int(match.group(1)) if match else None


def build_options(job_id: str, payload: DownloadRequest) -> dict:
    target = DOWNLOAD_DIR / job_id
    target.mkdir(parents=True, exist_ok=True)
    output = str(target / "%(title).140B-%(id)s.%(ext)s")
    base: dict = {
        "outtmpl": output,
        "noplaylist": True,
        "restrictfilenames": True,
        "max_filesize": MAX_FILE_SIZE_MB * 1024 * 1024,
        "socket_timeout": 20,
        "retries": 3,
        "fragment_retries": 3,
        "progress_hooks": [lambda data: progress_hook(job_id, data)],
        "quiet": True,
        "no_warnings": True,
    }
    if payload.kind == "audio":
        codec = payload.format.lower() if payload.format.lower() in {"mp3", "m4a", "wav"} else "mp3"
        base.update({"format": "bestaudio/best", "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": codec, "preferredquality": "320"}]})
    else:
        height = video_height(payload.quality)
        base["format"] = f"bv*[height<={height}]+ba/b[height<={height}]" if height else "bv*+ba/b"
        base["merge_output_format"] = payload.format.lower() if payload.format.lower() in {"mp4", "mkv", "webm"} else "mp4"
    return base


def progress_hook(job_id: str, data: dict) -> None:
    if data.get("status") != "downloading":
        return
    total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
    downloaded = data.get("downloaded_bytes") or 0
    progress = round(downloaded * 100 / total, 1) if total else 0
    update_job(job_id, progress=progress, speed=data.get("speed"), eta=data.get("eta"))


def run_download(job_id: str, payload: DownloadRequest) -> None:
    update_job(job_id, status="downloading", startedAt=time.time())
    try:
        with yt_dlp.YoutubeDL(build_options(job_id, payload)) as downloader:
            downloader.download([payload.url])
        files = [path for path in (DOWNLOAD_DIR / job_id).iterdir() if path.is_file() and not path.name.endswith(('.part', '.ytdl'))]
        if not files:
            raise RuntimeError("The download finished without an output file.")
        output = max(files, key=lambda path: path.stat().st_mtime)
        update_job(job_id, status="ready", progress=100, filename=output.name, path=str(output), completedAt=time.time())
    except Exception as error:
        shutil.rmtree(DOWNLOAD_DIR / job_id, ignore_errors=True)
        update_job(job_id, status="failed", error=str(error)[:500], completedAt=time.time())


def cleanup_loop() -> None:
    while True:
        cutoff = time.time() - FILE_TTL_SECONDS
        with jobs_lock:
            expired = [job_id for job_id, job in jobs.items() if job.get("createdAt", 0) < cutoff]
            for job_id in expired:
                jobs.pop(job_id, None)
                shutil.rmtree(DOWNLOAD_DIR / job_id, ignore_errors=True)
        time.sleep(300)


app = FastAPI(title="Downloadix API", version="1.0.0", docs_url="/docs")
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["GET", "POST"], allow_headers=["*"])


@app.on_event("startup")
def start_cleanup() -> None:
    threading.Thread(target=cleanup_loop, daemon=True, name="downloadix-cleanup").start()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "downloadix-api"}


@app.post("/downloads", status_code=202, dependencies=[Depends(require_api_key)])
def create_download(payload: DownloadRequest) -> dict:
    try:
        payload.url = validate_public_url(payload.url)
    except UnsafeUrlError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {"id": job_id, "status": "queued", "progress": 0, "createdAt": time.time()}
    executor.submit(run_download, job_id, payload)
    return {"jobId": job_id, "status": "queued"}


@app.get("/downloads/{job_id}", dependencies=[Depends(require_api_key)])
def download_status(job_id: str) -> dict:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Download job not found.")
        result = {key: value for key, value in job.items() if key != "path"}
    if result["status"] == "ready":
        base = PUBLIC_BASE_URL or ""
        result["downloadUrl"] = f"{base}/files/{job_id}"
    return result


@app.get("/files/{job_id}")
def get_file(job_id: str) -> FileResponse:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job or job.get("status") != "ready" or not job.get("path"):
            raise HTTPException(status_code=404, detail="File not found or expired.")
        path = Path(job["path"])
    if not path.is_file() or DOWNLOAD_DIR not in path.parents:
        raise HTTPException(status_code=404, detail="File not found or expired.")
    return FileResponse(path, filename=job.get("filename", path.name), media_type="application/octet-stream")
