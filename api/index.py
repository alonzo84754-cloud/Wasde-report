from fastapi import FastAPI, HTTPException
import pandas as pd
import numpy as np
import os
import sys
import logging
from datetime import datetime, timezone

# Ensure src is in path for modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from database_manager import execute_query, get_db_url, get_engine

logger = logging.getLogger("api")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = FastAPI(title="WASDE News Failure API")


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def _sanitize_df(df):
    """Replace NaN/inf with None so JSON serialization doesn't crash."""
    return df.replace({np.nan: None, np.inf: None, -np.inf: None})


@app.get("/")
def read_root():
    """Health check — verifies DB connectivity."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return {
            "status": "healthy",
            "database": "connected",
            "version": "1.1.0",
            "timestamp": _utc_now_iso(),
        }
    except Exception as e:
        logger.error("Health check failed: %s", e)
        raise HTTPException(status_code=503, detail=f"Database unreachable: {e}")


@app.get("/api/deploy-internal")
def deploy_internal():
    """Endpoint to trigger a git pull and restart services on AWS."""
    deploy_secret = os.getenv("DEPLOY_SECRET")
    if not deploy_secret:
        raise HTTPException(status_code=403, detail="DEPLOY_SECRET not configured")

    # Require ?secret=... query param
    # (FastAPI will inject from query)
    from fastapi import Query
    # NOTE: This is handled by the secure version below
    raise HTTPException(status_code=403, detail="Use POST /api/deploy-internal with secret")


@app.post("/api/deploy-internal")
def deploy_internal_post(secret: str = ""):
    """Secured deploy endpoint — requires DEPLOY_SECRET."""
    deploy_secret = os.getenv("DEPLOY_SECRET")
    if not deploy_secret or secret != deploy_secret:
        raise HTTPException(status_code=403, detail="Invalid or missing deploy secret")

    try:
        import subprocess
        try:
            pull_result = subprocess.check_output(
                ["git", "pull"], stderr=subprocess.STDOUT, timeout=30
            ).decode()
        except subprocess.CalledProcessError:
            reset_result = subprocess.check_output(
                ["git", "fetch", "--all"], stderr=subprocess.STDOUT, timeout=30
            ).decode()
            reset_result += subprocess.check_output(
                ["git", "reset", "--hard", "origin/main"], stderr=subprocess.STDOUT, timeout=30
            ).decode()
            pull_result = f"Pull failed, performed hard reset:\n{reset_result}"

        return {"status": "success", "output": pull_result}
    except Exception as e:
        logger.error("Deploy failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Deploy failed: {e}")


@app.get("/api/wasde-failures")
def get_wasde_failures():
    try:
        query = "SELECT * FROM market_reactions WHERE news_failure = 'YES' ORDER BY release_date DESC"
        df = _sanitize_df(execute_query(query))
        return {"data": df.to_dict(orient="records"), "last_updated": _utc_now_iso()}
    except Exception as e:
        logger.error("wasde-failures error: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to query market reactions: {e}")


@app.get("/api/wasde-all")
def get_wasde_all():
    try:
        query = "SELECT * FROM market_reactions ORDER BY release_date DESC"
        df = _sanitize_df(execute_query(query))
        return {"data": df.to_dict(orient="records"), "last_updated": _utc_now_iso()}
    except Exception as e:
        logger.error("wasde-all error: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to query market reactions: {e}")


@app.get("/api/realtime-monitor")
def get_realtime_monitor():
    try:
        db_url = get_db_url()
        is_postgres = db_url and 'postgresql' in db_url

        if is_postgres:
            q_wasde = "SELECT commodity as name, 'WASDE Report' as event, commodity as instrument, 'WASDE' as type, return_1d, news_failure, news_sentiment, reason, price_after as price FROM market_reactions WHERE release_date >= CAST(CURRENT_DATE - INTERVAL '1 day' AS TEXT) ORDER BY release_date DESC"
        else:
            q_wasde = "SELECT commodity as name, 'WASDE Report' as event, commodity as instrument, 'WASDE' as type, return_1d, news_failure, news_sentiment, reason, price_after as price FROM market_reactions WHERE release_date >= DATE('now', '-2 days') ORDER BY release_date DESC"

        if is_postgres:
            q_econ = "SELECT event_name || ' (' || instrument || ')' as name, event_name as event, instrument, 'Economic' as type, return_1d, news_failure, 'Neutral' as news_sentiment, 'N/A' as reason, price_after as price FROM economic_event_reactions WHERE release_date >= CAST(CURRENT_DATE - INTERVAL '1 day' AS TEXT) ORDER BY release_date DESC"
        else:
            q_econ = "SELECT event_name || ' (' || instrument || ')' as name, event_name as event, instrument, 'Economic' as type, return_1d, news_failure, 'Neutral' as news_sentiment, 'N/A' as reason, price_after as price FROM economic_event_reactions WHERE release_date >= DATE('now', '-2 days') ORDER BY release_date DESC"

        df_wasde = execute_query(q_wasde)
        df_econ = execute_query(q_econ)

        frames = [df for df in [df_wasde, df_econ] if df is not None and not df.empty]
        combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        combined = _sanitize_df(combined)
        return {"data": combined.to_dict(orient="records"), "last_updated": _utc_now_iso()}
    except Exception as e:
        logger.error("realtime-monitor error: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to query monitor data: {e}")


@app.get("/api/economic-calendar")
def get_economic_calendar():
    """Returns cached economic calendar events (today + tomorrow)."""
    try:
        query = "SELECT * FROM economic_calendar_today ORDER BY date ASC, time ASC"
        df = execute_query(query)
        if df is not None and not df.empty:
            df = _sanitize_df(df)
            return {"data": df.to_dict(orient="records"), "last_updated": _utc_now_iso()}
        return {"data": [], "last_updated": _utc_now_iso()}
    except Exception:
        return {"data": [], "last_updated": _utc_now_iso()}


@app.get("/api/economic-calendar/refresh")
def refresh_economic_calendar():
    """Scrape today's calendar from Investing.com and cache in DB."""
    try:
        import datetime as dt_mod
        from investing_scraper import fetch_investing_calendar
        from database_manager import replace_table_data

        today_str = dt_mod.datetime.now().strftime("%Y-%m-%d")
        df = fetch_investing_calendar(date_from=today_str, date_to=today_str)

        if df is not None and not df.empty:
            replace_table_data(df, 'economic_calendar_today')
            return {"status": "success", "events": len(df)}
        elif df is not None:
            return {"status": "success", "events": 0, "message": "No events today"}
        else:
            raise HTTPException(status_code=502, detail="Scraper blocked or failed")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Calendar refresh error: %s", e)
        raise HTTPException(status_code=500, detail=f"Calendar refresh failed: {e}")


