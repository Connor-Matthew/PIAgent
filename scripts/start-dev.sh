#!/bin/bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo -e "${YELLOW}🚀 Starting PIAgent dev environment...${NC}"

# Install frontend deps if missing
if [ ! -d "frontend/node_modules" ]; then
    echo -e "${BLUE}📦 Installing frontend dependencies...${NC}"
    (cd frontend && npm install)
fi

# Start backend (from repo root so Python can resolve the backend package)
echo -e "${BLUE}🔧 Starting backend (FastAPI) on http://localhost:8000${NC}"
(source backend/.venv/bin/activate && uvicorn backend.main:app --reload --port 8000) &
BACKEND_PID=$!

# Wait for backend health check
for i in {1..30}; do
    if curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Backend is ready${NC}"
        break
    fi
    sleep 0.5
done

# Start frontend
echo -e "${BLUE}🎨 Starting frontend (Vite) on http://localhost:5173${NC}"
(cd frontend && npm run dev) &
FRONTEND_PID=$!

# Give frontend a moment to bind
sleep 2

echo ""
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo -e "${GREEN}  PIAgent is running!${NC}"
echo -e "${GREEN}  Backend:  http://localhost:8000${NC}"
echo -e "${GREEN}  Frontend: http://localhost:5173${NC}"
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo ""
echo "Press Ctrl+C to stop all services."
echo ""

# Cleanup on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}🛑 Shutting down services...${NC}"
    kill $FRONTEND_PID 2>/dev/null || true
    kill $BACKEND_PID 2>/dev/null || true
    wait 2>/dev/null || true
    echo -e "${GREEN}👋 All services stopped.${NC}"
    exit 0
}
trap cleanup SIGINT SIGTERM

# Keep script alive waiting for any child process
wait
