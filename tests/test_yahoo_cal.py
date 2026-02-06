import requests
from bs4 import BeautifulSoup
url = 'https://finance.yahoo.com/calendar/economic?from=2026-01-25&to=2026-01-31&day=2026-01-28'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
response = requests.get(url, headers=headers)
print(f'Status: {response.status_code}')
soup = BeautifulSoup(response.text, 'html.parser')
rows = soup.find_all('tr', class_=lambda x: x and 'data-row' in x)
print(f'Found {len(rows)} rows')
for row in rows[:5]:
    cols = row.find_all('td')
    if len(cols) > 3:
        print([c.text.strip() for c in cols])