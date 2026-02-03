import os
import requests
from bs4 import BeautifulSoup
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

# Instruments and their Yahoo Finance tickers
INSTRUMENTS = {
    'Cotton': 'CT=F',
    'Oil': 'CL=F',
    'Coffee': 'KC=F',
    'Sugar': 'SB=F',
    'Corn': 'ZC=F',
    'Wheat': 'ZW=F',
    'Soybeans': 'ZS=F',
    'ES': 'ES=F',
    'NQ': 'NQ=F',
    '10Y_Bond': 'ZN=F',
    '30Y_Bond': 'ZB=F',
    'USD_Index': 'DX=F',
    'VIX': '^VIX',
    'Crude_Oil': 'CL=F',
    'Natural_Gas': 'NG=F',
    'Gasoline': 'RB=F'
}

def download_wasde_reports():
    """Download WASDE reports (TXT format) from 2020 to 2026 from USDA archive"""
    base_url = "https://esmis.nal.usda.gov"
    archive_url = "https://esmis.nal.usda.gov/publication/world-agricultural-supply-and-demand-estimates"
    
    # Use /tmp for Vercel, local data/ for development
    data_dir = '/tmp/wasde' if os.getenv('VERCEL') else 'data/wasde'
    os.makedirs(data_dir, exist_ok=True)
    
    txt_links = []
    # Scrape many pages to go back to 2020
    # Usually ~12 reports per page/section, 2026 to 2020 is about 6-10 pages.
    for page in range(12):
        try:
            url = f"{archive_url}?page={page}"
            print(f"Checking archive page {page}...")
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            found_year_on_page = False
            for a in soup.find_all('a', href=True):
                text = a.get_text().upper()
                href = a['href']
                # Target 2020-2026 reports in TXT format
                if any(year in text for year in [str(y) for y in range(2020, 2027)]) and "TXT" in text:
                    full_url = base_url + href if href.startswith('/') else href
                    filename = href.split('/')[-1]
                    if filename == 'latest.txt':
                        date_str = text.split('-')[0].strip().replace(' ', '_').lower()
                        filename = f"wasde_{date_str}.txt"
                    txt_links.append((full_url, filename))
                    found_year_on_page = True
            
            if not found_year_on_page and page > 1: # Basic stop condition if we hit very old records
                 pass 
        except Exception as e:
            print(f"Error scraping page {page}: {e}")
    
    # Download the files
    for url, filename in txt_links:
        filepath = os.path.join(data_dir, filename)
        if not os.path.exists(filepath):
            try:
                print(f"Downloading {filename}...")
                response = requests.get(url, timeout=15)
                response.raise_for_status()
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(response.text)
            except Exception as e:
                print(f"Failed to download {url}: {e}")

def fetch_stock_data():
    """Fetch daily price data for all instruments from Yahoo Finance since 2020"""
    end_date = datetime.now()
    start_date = datetime(2020, 1, 1)
    
    data_dir = 'data/stocks'
    os.makedirs(data_dir, exist_ok=True)
    
    for name, ticker in INSTRUMENTS.items():
        print(f"Fetching data for {name} ({ticker}) from {start_date.date()}...")
        data = yf.download(ticker, start=start_date, end=end_date)
        if not data.empty:
            # Flatten multi-index columns if they exist
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            
            filename = f"{name.lower()}_daily.csv"
            filepath = os.path.join(data_dir, filename)
            data.to_csv(filepath)
            print(f"Saved {filename}")

if __name__ == "__main__":
    print("Starting data collection...")
    download_wasde_reports()
    fetch_stock_data()
    print("Data collection complete.")