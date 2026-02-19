#!/bin/bash
set -e

# ============================================================
# WASDE Dashboard Startup Script
# ============================================================

echo "========================================"
echo "  WASDE Dashboard — Starting Up"
echo "========================================"

# ----------------------------------------------------------
# 1. Database initialization (FATAL — nothing works without it)
# ----------------------------------------------------------
echo ""
echo "[1/5] Initializing database..."
python src/database_manager.py || { echo "FATAL: Database initialization failed. Exiting."; exit 1; }
echo "  Database ready."

# ----------------------------------------------------------
# 2. Data pipeline (NON-FATAL — app can show stale data)
# ----------------------------------------------------------
echo ""
echo "[2/5] Running data pipeline (non-fatal)..."

echo "  Populating economic calendar..."
python src/populate_calendar.py || echo "  WARNING: populate_calendar.py failed (continuing)"

echo "  Parsing WASDE reports..."
python src/wasde_parser.py || echo "  WARNING: wasde_parser.py failed (continuing)"

echo "  Running market analysis..."
python src/market_analysis.py || echo "  WARNING: market_analysis.py failed (continuing)"

echo "  Running economic calendar analysis..."
python src/economic_calendar_analysis.py || echo "  WARNING: economic_calendar_analysis.py failed (continuing)"

# ----------------------------------------------------------
# 3. Start scheduler in background (WASDE auto-trigger + daily econ refresh)
# ----------------------------------------------------------
echo ""
echo "[3/6] Starting scheduler daemon..."
python src/scheduler.py &
SCHED_PID=$!
echo "  Scheduler running (PID: $SCHED_PID)"

# ----------------------------------------------------------
# 4. Start FastAPI in background
# ----------------------------------------------------------
echo ""
echo "[4/6] Starting FastAPI server..."
uvicorn api.index:app --host 0.0.0.0 --port 8000 &
API_PID=$!

# ----------------------------------------------------------
# 5. Wait for API readiness (max 30 seconds)
# ----------------------------------------------------------
echo "[5/6] Waiting for API to be ready..."
MAX_WAIT=30
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/ 2>/dev/null | grep -q "200\|503"; then
        echo "  API is ready (took ${WAITED}s)."
        break
    fi
    sleep 1
    WAITED=$((WAITED + 1))
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo "  WARNING: API did not respond within ${MAX_WAIT}s. Starting Streamlit anyway."
fi

# ----------------------------------------------------------
# 6. Start Streamlit on main port (Railway's PORT)
# ----------------------------------------------------------
echo ""
echo "[6/6] Starting Streamlit dashboard..."
echo "========================================"
echo "  Dashboard available at port ${PORT:-8501}"
echo "========================================"
streamlit run src/dashboard.py --server.port ${PORT:-8501} --server.address 0.0.0.0