@app.get("/api/economic-failures")
def get_economic_failures():
    try:
        query = "SELECT * FROM economic_event_reactions WHERE news_failure = 'YES' ORDER BY release_date DESC"
        df = _sanitize_df(execute_query(query))
        return {"data": df.to_dict(orient="records"), "last_updated": _utc_now_iso()}
    except Exception as e:
        logger.error("economic-failures error: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to query economic reactions: {e}")


@app.get("/api/economic-all")
def get_economic_all():
    try:
        query = "SELECT * FROM economic_event_reactions ORDER BY release_date DESC"
        df = _sanitize_df(execute_query(query))
        return {"data": df.to_dict(orient="records"), "last_updated": _utc_now_iso()}
    except Exception as e:
        logger.error("economic-all error: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to query economic reactions: {e}")


@app.get("/api/refresh-status")
def refresh_status():
    """Recalculate news failure statuses using live market prices.

    Called by the dashboard every 60s to keep failure labels current.
    """
    try:
        from realtime_monitor import refresh_all_failure_statuses
        result = refresh_all_failure_statuses(lookback_days=3)
        return {"status": "success", "updated": result, "last_updated": _utc_now_iso()}
    except Exception as e:
        logger.error("refresh-status error: %s", e)
        raise HTTPException(status_code=500, detail=f"Refresh failed: {e}")


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
        run_macro_analysis(days_back=14)

        return {"status": "success", "message": "Pipeline completed via Cron"}
    except Exception as e:
        logger.error("Cron process error: %s", e)
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
