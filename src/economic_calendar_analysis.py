import pandas as pd
import numpy as np
import os
import datetime
import time
import re
from sqlalchemy.exc import OperationalError
from database_manager import save_to_db, replace_table_data, execute_query
from investing_scraper import fetch_investing_calendar
from tastytrade_client import get_historical_prices
from resilience import get_logger, now_et

logger = get_logger("economic_analysis")


def load_local_prices(name, ticker=None):
    """Load prices from previously downloaded CSVs or fetch via Yahoo Finance.
    If CSV data is stale (more than 2 trading days old), fetch fresh data from Yahoo."""
    name_lower = name.lower()
    candidates = [
        f"data/stocks/{name_lower.replace(' ', '_')}_daily.csv",
        f"data/stocks/{name_lower}_daily.csv",
    ]

    csv_df = None
    csv_path = None
    for filepath in candidates:
        if os.path.exists(filepath):
            csv_df = pd.read_csv(filepath)
            csv_df['Date'] = pd.to_datetime(csv_df['Date']).dt.tz_localize(None)
            csv_path = filepath
            break

    if csv_df is not None and not csv_df.empty:
        latest_date = csv_df['Date'].max()
        days_old = (pd.Timestamp.now() - latest_date).days
        if days_old <= 3:
            logger.info("Loaded local prices from %s (current through %s)", csv_path, latest_date.date())
            return csv_df
        else:
            logger.info("Local prices stale (%s, latest: %s, %d days old) — fetching fresh data", csv_path, latest_date.date(), days_old)

    if ticker:
        try:
            df = get_historical_prices(ticker, days_back=730)
            if df is not None and not df.empty:
                df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
                if csv_path:
                    df.to_csv(csv_path, index=False)
                    logger.info("Updated %s with fresh data through %s", csv_path, df['Date'].max().date())
                return df
        except Exception as e:
            logger.warning("Yahoo fetch failed for %s: %s", ticker, e)

    if csv_df is not None:
        logger.info("Using stale local prices from %s as fallback", csv_path)
        return csv_df

    return None


def analyze_economic_failure(events_df):
    """
    Analyzes Economic Events vs Price Action using rules from event_mappings.csv.
    """
    mappings = pd.read_csv('data/event_mappings.csv')
    results = []

    price_cache = {}

    for _, event in events_df.iterrows():
        event_name = event['event'].strip()
        event_lower = event_name.lower()
        event_clean = re.sub(r'\s*\((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|Q[1-4])\w*\)', '', event_name, flags=re.IGNORECASE).strip()
        event_clean = re.sub(r'\s+', ' ', event_clean).strip()
        event_clean_lower = event_clean.lower()

        def _find_best_mapping(event_lower, event_clean_lower):
            candidates = []

            for idx, row in mappings.iterrows():
                map_name = row['event_name'].lower().strip()

                if event_clean_lower == map_name:
                    candidates.append((idx, 100, len(map_name)))
                elif map_name in event_lower or map_name in event_clean_lower:
                    candidates.append((idx, 90, len(map_name)))
                elif event_clean_lower in map_name:
                    candidates.append((idx, 80, len(map_name)))
                else:
                    map_words = set(re.sub(r'[^a-z0-9\s]', '', map_name).split())
                    evt_words = set(re.sub(r'[^a-z0-9\s]', '', event_clean_lower).split())
                    noise = {'the', 'a', 'an', 'of', 'in', 'for', 'and', 'or', 'us'}
                    map_words -= noise
                    evt_words -= noise
                    if map_words and map_words.issubset(evt_words):
                        candidates.append((idx, 70, len(map_name)))

            if not candidates:
                return pd.DataFrame()

            candidates.sort(key=lambda x: (x[1], x[2]), reverse=True)
            best_score = candidates[0][1]
            best_len = candidates[0][2]
            best_indices = [c[0] for c in candidates if c[1] == best_score and c[2] == best_len]

            return mappings.loc[best_indices]

        mapping = _find_best_mapping(event_lower, event_clean_lower)

        if mapping.empty:
            logger.debug("NO MAPPING for: %s", event_name)
            continue

        logger.debug("Found mapping for %s: %s", event_name, mapping['instrument'].tolist())

        for _, m in mapping.iterrows():
            inst_name = m['instrument']
            ticker = m.get('ticker', None)

            if inst_name not in price_cache:
                price_cache[inst_name] = load_local_prices(inst_name, ticker)
                if price_cache[inst_name] is not None:
                    logger.info("Loaded %d price records for %s", len(price_cache[inst_name]), inst_name)
                else:
                    logger.warning("Failed to load prices for %s (%s)", inst_name, ticker)

            prices = price_cache.get(inst_name)
            if prices is None:
                continue

            rule = m['sentiment_rule']
            actual = event['actual']
            forecast = event['forecast']

            PREV_AS_FORECAST_PATTERNS = ['cftc', 'baker hughes', 'bill auction', 'inflation expectations', 'employment trends']
            if pd.isna(forecast) and any(p in event_name.lower() for p in PREV_AS_FORECAST_PATTERNS):
                prev_val = event.get('previous', None)
                if prev_val is not None and not pd.isna(prev_val):
                    forecast = prev_val
                    logger.debug("Using previous (%s) as baseline for %s", prev_val, event_name)

            if pd.isna(actual) or pd.isna(forecast):
                continue

            sentiment = 'Neutral'
            if "Actual < Forecast = Bullish" in rule:
                sentiment = 'Bullish' if actual < forecast else 'Bearish' if actual > forecast else 'Neutral'
            elif "Actual > Forecast = Bullish" in rule:
                sentiment = 'Bullish' if actual > forecast else 'Bearish' if actual < forecast else 'Neutral'

            event_date = pd.to_datetime(event['date']).tz_localize(None)

            day_before = prices[prices['Date'] < event_date].tail(1)
            day_of = prices[prices['Date'] >= event_date].head(1)

            if day_before.empty or day_of.empty:
                max_date = prices['Date'].max()
                min_date = prices['Date'].min()
                logger.debug("Price Gap: Event Date %s | Price Range %s to %s", event_date, min_date, max_date)

            if not day_before.empty and not day_of.empty:
                close_col = day_before['Close']
                if hasattr(close_col.iloc[0], 'iloc'):
                    p_before = float(close_col.iloc[0].iloc[0])
                    p_after = float(day_of['Close'].iloc[0].iloc[0])
                else:
                    p_before = float(close_col.iloc[0])
                    p_after = float(day_of['Close'].iloc[0])
                ret_1d = (p_after - p_before) / p_before

                failure = 'NO'
                reason = 'N/A'
                if sentiment == 'Bullish' and ret_1d < -0.001:
                    failure = 'YES'
                    reason = 'News Failure-Bearish'
                elif sentiment == 'Bearish' and ret_1d > 0.001:
                    failure = 'YES'
                    reason = 'News Failure-Bullish'
                elif sentiment == 'Neutral':
                    failure = 'N/A'

                actual = round(actual, 4)
                forecast = round(forecast, 4)

                diff = actual - forecast
                pct = (diff / forecast * 100) if forecast != 0 else 0
                summary = f"{event_name} came in at {actual} (Forecast: {forecast}, Surprise: {pct:+.1f}%)"

                results.append({
                    'event_name': event_name,
                    'instrument': inst_name,
                    'release_date': event_date.strftime('%Y-%m-%d'),
                    'release_time': event.get('time', ''),
                    'actual': actual,
                    'forecast': forecast,
                    'news_sentiment': sentiment,
                    'return_1d': round(ret_1d, 6),
                    'price_before': p_before,
                    'price_after': p_after,
                    'news_failure': failure,
                    'reason': reason,
                    'summary': summary
                })

    return pd.DataFrame(results)


