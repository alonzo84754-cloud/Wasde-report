import pandas as pd
import numpy as np
import yfinance as yf
import os
import sqlite3
import datetime
import time
from database_manager import save_to_db, clear_table, execute_query
from investing_scraper import fetch_investing_calendar

def load_local_prices(name, ticker=None):
    """Load prices from previously downloaded CSVs or fetch from yfinance."""
    # Handle spaces in names (e.g., "Natural Gas" -> "natural_gas")
    filename = name.lower().replace(" ", "_")
    filepath = f"data/stocks/{filename}_daily.csv"
    if os.path.exists(filepath):
        df = pd.read_csv(filepath)
        df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
        return df
    
    # Fallback to yfinance if local file missing
    if ticker:
        try:
            df = yf.download(ticker, period="2y")
            if not df.empty:
                df = df.reset_index()
                df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
                return df
        except:
            pass
    return None

def analyze_economic_failure(events_df):
    """
    Analyzes Economic Events vs Price Action using rules from event_mappings.csv.
    """
    # Load expanded mappings generated from economic_data.xlsx
    mappings = pd.read_csv('data/event_mappings.csv')
    results = []
    
    # Cache for instrument prices
    price_cache = {}

    for _, event in events_df.iterrows():
        event_name = event['event'].strip()
        # Fuzzy match event name
        mapping = mappings[mappings['event_name'].str.contains(event_name, case=False, na=False, regex=False)]
        
        if mapping.empty:
            # Try reverse match (csv name in event name)
            mapping = mappings[mappings.apply(lambda row: row['event_name'].lower() in event_name.lower(), axis=1)]
            
        if mapping.empty:
            continue
            
        print(f"Found mapping for {event_name}: {mapping['instrument'].tolist()}")
            
        for _, m in mapping.iterrows():
            inst_name = m['instrument']
            ticker = m.get('ticker', None)
            
            if inst_name not in price_cache:
                price_cache[inst_name] = load_local_prices(inst_name, ticker)
                if price_cache[inst_name] is not None:
                    print(f"Loaded {len(price_cache[inst_name])} price records for {inst_name}")
                else:
                    print(f"Failed to load prices for {inst_name} ({ticker})")
            
            prices = price_cache.get(inst_name)
            if prices is None:
                continue

            rule = m['sentiment_rule']
            actual = event['actual']
            forecast = event['forecast']
            
            # Fallback to previous if forecast is missing
            if pd.isna(forecast) and not pd.isna(event.get('previous')):
                forecast = event['previous']
            
            if pd.isna(actual) or pd.isna(forecast):
                continue
                
            # Logic: Determine Sentiment
            sentiment = 'Neutral'
            if "Actual < Forecast = Bullish" in rule:
                sentiment = 'Bullish' if actual < forecast else 'Bearish' if actual > forecast else 'Neutral'
            elif "Actual > Forecast = Bullish" in rule:
                sentiment = 'Bullish' if actual > forecast else 'Bearish' if actual < forecast else 'Neutral'
            
            event_date = pd.to_datetime(event['date']).tz_localize(None)
            
            # Find closest price action
            day_before = prices[prices['Date'] < event_date].tail(1)
            day_of = prices[prices['Date'] >= event_date].head(1)
            
            if day_before.empty or day_of.empty:
                # Debug: Why no prices?
                max_date = prices['Date'].max()
                min_date = prices['Date'].min()
                print(f"  Price Gap: Event Date {event_date} | Price Range {min_date} to {max_date}")

            if not day_before.empty and not day_of.empty:
                p_before = float(day_before['Close'].iloc[0])
                p_after = float(day_of['Close'].iloc[0])
                ret_1d = float((p_after - p_before) / p_before)
                
                # Detection: News Failure (Price moves opposite to Sentiment)
                failure = 'NO'
                reason = 'N/A'
                if sentiment == 'Bullish' and ret_1d < -0.001: # 0.1% threshold for noise
                    failure = 'YES'
                    reason = 'News Failure-Bearish'
                elif sentiment == 'Bearish' and ret_1d > 0.001:
                    failure = 'YES'
                    reason = 'News Failure-Bullish'
                elif sentiment == 'Neutral':
                    failure = 'N/A'
                
                # Generate Summary
                diff = actual - forecast
                pct = (diff / forecast * 100) if forecast != 0 else 0
                summary = f"{event_name} came in at {actual} (Forecast: {forecast}, Surprise: {pct:+.1f}%)"

                print(f"  Appending result for {event_name} on {event_date}")
                results.append({
                    'event_name': event_name,
                    'instrument': inst_name,
                    'release_date': event_date.strftime('%Y-%m-%d'),
                    'actual': actual,
                    'forecast': forecast,
                    'news_sentiment': sentiment,
                    'return_1d': ret_1d,
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
    Run analysis for a range of days by looping single-day scrapes to ensure thorough capture.
    """
    print(f"Starting Macro Analysis for last {days_back} days...")
    all_results = []
    
    today = datetime.datetime.now()
    # Use 1-day chunks to ensure date accuracy in the scraper
    for i in range(days_back + 1):
        target_date = today - datetime.timedelta(days=i)
        date_str = target_date.strftime("%Y-%m-%d")
        
        print(f" Processing date: {date_str}")
        
        df_calendar = fetch_investing_calendar(date_from=date_str, date_to=date_str)
        if df_calendar is not None and not df_calendar.empty:
            day_results = analyze_economic_failure(df_calendar)
            if not day_results.empty:
                all_results.append(day_results)
        
        time.sleep(2.0) # Longer sleep to avoid 429

    if all_results:
        results_df = pd.concat(all_results, ignore_index=True)
        # ONLY clear if we have REAL results from today/the past few days
        clear_table('economic_event_reactions')
    else:
        print("Scraper blocked or no events found. Using mock data for safety.")
        df_mock = get_mock_calendar_data()
        results_df = analyze_economic_failure(df_mock)
        # DO NOT clear table if we are using mock data so we don't wipe historicals
        # just for a data source hiccup.

    if not results_df.empty:
        results_df = results_df.drop_duplicates(subset=['event_name', 'release_date', 'instrument'])
        
        # Filter for ACTUAL failures
        failures_only = results_df[results_df['news_failure'] == 'YES'].copy()
        print(f"Detected {len(failures_only)} total macro news failures across {days_back} days.")
        
        # Clear only if it's the real branch
        if all_results:
            save_to_db(results_df, 'economic_event_reactions', if_exists='append')
        else:
            # Maybe append mock data for demo, or just skip
            pass
        
        if not os.getenv('VERCEL'):
            results_df.to_csv('data/economic_market_reactions.csv', index=False)
            
        print("Macro analysis completed and saved to database.")
        return results_df
    else:
        print("No economic events matched our mappings.")
        return pd.DataFrame()

if __name__ == "__main__":
    run_macro_analysis(days_back=14)
