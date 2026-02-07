from fastapi import FastAPI, HTTPException, Body
import pandas as pd
import os
import sys

# Ensure src is in path for modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from database_manager import execute_query, get_db_url

app = FastAPI(title="WASDE News Failure API")

@app.get("/")
def read_root():
    return {"status": "WASDE API is running", "version": "1.0.1"}

@app.get("/api/deploy-internal")
def deploy_internal():
    """Endpoint to trigger a git pull and restart services on AWS"""
    try:
        import subprocess
        # Try to pull, if it fails, try to reset hard
        try:
            pull_result = subprocess.check_output(["git", "pull"], stderr=subprocess.STDOUT).decode()
        except subprocess.CalledProcessError as e:
            # If pull fails due to local changes, force reset
            reset_result = subprocess.check_output(["git", "fetch", "--all"], stderr=subprocess.STDOUT).decode()
            reset_result += subprocess.check_output(["git", "reset", "--hard", "origin/main"], stderr=subprocess.STDOUT).decode()
            pull_result = f"Pull failed, performed hard reset:\n{reset_result}"
            
        return {"status": "success", "output": pull_result}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/wasde-failures")
def get_wasde_failures():
    try:
        query = "SELECT * FROM market_reactions WHERE news_failure = 'YES' ORDER BY release_date DESC"
        df = execute_query(query)
        return df.to_dict(orient="records")
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/wasde-all")
def get_wasde_all():
    try:
        query = "SELECT * FROM market_reactions ORDER BY release_date DESC"
        df = execute_query(query)
        return df.to_dict(orient="records")
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/realtime-monitor")
def get_realtime_monitor():
    try:
        from database_manager import get_db_url
        db_url = get_db_url()
        is_postgres = db_url and 'postgresql' in db_url
        
        # 1. Get WASDE monitor data
        if is_postgres:
            q_wasde = "SELECT commodity as name, 'WASDE Report' as event, commodity as instrument, 'WASDE' as type, return_1d, news_failure, news_sentiment, reason, price_after as price FROM market_reactions WHERE release_date >= CAST(CURRENT_DATE - INTERVAL '1 day' AS TEXT) ORDER BY release_date DESC"
        else:
            q_wasde = "SELECT commodity as name, 'WASDE Report' as event, commodity as instrument, 'WASDE' as type, return_1d, news_failure, news_sentiment, reason, price_after as price FROM market_reactions WHERE release_date >= DATE('now', '-2 days') ORDER BY release_date DESC"
        
        # 2. Get Economic monitor data - Combine event and instrument in the name so it's always visible
        if is_postgres:
            q_econ = "SELECT event_name || ' (' || instrument || ')' as name, event_name as event, instrument, 'Economic' as type, return_1d, news_failure, 'Neutral' as news_sentiment, 'N/A' as reason, price_after as price FROM economic_event_reactions WHERE release_date >= CAST(CURRENT_DATE - INTERVAL '1 day' AS TEXT) ORDER BY release_date DESC"
        else:
            q_econ = "SELECT event_name || ' (' || instrument || ')' as name, event_name as event, instrument, 'Economic' as type, return_1d, news_failure, 'Neutral' as news_sentiment, 'N/A' as reason, price_after as price FROM economic_event_reactions WHERE release_date >= DATE('now', '-2 days') ORDER BY release_date DESC"
        
        df_wasde = execute_query(q_wasde)
        df_econ = execute_query(q_econ)
        
        combined = pd.concat([df_wasde, df_econ], ignore_index=True)
        return combined.to_dict(orient="records")
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/economic-failures")
def get_economic_failures():
    try:
        query = "SELECT * FROM economic_event_reactions WHERE news_failure = 'YES' ORDER BY release_date DESC"
        df = execute_query(query)
        return df.to_dict(orient="records")
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/economic-all")
def get_economic_all():
    try:
        query = "SELECT * FROM economic_event_reactions ORDER BY release_date DESC"
        df = execute_query(query)
        return df.to_dict(orient="records")
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/cron/process")
def cron_process():
    """Triggered by Vercel Cron to process data."""
    try:
        from wasde_parser import process_all_reports
        from market_analysis import run_full_analysis
        from economic_calendar_analysis import run_macro_analysis
        from database_manager import init_db
        
        init_db()
        process_all_reports()
        run_full_analysis()
        run_macro_analysis(days_back=7)
        
        return {"status": "success", "message": "Pipeline completed via Cron"}
    except Exception as e:
        return {"status": "error", "message": str(e)}



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
