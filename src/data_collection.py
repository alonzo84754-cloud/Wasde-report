import os
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
from tastytrade_client import get_historical_prices
from resilience import get_logger, retry

logger = get_logger("data_collection")

# Instruments and their Yahoo Finance tickers
INSTRUMENTS = {
    'Cotton': 'CT=F',
    'Coffee': 'KC=F',
    'Sugar': 'SB=F',
    'Corn': 'ZC=F',
    'Wheat': 'ZW=F',
    'Soybeans': 'ZS=F',
    'Soybean_Meal': 'ZM=F',
    'Soybean_Oil': 'ZL=F',
    'Live_Cattle': 'LE=F',
    'Feeder_Cattle': 'GF=F',
    'Lean_Hogs': 'HE=F',
    'ES': 'ES=F',
    'ZN': 'ZN=F',
    'Crude Oil': 'CL=F',
    'Natural Gas': 'NG=F',
    'Gasoline': 'RB=F',
    'Heating Oil': 'HO=F',
}


@retry(max_attempts=3, base_delay=3.0, exceptions=(requests.exceptions.RequestException,))
def _download_page(url):
    """Download a single URL with retry."""
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    return response


def download_wasde_reports():
    """Download WASDE reports (TXT format) from 2020 to 2026 from USDA archive"""
    base_url = "https://esmis.nal.usda.gov"
    archive_url = "https://esmis.nal.usda.gov/publication/world-agricultural-supply-and-demand-estimates"

    data_dir = '/tmp/wasde' if os.getenv('VERCEL') else 'data/wasde'
    os.makedirs(data_dir, exist_ok=True)

    txt_links = []
    for page in range(12):
        try:
            url = f"{archive_url}?page={page}"
            logger.info("Checking archive page %d...", page)
            response = _download_page(url)
            soup = BeautifulSoup(response.content, 'html.parser')

            found_year_on_page = False
            for a in soup.find_all('a', href=True):
                text = a.get_text().upper()
                href = a['href']
                if any(year in text for year in [str(y) for y in range(2020, 2027)]) and "TXT" in text:
                    full_url = base_url + href if href.startswith('/') else href
                    filename = href.split('/')[-1]
                    if filename == 'latest.txt':
                        date_str = text.split('-')[0].strip().replace(' ', '_').lower()
                        filename = f"wasde_{date_str}.txt"
                    txt_links.append((full_url, filename))
                    found_year_on_page = True

            if not found_year_on_page and page > 1:
                pass
        except Exception as e:
            logger.warning("Error scraping page %d: %s", page, e)

    for url, filename in txt_links:
        filepath = os.path.join(data_dir, filename)
        if not os.path.exists(filepath):
            try:
                logger.info("Downloading %s...", filename)
                response = _download_page(url)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(response.text)
            except Exception as e:
                logger.warning("Failed to download %s: %s", url, e)


def fetch_stock_data():
    """Fetch daily price data for all instruments from Tastytrade since 2020"""
    days_back = (datetime.now() - datetime(2020, 1, 1)).days

    data_dir = 'data/stocks'
    os.makedirs(data_dir, exist_ok=True)

    for name, ticker in INSTRUMENTS.items():
        logger.info("Fetching data for %s (%s)...", name, ticker)
        data = get_historical_prices(ticker, days_back=days_back)
        if data is not None and not data.empty:
            filename = f"{name.lower()}_daily.csv"
            filepath = os.path.join(data_dir, filename)
            data.to_csv(filepath, index=False)
            logger.info("Saved %s (%d rows)", filename, len(data))


if __name__ == "__main__":
    logger.info("Starting data collection...")
    download_wasde_reports()
    fetch_stock_data()
    logger.info("Data collection complete.")
