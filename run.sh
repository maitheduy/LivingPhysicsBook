#!/bin/bash

set -e

if [ ! -f .env ]; then
    echo "❌ Không tìm thấy file .env"
    exit 1
fi

set -a
source .env
set +a

if [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ OPENAI_API_KEY đang trống"
    exit 1
fi

echo "================================================"
echo "🚀 KHỞI ĐỘNG HỆ THỐNG RAG GIÁO TRÌNH"
echo "================================================"
echo "▶ API KEY: ${OPENAI_API_KEY:0:10}... (hidden)"
echo "▶ CHROMA_PATH: $CHROMA_PATH"
echo "▶ MODEL: $MODEL"
echo "▶ PORT: $PORT"
echo "================================================"


cd "$(dirname "$0")/app/backend"

uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000} --reload
# Chạy GIÁO TRÌNH AI

set -e

# Điều chỉnh nếu cần
export RAG_PROJECT_ROOT="${RAG_PROJECT_ROOT:-$HOME/Documents/For RAG/RAG_GiaoTrinh}"
export CHROMA_PATH="${CHROMA_PATH:-$RAG_PROJECT_ROOT/chroma_db}"
export CHROMA_COLLECTION="${CHROMA_COLLECTION:-giaotrinh_physics}"
export CHAT_MODEL="${CHAT_MODEL:-gpt-4o-mini}"
export PORT="${PORT:-8000}"

if [ -z "$OPENAI_API_KEY" ]; then
  echo "❌ OPENAI_API_KEY chưa được set. Hãy export trước khi chạy."
  exit 1
fi

echo "▶ RAG_PROJECT_ROOT = $RAG_PROJECT_ROOT"
echo "▶ CHROMA_PATH       = $CHROMA_PATH"
echo "▶ Collection        = $CHROMA_COLLECTION"
echo "▶ Model             = $CHAT_MODEL"
echo "▶ Port              = $PORT"
echo ""

cd "$(dirname "$0")/app/backend"
exec uvicorn api:app --host 0.0.0.0 --port "$PORT" --reload
