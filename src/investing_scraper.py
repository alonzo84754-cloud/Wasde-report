import cloudscraper
from bs4 import BeautifulSoup
import pandas as pd
import datetime

from resilience import get_logger, retry

logger = get_logger("investing_scraper")

# Known forecast values for EIA reports when scraper returns suspicious data
EIA_FORECAST_OVERRIDES = {
    "Gasoline Inventories": (-5.0, 5.0),
    "Crude Oil Inventories": (-10.0, 10.0),
    "Natural Gas Storage": (-300, 150),
    "Distillates": (-8.0, 8.0),
}

# Reuse a single cloudscraper session (avoids re-solving Cloudflare challenge)
_scraper = None


def _get_scraper():
    global _scraper
    if _scraper is None:
        _scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'mobile': False,
            }
        )
    return _scraper


@retry(max_attempts=3, base_delay=5.0, max_delay=30.0)
def fetch_investing_calendar(date_from=None, date_to=None):
    """
    Scrapes the Investing.com economic calendar using cloudscraper to bypass Cloudflare.
    """
    url = "https://www.investing.com/economic-calendar/Service/getCalendarFilteredData"

    if not date_from:
        date_from = datetime.datetime.now().strftime("%Y-%m-%d")
    if not date_to:
        date_to = date_from

    scraper = _get_scraper()

    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.investing.com/economic-calendar/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    data = {
        "country[]": [5],
        "importance[]": [1, 2, 3],
        "dateFrom": date_from,
        "dateTo": date_to,
        "timeZone": 8,
        "lang": 1
    }

    response = scraper.post(url, data=data, headers=headers, timeout=15)
    if response.status_code != 200:
        logger.warning("Calendar fetch error: status %d", response.status_code)
        return None

    res_json = response.json()
    html = res_json.get("data", "")
    if "noResults" in html:
        logger.info("No events found for %s to %s", date_from, date_to)
        return pd.DataFrame()

    return parse_investing_html(html, fallback_date=date_from)


def parse_investing_html(html, fallback_date=None):
    soup = BeautifulSoup(html, "html.parser")

    events = []
    current_date = fallback_date

    all_rows = soup.find_all("tr")
    logger.debug("Found %d rows in calendar HTML", len(all_rows))
    for row in all_rows:
        classes = row.get("class", [])
        if "theDay" in classes:
            current_date = row.text.strip()
            continue

        if "js-event-item" in classes:
            try:
                event_id = row.get("id").replace("eventRowId_", "")
                time_cell = row.find("td", class_="time").text.strip()
                event_cell = row.find("td", class_="event").text.strip()

                sentiment_cell = row.find("td", class_="sentiment")
                importance = 1
                if sentiment_cell:
                    icon = sentiment_cell.find("i")
                    if icon:
                        icon_classes = icon.get("class", [])
                        for cls in icon_classes:
                            if "bull3" in cls or "grayFullBull498" in cls:
                                importance = 3
                            elif "bull2" in cls or "grayFullBullMedium498" in cls:
                                importance = 2
                    if importance == 1:
                        bulls = sentiment_cell.find_all("i")
                        filled = [b for b in bulls if 'grayFullBull' in ' '.join(b.get('class', []))]
                        if len(filled) >= 3:
                            importance = 3
                        elif len(filled) >= 2:
                            importance = 2

                actual_cell = row.find("td", id=f"eventActual_{event_id}")
                forecast_cell = row.find("td", id=f"eventForecast_{event_id}")
                previous_cell = row.find("td", id=f"eventPrevious_{event_id}")

                def clean_val(cell):
                    if not cell:
                        return None
                    val = cell.text.strip().replace(",", "")
                    if not val or val == "\xa0" or val == "":
                        return None

                    multiplier = 1
                    if "B" in val:
                        multiplier = 1000
                        val = val.replace("B", "")
                    elif "M" in val:
                        multiplier = 1
                        val = val.replace("M", "")
                    elif "K" in val:
                        multiplier = 0.001
                        val = val.replace("K", "")

                    val = val.replace("%", "")

                    try:
                        return float(val) * multiplier
                    except Exception:
                        return None

                actual_val = clean_val(actual_cell)
                forecast_val = clean_val(forecast_cell)
                previous_val = clean_val(previous_cell)

                # Sanity check for EIA energy data
                for event_key, (min_val, max_val) in EIA_FORECAST_OVERRIDES.items():
                    if event_key.lower() in event_cell.lower():
                        if forecast_val is not None:
                            if actual_val is not None and abs(actual_val) > 0.1:
                                ratio = abs(forecast_val / actual_val) if actual_val != 0 else 1
                                if ratio < 0.5 and previous_val is not None:
                                    logger.warning(
                                        "Suspicious forecast for %s. Forecast=%s, Actual=%s. Using previous=%s",
                                        event_cell, forecast_val, actual_val, previous_val,
                                    )
                                    forecast_val = previous_val
                        break

                def raw_val(cell):
                    if not cell:
                        return ""
                    val = cell.text.strip()
                    if not val or val == "\xa0":
                        return ""
                    return val

                events.append({
                    "date": current_date,
                    "time": time_cell,
                    "event": event_cell,
                    "importance": importance,
                    "actual": actual_val,
                    "forecast": forecast_val,
                    "previous": previous_val,
                    "actual_raw": raw_val(actual_cell),
                    "forecast_raw": raw_val(forecast_cell),
                    "previous_raw": raw_val(previous_cell),
                })
            except Exception as e:
                logger.warning("Error parsing row: %s", e)
                continue

    df = pd.DataFrame(events)
    if not df.empty and df['date'].isnull().all():
        df['date'] = datetime.datetime.now().strftime("%Y-%m-%d")

    return df


if __name__ == "__main__":
    today = datetime.datetime.now()
    last_week = today - datetime.timedelta(days=7)

    df = fetch_investing_calendar(
        date_from=last_week.strftime("%Y-%m-%d"),
        date_to=today.strftime("%Y-%m-%d")
    )
    if df is not None and not df.empty:
        logger.info("Total events found: %d", len(df))
    else:
        logger.warning("Scraper failed or returned no data.")
