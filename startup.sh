#!/bin/bash
apt-get update && apt-get install -y ffmpeg
gunicorn app.main:app --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
