#!/bin/bash
echo "=========================================="
echo "  SPED Autocorretor - Iniciando..."
echo "=========================================="

DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "[1/2] Iniciando backend Python (porta 8000)..."
cd "$DIR/backend"
python -m pip install -r requirements.txt -q
python -m uvicorn main:app --reload --port 8000 &
BACKEND_PID=$!

sleep 2

echo "[2/2] Iniciando frontend Next.js (porta 3000)..."
cd "$DIR/frontend"
npm install -q
npm run dev &
FRONTEND_PID=$!

echo ""
echo "=========================================="
echo "  Acesse: http://localhost:3000"
echo "  Backend: http://localhost:8000/docs"
echo "=========================================="
echo "  Ctrl+C para parar ambos os servidores"
echo "=========================================="

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM
wait
