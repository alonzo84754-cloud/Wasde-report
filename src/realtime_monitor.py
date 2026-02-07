import time
import pandas as pd
import yfinance as yf
import sqlite3
from datetime import datetime, timedelta
import os

DB_PATH = 'data/wasde.db'

# Track which commodity+date combos have already triggered trades this session
_traded_signals = set()

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

def get_current_price(ticker):
    """Fetch the latest price using yfinance."""
    ticker_obj = yf.Ticker(ticker)
    # Get last 1 minute data
    df = ticker_obj.history(period='1d', interval='1m')
    if not df.empty:
        return df['Close'].iloc[-1]
    return None

def update_realtime_status(commodity, current_price):
    """Update the database with the real-time price and recalculate failure status."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 1. Get the 'price_before' and 'surprise' for today's entry
    # Note: market_analysis.py must have run once today or we must have the surprise data.
    cursor.execute("""
        SELECT price_before, surprise, news_sentiment 
        FROM market_reactions 
        WHERE commodity = ? AND release_date = ?
    """, (commodity.lower(), today))
    
    row = cursor.fetchone()
    if not row:
        # If no WASDE record for today, let's at least monitor price versus yesterday's close
        # but avoid updating if we don't have fundamental data to flag a 'failure'.
        conn.close()
        return
        
    price_before, surprise, sentiment = row
    if price_before is None or pd.isna(price_before):
        conn.close()
        return
        
    ret_current = (current_price - price_before) / price_before
    
    # Recalculate failure
    failure = 'NO'
    reason = 'N/A'
    if sentiment == 'Bullish' and ret_current < 0:
        failure = 'YES'
        reason = 'News Failure-Bearish'
    elif sentiment == 'Bearish' and ret_current > 0:
        failure = 'YES'
        reason = 'News Failure-Bullish'
        
    # 2. Update the DB
    cursor.execute("""
        UPDATE market_reactions 
        SET price_after = ?, 
            return_1d = ?, 
            news_failure = ?, 
            reason = ?,
            is_realtime = 1
        WHERE commodity = ? AND release_date = ?
    """, (current_price, ret_current, failure, reason, commodity.lower(), today))
    
    conn.commit()
    conn.close()
    print(f"Updated {commodity} | Price: {current_price:.2f} | Failure: {failure}")


def run_monitor_window():
    """Runs the monitoring loop from 12:00 PM to 4:00 PM."""
    print("Starting WASDE Real-time Monitor...")
    
    # For testing purposes, we can override time checks or simulate.
    # In production, this would be:
    # while True:
    #     now = datetime.now()
    #     if now.hour >= 12 and now.hour < 16:
    #         ... fetch and update ...
    #         time.sleep(15)
    #     else:
    #         time.sleep(60)

    # Production-ready loop for 12PM-4PM window
    # To meet client requirement for "every second or other" frequency
    while True:
        now = datetime.now()
        # Monitor during the 12:00 PM - 4:00 PM window
        if now.hour >= 12 and now.hour < 16:
            try:
                # Fetch all tickers at once to be more efficient
                tickers = list(MONITOR_LIST.values())
                data = yf.download(tickers, period='1d', interval='1m', group_by='ticker', progress=False)
                
                for name, ticker in MONITOR_LIST.items():
                    try:
                        if len(tickers) > 1:
                            ticker_df = data[ticker].dropna()
                        else:
                            ticker_df = data.dropna()
                            
                        if not ticker_df.empty:
                            price = float(ticker_df['Close'].iloc[-1])
                            update_realtime_status(name, price)
                    except Exception as e:
                        print(f"Error processing {name}: {e}")
            except Exception as e:
                print(f"Error fetching batch data: {e}")
                
            time.sleep(2) # Refresh every 2 seconds
        else:
            time.sleep(60) # Check every minute if we are in the window

if __name__ == "__main__":
    run_monitor_window()