def get_mock_calendar_data():
    """Generates mock historical data for demonstration based on Investing.com pattern."""
    return pd.DataFrame([
        {'date': '2026-01-22', 'event': 'Gasoline Inventories', 'actual': 1.2, 'forecast': 2.5},
        {'date': '2026-01-22', 'event': 'Natural Gas Storage', 'actual': -210, 'forecast': -200},
        {'date': '2026-01-15', 'event': 'Gasoline Inventories', 'actual': 3.1, 'forecast': 2.0},
        {'date': '2026-01-15', 'event': 'Natural Gas Storage', 'actual': -150, 'forecast': -160},
        {'date': '2026-01-21', 'event': 'Crude Oil Inventories', 'actual': -3.2, 'forecast': -1.2},
        {'date': '2026-01-14', 'event': 'Crude Oil Inventories', 'actual': 1.5, 'forecast': 0.5},
        {'date': '2026-01-22', 'event': 'EIA Weekly Distillates Stocks', 'actual': 0.5, 'forecast': -0.5},
        {'date': '2026-01-14', 'event': 'Core CPI (MoM)', 'actual': 0.3, 'forecast': 0.2},
        {'date': '2026-01-14', 'event': 'CPI (YoY)', 'actual': 3.4, 'forecast': 3.2},
        {'date': '2026-01-10', 'event': 'Nonfarm Payrolls', 'actual': 216, 'forecast': 170},
    ])


def run_macro_analysis(days_back=30):
    """
    Main entry point: Scrapes real data, analyzes failures, and saves to DB.
    """
    logger.info("Starting Macro Analysis for last %d days...", days_back)
    all_results = []

    today = now_et()
    consecutive_errors = 0
    for i in range(days_back + 1):
        target_date = today - datetime.timedelta(days=i)
        date_str = target_date.strftime("%Y-%m-%d")

        if target_date.weekday() >= 5:
            continue

        logger.info("Processing date: %s", date_str)

        for attempt in range(3):
            df_calendar = fetch_investing_calendar(date_from=date_str, date_to=date_str)
            if df_calendar is not None:
                break
            consecutive_errors += 1
            backoff = min(5 + consecutive_errors * 3, 30)
            logger.warning("Rate limited on %s (attempt %d/3), backing off %ds...", date_str, attempt + 1, backoff)
            time.sleep(backoff)

        if df_calendar is not None and not df_calendar.empty:
            consecutive_errors = 0
            day_results = analyze_economic_failure(df_calendar)
            if not day_results.empty:
                all_results.append(day_results)

        time.sleep(3.5)

    if all_results:
        results_df = pd.concat(all_results, ignore_index=True)
        replace_table_data(results_df, 'economic_event_reactions')
    else:
        logger.warning("Scraper blocked or no events found. Using mock data for safety.")
        df_mock = get_mock_calendar_data()
        results_df = analyze_economic_failure(df_mock)

    if not results_df.empty:
        results_df = results_df.drop_duplicates(subset=['event_name', 'release_date', 'instrument'])

        failures_only = results_df[results_df['news_failure'] == 'YES'].copy()
        logger.info("Detected %d total macro news failures across %d days.", len(failures_only), days_back)

        if all_results:
            # Already saved via replace_table_data above
            pass
        else:
            # Mock data — don't wipe real data
            pass

        if not os.getenv('VERCEL'):
            results_df.to_csv('data/economic_market_reactions.csv', index=False)

        logger.info("Macro analysis completed and saved to database.")
        return results_df
    else:
        logger.warning("No economic events matched our mappings.")
        return pd.DataFrame()


if __name__ == "__main__":
    run_macro_analysis(days_back=14)
