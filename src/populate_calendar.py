"""Populate today's economic calendar into DB for the dashboard to read.
Fetches both today and tomorrow (ET) to handle timezone differences."""
import time
import pandas as pd
from investing_scraper import fetch_investing_calendar
from database_manager import replace_table_data, init_db
from resilience import get_logger, now_et

logger = get_logger("populate_calendar")


def populate_today_calendar():
    today = now_et()
    tomorrow = today + __import__("datetime").timedelta(days=1)
    today_str = today.strftime("%Y-%m-%d")
    tomorrow_str = tomorrow.strftime("%Y-%m-%d")

    all_events = []

    logger.info("Fetching economic calendar for %s...", today_str)
    df_today = fetch_investing_calendar(date_from=today_str, date_to=today_str)
    if df_today is not None and not df_today.empty:
        all_events.append(df_today)
        logger.info("Got %d events for %s", len(df_today), today_str)

    time.sleep(3)

    logger.info("Fetching economic calendar for %s...", tomorrow_str)
    df_tomorrow = fetch_investing_calendar(date_from=tomorrow_str, date_to=tomorrow_str)
    if df_tomorrow is not None and not df_tomorrow.empty:
        all_events.append(df_tomorrow)
        logger.info("Got %d events for %s", len(df_tomorrow), tomorrow_str)

    if all_events:
        combined = pd.concat(all_events, ignore_index=True)
        replace_table_data(combined, 'economic_calendar_today')
        logger.info("Saved %d total calendar events to DB", len(combined))
    else:
        logger.warning("No calendar events found for today or tomorrow")


if __name__ == "__main__":
    populate_today_calendar()
