#!/bin/bash

# Initialize DB and run data pipeline
python src/database_manager.py
python src/wasde_parser.py
python src/market_analysis.py
python src/economic_calendar_analysis.py

# Start FastAPI in background
uvicorn api.index:app --host 0.0.0.0 --port 8000 &

# Start Streamlit on main port (Railway's PORT)
streamlit run src/dashboard.py --server.port ${PORT:-8501} --server.address 0.0.0.0
