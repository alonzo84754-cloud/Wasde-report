"""Inject dummy WASDE data to test live refresh pipeline.

Usage:
    python src/inject_dummy_wasde.py          # insert dummy rows
    python src/inject_dummy_wasde.py --clean   # remove dummy rows

What it does:
  1. Fetches CURRENT live prices for a handful of commodities
  2. Inserts fake market_reactions rows dated RIGHT NOW with:
     - price_before = current live price (so any tick will trigger a change)
     - A mix of Bullish / Bearish sentiments
     - news_failure initially set to NO
  3. The /api/refresh-status endpoint (called every 60s by the dashboard)
     will pick these rows up, fetch a NEW live price, and recalculate
     whether each one is a news failure or not.
  4. You can watch the dashboard flip in real-time.

Run --clean to delete the dummy rows when done testing.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from datetime import datetime
from database_manager import get_engine, init_db
from tastytrade_client import get_current_quotes
from resilience import get_logger, now_et
from sqlalchemy import text

logger = get_logger("dummy_wasde")

# Dummy commodities with forced sentiments to test both directions
DUMMY_ROWS = [
    # (commodity, ticker, sentiment, fake_surprise)
    # Bullish sentiment = ending stocks DOWN = expect price to go UP
    # If price goes DOWN instead -> News Failure-Bearish
    ("corn",         "ZC=F", "Bullish",  -5.0),
    ("wheat",        "ZW=F", "Bearish",   3.0),
    ("soybeans",     "ZS=F", "Bullish",  -2.5),
    ("soybean meal", "ZM=F", "Bearish",   1.8),
    ("cotton",       "CT=F", "Bullish",  -4.0),
    ("lean hogs",    "HE=F", "Bearish",   6.0),
    ("live cattle",  "LE=F", "Bullish",  -3.0),
]

DUMMY_TAG = "DUMMY_TEST"  # used in summary field so we can clean up


def inject():
    init_db()

    # Fetch live prices for all tickers
    tickers = list(set(t for _, t, _, _ in DUMMY_ROWS))
    logger.info("Fetching live prices for %d tickers...", len(tickers))
    quotes = get_current_quotes(tickers)

    now = now_et()
    release_date = now.strftime("%Y-%m-%d")
    release_time = now.strftime("%I:%M %p")

    rows = []
    for commodity, ticker, sentiment, surprise in DUMMY_ROWS:
        if ticker not in quotes or not quotes[ticker].get("price"):
            logger.warning("No quote for %s (%s) — skipping", commodity, ticker)
            continue

        price = quotes[ticker]["price"]
        surprise_pct = (surprise / 100.0) * 2  # small percentage

        # Offset price_before so there's a guaranteed return for testing:
        #   Bullish sentiment + price_before ABOVE current = negative return = News Failure
        #   Bearish sentiment + price_before BELOW current = positive return = News Failure
        # This ensures all dummy rows trigger a news failure immediately.
        offset_pct = 0.005  # 0.5% offset
        if sentiment == "Bullish":
            fake_price_before = price * (1 + offset_pct)  # higher than current -> negative return
        else:
            fake_price_before = price * (1 - offset_pct)  # lower than current -> positive return

        rows.append({
            "commodity": commodity,
            "release_date": release_date,
            "release_time": release_time,
            "proj_val": 100.0,
            "act_val": 100.0 + surprise,
            "surprise": surprise,
            "surprise_percent": surprise_pct,
            "return_1d": 0.0,               # will be recalculated by refresh
            "price_before": fake_price_before,  # offset to guarantee failure
            "price_after": price,            # same — refresh will update
            "news_sentiment": sentiment,
            "news_failure": "NO",            # refresh will recalculate
            "reason": "N/A",
            "summary": DUMMY_TAG,            # tag so we can clean up
            "status": "Expected Reaction",
            "is_realtime": 1,
        })

    if not rows:
        logger.error("Could not fetch any live prices — nothing inserted")
        return

    df = pd.DataFrame(rows)

    # Delete any previous dummy rows first, then insert
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM market_reactions WHERE summary = :tag"),
            {"tag": DUMMY_TAG},
        )
        df.to_sql("market_reactions", conn, if_exists="append", index=False)

    logger.info("Inserted %d dummy WASDE rows for %s at %s", len(df), release_date, release_time)
    logger.info("")
    logger.info("=== Dummy Data Inserted ===")
    for _, r in df.iterrows():
        logger.info(
            "  %s | sentiment=%s | price_before=%.2f | surprise=%.1f",
            r["commodity"], r["news_sentiment"], r["price_before"], r["surprise"],
        )
    logger.info("")
    logger.info("Now open the dashboard -> Market Monitor. Within 60s the")
    logger.info("refresh will recalculate failure status using new live prices.")
    logger.info("If the price ticks down and sentiment is Bullish -> News Failure.")
    logger.info("")
    logger.info("Run with --clean to remove dummy rows when done.")


def clean():
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM market_reactions WHERE summary = :tag"),
            {"tag": DUMMY_TAG},
        )
        logger.info("Deleted %d dummy rows from market_reactions", result.rowcount)


if __name__ == "__main__":
    if "--clean" in sys.argv:
        clean()
    else:
        inject()
