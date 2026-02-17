import time
import pandas as pd
from sqlalchemy import text
from tastytrade_client import get_current_quotes
from database_manager import get_engine
from resilience import get_logger, CircuitBreaker, now_et

logger = get_logger("realtime_monitor")

# Track which commodity+date combos have already triggered trades this session
_traded_signals = set()

# Circuit breaker for the poll loop
_poll_circuit = CircuitBreaker(failure_threshold=5, recovery_timeout=30, name="monitor_poll")

# Instruments to monitor during the 12:00 PM - 4:00 PM window
MONITOR_LIST = {
    'Cotton': 'CT=F',
    'Corn': 'ZC=F',
    'Wheat': 'ZW=F',
    'Soybeans': 'ZS=F',
    'Soybean Meal': 'ZM=F',
    'Soybean Oil': 'ZL=F',
    'Sugar': 'SB=F',
    'Live Cattle': 'LE=F',
    'Feeder Cattle': 'GF=F',
    'Lean Hogs': 'HE=F',
    'ES': 'ES=F',
    '10Y_Bond': 'ZN=F',
    'Crude Oil': 'CL=F',
    'Gasoline': 'RB=F',
    'Natural Gas': 'NG=F'
}

# Mapping from economic instrument names to tickers
ECON_INSTRUMENT_TICKERS = {
    'ES': 'ES=F',
    'ZN': 'ZN=F',
    'NQ': 'NQ=F',
    'Crude Oil': 'CL=F',
    'Natural Gas': 'NG=F',
    'Gasoline': 'RB=F',
    'Heating Oil': 'HO=F',
    'Gold': 'GC=F',
}


def get_current_price(ticker):
    """Fetch the latest price using Tastytrade."""
    quotes = get_current_quotes([ticker])
    if ticker in quotes:
        return quotes[ticker]['price']
    return None


def _recalc_failure(sentiment, ret):
    """Recalculate failure status given sentiment and return."""
    if sentiment == 'Neutral':
        return 'N/A', 'N/A'
    if sentiment == 'Bullish' and ret < 0:
        return 'YES', 'News Failure-Bearish'
    if sentiment == 'Bearish' and ret > 0:
        return 'YES', 'News Failure-Bullish'
    return 'NO', 'N/A'


def update_realtime_status(commodity, current_price):
    """Update the database with the real-time price and recalculate failure status."""
    engine = get_engine()
    today = now_et().strftime('%Y-%m-%d')

    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT price_before, surprise, news_sentiment "
                "FROM market_reactions "
                "WHERE commodity = :commodity AND release_date = :today"
            ),
            {"commodity": commodity.lower(), "today": today},
        ).fetchone()

        if not row:
            return

        price_before, surprise, sentiment = row
        if price_before is None or pd.isna(price_before):
            return

        ret_current = (current_price - price_before) / price_before
        failure, reason = _recalc_failure(sentiment, ret_current)

        conn.execute(
            text(
                "UPDATE market_reactions "
                "SET price_after = :price_after, "
                "    return_1d = :return_1d, "
                "    news_failure = :failure, "
                "    reason = :reason, "
                "    is_realtime = 1 "
                "WHERE commodity = :commodity AND release_date = :today"
            ),
            {
                "price_after": current_price,
                "return_1d": ret_current,
                "failure": failure,
                "reason": reason,
                "commodity": commodity.lower(),
                "today": today,
            },
        )

    logger.info("Updated %s | Price: %.2f | Failure: %s", commodity, current_price, failure)


