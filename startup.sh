#!/bin/bash
if ! command -v ffmpeg &> /dev/null; then
    apt-get update && apt-get install -y ffmpeg
fi
exec gunicorn app.main:app --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000