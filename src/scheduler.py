"""WASDE + Economic Events Scheduler.

Runs as a background daemon. Responsibilities:
  1. On WASDE release days — trigger full pipeline at 12:05 PM ET
  2. Daily at 7:55 AM ET — refresh economic calendar for today
  3. Daily at 8:00 AM ET — run economic events analysis (last 14 days)

The scheduler uses Eastern Time for all checks since WASDE
reports always drop at 12:00 PM ET.
"""

import time
import threading
from datetime import datetime, timedelta
from resilience import get_logger, now_et

logger = get_logger("scheduler")


# ---------------------------------------------------------------------------
# WASDE release dates (same source of truth as market_analysis.py)
# ---------------------------------------------------------------------------
def _get_wasde_dates():
    """Import WASDE_DATES from market_analysis to avoid duplication."""
    try:
        from market_analysis import WASDE_DATES
        return WASDE_DATES
    except ImportError:
        logger.error("Cannot import WASDE_DATES from market_analysis")
        return {}


def _is_wasde_day(dt=None):
    """Check if a given date (default: today ET) is a WASDE release day."""
    dt = dt or now_et()
    dates = _get_wasde_dates()
    year_dates = dates.get(dt.year, {})
    expected = year_dates.get(dt.month)
    if expected is None:
        return False
    return dt.strftime("%Y-%m-%d") == expected


# ---------------------------------------------------------------------------
# Pipeline functions
# ---------------------------------------------------------------------------
def run_wasde_pipeline():
    """Full WASDE pipeline: download → parse → analyze → done.

    The realtime monitor / refresh-status endpoint handles live updates after.
    """
    logger.info("=== WASDE Pipeline START ===")

    try:
        from wasde_parser import process_all_reports
        logger.info("Step 1/3: Downloading & parsing WASDE reports...")
        process_all_reports()
        logger.info("Step 1/3: Done.")
    except Exception as e:
        logger.error("WASDE download/parse failed: %s", e)

    try:
        from market_analysis import run_full_analysis
        logger.info("Step 2/3: Running market analysis...")
        run_full_analysis()
        logger.info("Step 2/3: Done.")
    except Exception as e:
        logger.error("Market analysis failed: %s", e)

    try:
        from realtime_monitor import refresh_all_failure_statuses
        logger.info("Step 3/3: Initial failure status refresh...")
        result = refresh_all_failure_statuses(lookback_days=1)
        logger.info("Step 3/3: Done. Updated %s", result)
    except Exception as e:
        logger.error("Failure refresh failed: %s", e)

    logger.info("=== WASDE Pipeline END ===")


def run_economic_refresh():
    """Refresh economic calendar + run macro analysis."""
    logger.info("=== Economic Refresh START ===")

    try:
        from populate_calendar import populate_today_calendar
        logger.info("Refreshing economic calendar...")
        populate_today_calendar()
    except Exception as e:
        logger.error("Calendar refresh failed: %s", e)

    try:
        from economic_calendar_analysis import run_macro_analysis
        logger.info("Running economic analysis (14 days)...")
        run_macro_analysis(days_back=14)
    except Exception as e:
        logger.error("Economic analysis failed: %s", e)

    logger.info("=== Economic Refresh END ===")


# ---------------------------------------------------------------------------
# Scheduler loop
# ---------------------------------------------------------------------------
def _run_in_thread(fn, name):
    """Run a function in a daemon thread so it doesn't block the scheduler."""
    t = threading.Thread(target=fn, name=name, daemon=True)
    t.start()
    return t


def start_scheduler():
    """Main scheduler loop. Checks every 30 seconds."""
    logger.info("Scheduler started.")

    wasde_triggered_today = False
    econ_triggered_today = False
    last_date = None

    while True:
        try:
            now = now_et()
            today_str = now.strftime("%Y-%m-%d")

            # Reset daily flags at midnight
            if last_date and today_str != last_date:
                wasde_triggered_today = False
                econ_triggered_today = False
                logger.info("New day: %s — flags reset", today_str)
            last_date = today_str

            hour, minute = now.hour, now.minute

            # --- WASDE trigger: 12:05 PM ET on release days ---
            if (not wasde_triggered_today
                    and _is_wasde_day(now)
                    and hour == 12 and minute >= 5):
                logger.info("WASDE release day detected! Triggering pipeline...")
                wasde_triggered_today = True
                _run_in_thread(run_wasde_pipeline, "wasde-pipeline")

            # --- Economic refresh: 7:55 AM ET daily ---
            if (not econ_triggered_today
                    and hour >= 8 and minute >= 0):
                logger.info("Daily economic refresh triggered.")
                econ_triggered_today = True
                _run_in_thread(run_economic_refresh, "econ-refresh")

        except Exception as e:
            logger.error("Scheduler tick error: %s", e)

        time.sleep(30)


if __name__ == "__main__":
    start_scheduler()