def refresh_all_failure_statuses(lookback_days=3):
    """Recalculate failure status for ALL recent entries using live prices.

    Updates both market_reactions (WASDE) and economic_event_reactions tables.
    Called by the API on dashboard load to keep data fresh.

    Args:
        lookback_days: How many days back to recalculate (default 3 = today + 2 prior).

    Returns:
        Dict with counts of updated rows per table.
    """
    engine = get_engine()
    today = now_et()
    cutoff = (today - __import__("datetime").timedelta(days=lookback_days)).strftime('%Y-%m-%d')

    updated = {"market_reactions": 0, "economic_event_reactions": 0}

    # --- 1. Recalculate WASDE (market_reactions) ---
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text(
                    "SELECT commodity, release_date, price_before, news_sentiment "
                    "FROM market_reactions "
                    "WHERE release_date >= :cutoff AND price_before IS NOT NULL"
                ),
                {"cutoff": cutoff},
            ).fetchall()

        if rows:
            # Collect all tickers we need quotes for
            commodities_needing_quotes = {}
            for commodity, release_date, price_before, sentiment in rows:
                # Map commodity name to ticker
                for name, ticker in MONITOR_LIST.items():
                    if name.lower() == commodity.lower() or commodity.lower() in name.lower():
                        commodities_needing_quotes[commodity] = ticker
                        break

            if commodities_needing_quotes:
                all_tickers = list(set(commodities_needing_quotes.values()))
                quotes = get_current_quotes(all_tickers)

                with engine.begin() as conn:
                    for commodity, release_date, price_before, sentiment in rows:
                        ticker = commodities_needing_quotes.get(commodity)
                        if not ticker or ticker not in quotes:
                            continue
                        current_price = quotes[ticker].get('price', 0)
                        if not current_price or current_price == 0:
                            continue

                        ret = (current_price - price_before) / price_before
                        failure, reason = _recalc_failure(sentiment, ret)

                        conn.execute(
                            text(
                                "UPDATE market_reactions "
                                "SET price_after = :price_after, "
                                "    return_1d = :return_1d, "
                                "    news_failure = :failure, "
                                "    reason = :reason, "
                                "    is_realtime = 1 "
                                "WHERE commodity = :commodity AND release_date = :release_date"
                            ),
                            {
                                "price_after": current_price,
                                "return_1d": ret,
                                "failure": failure,
                                "reason": reason,
                                "commodity": commodity,
                                "release_date": release_date,
                            },
                        )
                        updated["market_reactions"] += 1

    except Exception as e:
        logger.error("Error refreshing market_reactions: %s", e)

    # --- 2. Recalculate Economic Events (economic_event_reactions) ---
    try:
        with engine.begin() as conn:
            econ_rows = conn.execute(
                text(
                    "SELECT event_name, instrument, release_date, price_before, news_sentiment "
                    "FROM economic_event_reactions "
                    "WHERE release_date >= :cutoff AND price_before IS NOT NULL"
                ),
                {"cutoff": cutoff},
            ).fetchall()

        if econ_rows:
            # Collect all instrument tickers we need
            instruments_needing_quotes = {}
            for event_name, instrument, release_date, price_before, sentiment in econ_rows:
                ticker = ECON_INSTRUMENT_TICKERS.get(instrument)
                if ticker:
                    instruments_needing_quotes[instrument] = ticker

            if instruments_needing_quotes:
                all_tickers = list(set(instruments_needing_quotes.values()))
                quotes = get_current_quotes(all_tickers)

                with engine.begin() as conn:
                    for event_name, instrument, release_date, price_before, sentiment in econ_rows:
                        ticker = instruments_needing_quotes.get(instrument)
                        if not ticker or ticker not in quotes:
                            continue
                        current_price = quotes[ticker].get('price', 0)
                        if not current_price or current_price == 0:
                            continue

                        ret = (current_price - price_before) / price_before
                        failure, reason = _recalc_failure(sentiment, ret)

                        conn.execute(
                            text(
                                "UPDATE economic_event_reactions "
                                "SET price_after = :price_after, "
                                "    return_1d = :return_1d, "
                                "    news_failure = :failure, "
                                "    reason = :reason "
                                "WHERE event_name = :event_name "
                                "  AND instrument = :instrument "
                                "  AND release_date = :release_date"
                            ),
                            {
                                "price_after": current_price,
                                "return_1d": ret,
                                "failure": failure,
                                "reason": reason,
                                "event_name": event_name,
                                "instrument": instrument,
                                "release_date": release_date,
                            },
                        )
                        updated["economic_event_reactions"] += 1

    except Exception as e:
        logger.error("Error refreshing economic_event_reactions: %s", e)

    logger.info(
        "Refreshed failure statuses: %d WASDE rows, %d Economic rows",
        updated["market_reactions"], updated["economic_event_reactions"],
    )
    return updated


def run_monitor_window():
    """Runs the monitoring loop. Active polling 12-4 PM ET, periodic refresh otherwise."""
    logger.info("Starting WASDE Real-time Monitor...")

    while True:
        now = now_et()

        if now.hour >= 12 and now.hour < 16:
            # Active monitoring window — poll every 2 seconds
            if not _poll_circuit.allow_request():
                logger.warning("Circuit open — backing off to 30s")
                time.sleep(30)
                continue

            try:
                tickers = list(MONITOR_LIST.values())
                quotes = get_current_quotes(tickers)

                for name, ticker in MONITOR_LIST.items():
                    try:
                        if ticker in quotes and quotes[ticker]['price']:
                            price = float(quotes[ticker]['price'])
                            update_realtime_status(name, price)
                    except Exception as e:
                        logger.error("Error processing %s: %s", name, e)

                _poll_circuit.record_success()
            except Exception as e:
                _poll_circuit.record_failure()
                logger.error("Error fetching batch data: %s", e)

            time.sleep(2)

        elif 9 <= now.hour < 12 or 16 <= now.hour < 18:
            # Extended market hours — refresh every 60 seconds
            try:
                refresh_all_failure_statuses(lookback_days=2)
            except Exception as e:
                logger.error("Extended-hours refresh error: %s", e)
            time.sleep(60)

        else:
            # Off hours — just sleep
            time.sleep(300)


if __name__ == "__main__":
    run_monitor_window()
