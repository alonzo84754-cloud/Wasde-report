import requests
from datetime import datetime
url = 'https://www.dailyfx.com/api/v1/calendar?start=2026-01-28T00:00:00Z&end=2026-01-29T00:00:00Z'
response = requests.get(url)
print(f'Status: {response.status_code}')
if response.status_code == 200:
    data = response.json()
    print(f'Found {len(data)} events')
    for item in data[:5]:
        print(f'{item.get("date")} | {item.get("title")} | Actual: {item.get("actual")} | Forecast: {item.get("forecast")}')