import yfinance as yf
import pandas as pd
import os
from datetime import datetime

def fetch_historical_prices(ticker, start_date, end_date, interval='1d'):
    """Fetch historical prices for a given ticker."""
    print(f"Fetching {ticker} from {start_date} to {end_date}...")
    df = yf.download(ticker, start=start_date, end=end_date, interval=interval)
    return df

def fetch_realtime_price(ticker):
    """Fetch the latest price (15-min delayed or real-time depending on yfinance)."""
    stock = yf.Ticker(ticker)
    df = stock.history(period='1d', interval='1m')
    if not df.empty:
        return df['Close'].iloc[-1]
    return None

def save_prices(df, commodity):
    os.makedirs('data/stocks', exist_ok=True)
    filepath = f'data/stocks/{commodity}_prices.csv'
    df.to_csv(filepath)
    print(f"Saved {commodity} prices to {filepath}")

if __name__ == "__main__":
    # Example usage
    tickers = {'cotton': 'CT=F', 'sugar': 'SB=F', 'wheat': 'ZW=F'}
    for name, ticker in tickers.items():
        data = fetch_historical_prices(ticker, '2020-01-01', datetime.now().strftime('%Y-%m-%d'))
        if not data.empty:
            save_prices(data, name)
