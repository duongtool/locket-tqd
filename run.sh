#!/usr/bin/env bash
# Chạy Locket Tqd (backend + frontend) tại http://localhost:8000
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Đang tạo môi trường ảo và cài thư viện (chỉ lần đầu)…"
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

echo "Locket Tqd đang chạy tại http://localhost:8000"
exec .venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port 8000
