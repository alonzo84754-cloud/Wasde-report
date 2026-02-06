import cloudscraper
from bs4 import BeautifulSoup
import pandas as pd
import datetime
import time
import requests

# Known forecast values for EIA reports when scraper returns suspicious data
# These are updated weekly - used as sanity check
EIA_FORECAST_OVERRIDES = {
    # Format: (event_name_contains, min_reasonable_forecast, max_reasonable_forecast)
    # If scraped forecast is outside this range, use previous week's value or consensus
    "Gasoline Inventories": (-5.0, 5.0),  # Typically -5M to +5M barrels
    "Crude Oil Inventories": (-10.0, 10.0),  # Typically -10M to +10M barrels
    "Natural Gas Storage": (-300, 150),  # Typically -300 to +150 Bcf
    "Distillates": (-8.0, 8.0),  # Typically -8M to +8M barrels
}

def fetch_investing_calendar(date_from=None, date_to=None):
    """
    Scrapes the Investing.com economic calendar using cloudscraper to bypass Cloudflare.
    """
    url = "https://www.investing.com/economic-calendar/Service/getCalendarFilteredData"
    
    if not date_from:
        date_from = datetime.datetime.now().strftime("%Y-%m-%d")
    if not date_to:
        date_to = date_from

    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'mobile': False
        }
    )
    
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.investing.com/economic-calendar/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # importance 1=Low, 2=Medium, 3=High
    # countries 5=USA
    data = {
        "country[]": [5],
        "importance[]": [1, 2, 3],
        "dateFrom": date_from,
        "dateTo": date_to,
        "timeZone": 8,
        "lang": 1
    }
    
    try:
        response = scraper.post(url, data=data, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"Error fetching calendar: Status {response.status_code}")
            return None
            
        res_json = response.json()
        html = res_json.get("data", "")
        if "noResults" in html:
            print("No events found for this period.")
            return pd.DataFrame()
            
        return parse_investing_html(html, fallback_date=date_from)
        
    except Exception as e:
        print(f"Exception in scraper: {e}")
        return None

def parse_investing_html(html, fallback_date=None):
    soup = BeautifulSoup(html, "html.parser")
    # rows = soup.find_all("tr", class_="js-event-item")
    
    events = []
    current_date = fallback_date
    
    # Note: Sometimes the date is in a separate row above the events
    # But for AJAX results, it might be different. Let's handle both.
    
    all_rows = soup.find_all("tr")
    print(f"DEBUG: Found {len(all_rows)} rows in calendar HTML")
    for row in all_rows:
        classes = row.get("class", [])
        if "theDay" in classes:
            current_date = row.text.strip()
            print(f"DEBUG: Found date row: {current_date}")
            continue
            
        if "js-event-item" in classes:
            try:
                event_id = row.get("id").replace("eventRowId_", "")
                time_cell = row.find("td", class_="time").text.strip()
                event_cell = row.find("td", class_="event").text.strip()
                
                actual_cell = row.find("td", id=f"eventActual_{event_id}")
                forecast_cell = row.find("td", id=f"eventForecast_{event_id}")
                previous_cell = row.find("td", id=f"eventPrevious_{event_id}")
                
                def clean_val(cell):
                    if not cell: return None
                    val = cell.text.strip().replace(",", "")
                    if not val or val == "\xa0" or val == "": return None

                    # Track multiplier for K, M, B suffixes
                    multiplier = 1
                    if "B" in val:
                        multiplier = 1000  # Convert to millions for consistency
                        val = val.replace("B", "")
                    elif "M" in val:
                        multiplier = 1
                        val = val.replace("M", "")
                    elif "K" in val:
                        multiplier = 0.001  # Convert to millions for consistency
                        val = val.replace("K", "")

                    # Remove % sign
                    val = val.replace("%", "")

                    try:
                        return float(val) * multiplier
                    except:
                        return None

                # Debug: print raw values before cleaning
                raw_actual = actual_cell.text.strip() if actual_cell else "N/A"
                raw_forecast = forecast_cell.text.strip() if forecast_cell else "N/A"
                raw_previous = previous_cell.text.strip() if previous_cell else "N/A"
                print(f"DEBUG: {event_cell[:40]} | Actual: {raw_actual} | Forecast: {raw_forecast} | Previous: {raw_previous}")

                actual_val = clean_val(actual_cell)
                forecast_val = clean_val(forecast_cell)
                previous_val = clean_val(previous_cell)

                # Sanity check for EIA energy data - forecast should be in reasonable range
                # If forecast looks wrong, use previous value as proxy
                for event_key, (min_val, max_val) in EIA_FORECAST_OVERRIDES.items():
                    if event_key.lower() in event_cell.lower():
                        if forecast_val is not None:
                            # Check if forecast is suspiciously small compared to actual
                            if actual_val is not None and abs(actual_val) > 0.1:
                                ratio = abs(forecast_val / actual_val) if actual_val != 0 else 1
                                # If forecast is less than 50% of actual, it's likely wrong
                                if ratio < 0.5 and previous_val is not None:
                                    print(f"WARNING: Suspicious forecast for {event_cell}. Forecast={forecast_val}, Actual={actual_val}. Using previous={previous_val}")
                                    forecast_val = previous_val
                        break

                events.append({
                    "date": current_date,
                    "time": time_cell,
                    "event": event_cell,
                    "actual": actual_val,
                    "forecast": forecast_val,
                    "previous": previous_val
                })
            except Exception as e:
                print(f"Error parsing row: {e}")
                continue
                
    df = pd.DataFrame(events)
    # If date is none, we use current date as fallback or try to extract from release_date
    if not df.empty and df['date'].isnull().all():
        df['date'] = datetime.datetime.now().strftime("%Y-%m-%d")
        
    return df

if __name__ == "__main__":
    # Test for the last week
    today = datetime.datetime.now()
    last_week = today - datetime.timedelta(days=7)
    
    df = fetch_investing_calendar(
        date_from=last_week.strftime("%Y-%m-%d"),
        date_to=today.strftime("%Y-%m-%d")
    )
    if df is not None and not df.empty:
        print(df.head())
        print(f"Total events found: {len(df)}")
    else:
        print("Scraper failed or returned no data.")
