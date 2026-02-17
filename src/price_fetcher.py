import pandas as pd
import os
from datetime import datetime
from tastytrade_client import get_historical_prices as _tt_historical, get_current_quotes
from resilience import get_logger

logger = get_logger("price_fetcher")


def fetch_historical_prices(ticker, start_date, end_date, interval='1d'):
    """Fetch historical prices for a given ticker."""
    logger.info("Fetching %s from %s to %s...", ticker, start_date, end_date)
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    days_back = (end_dt - start_dt).days
    df = _tt_historical(ticker, days_back=days_back)
    if df is not None:
        df = df[(df['Date'] >= start_dt) & (df['Date'] <= end_dt)]
    return df if df is not None else pd.DataFrame()


def fetch_realtime_price(ticker):
    """Fetch the latest price via Tastytrade."""
    quotes = get_current_quotes([ticker])
    if ticker in quotes:
        return quotes[ticker]['price']
    return None


def save_prices(df, commodity):
    os.makedirs('data/stocks', exist_ok=True)
    filepath = f'data/stocks/{commodity}_prices.csv'
    df.to_csv(filepath)
    logger.info("Saved %s prices to %s", commodity, filepath)


if __name__ == "__main__":
    tickers = {'cotton': 'CT=F', 'sugar': 'SB=F', 'wheat': 'ZW=F'}
    for name, ticker in tickers.items():
        data = fetch_historical_prices(ticker, '2020-01-01', datetime.now().strftime('%Y-%m-%d'))
        if not data.empty:
            save_prices(data, name)
